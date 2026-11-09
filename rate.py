"""Fargo-style rack-based ratings with 2-year half-life, placed on the FargoRate scale with a set of reference ratings."""
import sqlite3, numpy as np, datetime, json, sys

DB = 'de_pool.sqlite'
HALF_LIFE_Y = 2.0
PRIOR_RACKS = 3          # virtual racks won and lost vs an average newcomer
NEWCOMER = 450           # anchored-scale rating that the prior pulls towards
TODAY = datetime.date.today()
K = np.log(2) / 100      # 100 points = 2:1 rack odds

# Reference ratings (FargoRate scale, checked 3 Nov 2026): German players with 1,000+ FargoRate games who play often in German CueScore events
ANCHORS = {'Vu David': 729, 'Johanning Nils': 685, 'Letzel Manuel': 682, 'Kirsch Thomas': 659, 'Baier Pius': 655,
           'Sambulski Christian': 639, 'Tunger Simon': 629, 'Eden Georg': 627, 'Ahrens Dirk': 610, 'Garlipp Marco': 609,
           'Sobing Manfred': 578, 'Ast Markus': 574}

db = sqlite3.connect(DB)
pl = db.execute('SELECT id, last_name, first_name, shown FROM players').fetchall()
pids = [p[0] for p in pl]; idx = {p: i for i, p in enumerate(pids)}; N = len(pids)
M = db.execute('SELECT date, player_a, player_b, score_a, score_b FROM matches ORDER BY date').fetchall()
dates = np.array([datetime.date.fromisoformat(m[0]).toordinal() for m in M])
A = np.array([idx[m[1]] for m in M]); B = np.array([idx[m[2]] for m in M])
WA = np.array([m[3] for m in M], float); WB = np.array([m[4] for m in M], float)

import unicodedata
def key(s):
    s = unicodedata.normalize('NFKD', s.lower()); return ''.join(c for c in s if not unicodedata.combining(c)).replace('sh', 's')
anchor_idx = {}
for ln_fn, val in ANCHORS.items():
    ln, fn = ln_fn.split(' ', 1)
    hit = [i for i, p in enumerate(pl) if p[3] and key(p[1]) == key(ln) and key(fn).split()[0] in key(p[2])]
    if not hit:
        hit = [i for i, p in enumerate(pl) if p[3] and key(ln)[:5] == key(p[1])[:5] and key(fn)[:4] in key(p[2])]
    if hit: anchor_idx[hit[0]] = val
    else: print('anchor not found', ln_fn, file=sys.stderr)

LV = np.array([bool(p[3]) for p in pl])   # shown (German) players
# Foreign players with an established FargoRate (200+ games, decided 3 Nov 2026) keep it as a fixed rating (fargo_fixed.json: player id -> rating)
import os
# Option C (9 Nov 2026): a foreign player's FargoRate counts as virtual racks at that rating, weighted by his FargoRate
# games (FARGO_W racks per game, capped), on top of his results here. Nobody is fixed.
FARGO_W, FARGO_CAP = 0.5, 1500
FIX = np.zeros(N, bool); FIXV = np.zeros(N); FW = np.zeros(N)
if os.path.exists('data/fargo_prior.json'):
    for k, v in json.load(open('data/fargo_prior.json')).items():
        if int(k) in idx and not LV[idx[int(k)]]:
            i = idx[int(k)]; FIX[i] = True; FIXV[i] = v[0]; FW[i] = min(v[1] * FARGO_W, FARGO_CAP) / 2
print('fixed FargoRate players:', int(FIX.sum()))
PIN_OFFSET = None   # solver scale -> FargoRate scale; set once known
# Newcomer prior: a player is pulled (3 virtual racks won and lost) towards the average of his own group.
# Latvians and foreign players get separate group averages, so strong foreign BPL players do not lift the
# point that Latvian club players are pulled towards. The Latvian group average stays at 0 on the solver scale.
def solve(upto_ord, r0=None, prior_mu=0.0, iters=400, mu_f=0.0):
    sel = dates <= upto_ord
    a, b, wa, wb = A[sel], B[sel], WA[sel], WB[sel]
    age = (upto_ord - dates[sel]) / 365.25
    w = 0.5 ** (age / HALF_LIFE_Y)
    r = np.zeros(N) if r0 is None else r0.copy()
    active = np.zeros(N, bool); active[a] = True; active[b] = True
    n = wa + wb
    for _ in range(iters):
        p = 1 / (1 + np.exp(-K * (r[a] - r[b])))           # P(a wins a rack)
        ga = w * (wa - n * p); h = w * n * p * (1 - p) * K
        g = np.bincount(a, ga, N) - np.bincount(b, ga, N)
        H = np.bincount(a, h, N) + np.bincount(b, h, N)
        mu = np.where(LV, prior_mu, mu_f)
        pp = 1 / (1 + np.exp(-K * (r - mu)))
        gp = PRIOR_RACKS - 2 * PRIOR_RACKS * pp; hp = 2 * PRIOR_RACKS * pp * (1 - pp) * K
        g += gp; H += hp
        if PIN_OFFSET is not None and FIX.any():   # FargoRate as weighted virtual racks
            t = FIXV[FIX] - PIN_OFFSET; pf = 1 / (1 + np.exp(-K * (r[FIX] - t)))
            g[FIX] += FW[FIX] - 2 * FW[FIX] * pf; H[FIX] += 2 * FW[FIX] * pf * (1 - pf) * K
        step = np.clip(g / H, -60, 60)
        step[~active] = 0
        r += step
        # the overall level is pinned only by the weak prior, so move everyone together towards it as well
        pp = 1 / (1 + np.exp(-K * (r - mu)))
        gp = PRIOR_RACKS - 2 * PRIOR_RACKS * pp; hp = 2 * PRIOR_RACKS * pp * (1 - pp) * K
        al, af = active & LV, active & ~LV
        shift = float(np.clip(gp[al].sum() / hp[al].sum(), -60, 60)) if al.any() else 0.0
        r[active] += shift
        dmf = float(np.clip(-gp[af].sum() / hp[af].sum(), -60, 60)) if af.any() else 0.0
        mu_f += dmf
        if np.abs(step).max() < 0.005 and abs(shift) < 0.005 and abs(dmf) < 0.005: break
    racks = np.bincount(a, n, N) + np.bincount(b, n, N)
    eff = np.bincount(a, w * n, N) + np.bincount(b, w * n, N)
    solve.mu_f = mu_f
    return r, active, racks, eff

# Determine offset (unanchored -> anchored) with prior mean consistent with NEWCOMER
today = TODAY.toordinal(); offset = 0.0; r = None
# The prior only fixes where the scale sits; anchoring then shifts the whole scale, so solve once with prior at 0.
r, active, racks, eff = solve(today, None, prior_mu=0.0, iters=3000)
ai = list(anchor_idx); offset = float(np.mean([anchor_idx[i] - r[i] for i in ai]))
if FIX.any():   # pin the FargoRate players, re-solve, and re-place the scale with the German reference players until it settles
    for _ in range(6):
        PIN_OFFSET = offset
        r, active, racks, eff = solve(today, r, prior_mu=0.0, iters=3000)
        new = float(np.mean([anchor_idx[i] - r[i] for i in ai]))
        print('pinned solve: offset', round(offset, 1), '->', round(new, 1))
        if abs(new - offset) < 0.5: offset = new; break
        offset = new
    PIN_OFFSET = offset
print('newcomer pull point on the anchored scale:', round(offset))
final = r + offset
print('offset', round(offset, 1), 'foreign newcomer point', round(solve.mu_f + offset))
print('anchor check:', [(pl[i][1], anchor_idx[i], round(final[i])) for i in anchor_idx])

# current ratings table
nmatch = np.bincount(A, None, N) + np.bincount(B, None, N)
lastp = {}
for m in M: lastp[m[1]] = m[0]; lastp[m[2]] = m[0]
order = sorted([i for i in range(N) if active[i]], key=lambda i: (not pl[i][3], -final[i]))
db.execute('DELETE FROM ratings'); db.execute('DELETE FROM rating_history')
rank = 0
for i in order:
    rank += 1 if pl[i][3] else 0
    db.execute('INSERT INTO ratings VALUES(?,?,?,?,?,?,?)', (pids[i], round(float(final[i]), 1), int(racks[i]), round(float(eff[i]), 1),
               int(nmatch[i]), lastp[pids[i]], rank if pl[i][3] else None))

# monthly history (month-end reconstructions)
# The scale is pinned to the average Latvian player, and many new (mostly weaker) players joined over the years,
# so without a correction everyone drifts upwards over time (even players who stopped playing).
# Each month is therefore shifted so that players who have not played since that month keep, on average (median),
# the rating they have today: a player's history only moves because of his own results and his opponents'.
last_ord = np.full(N, -1); nm_cnt = np.zeros(N, int)
for k in range(len(M)):
    last_ord[A[k]] = max(last_ord[A[k]], dates[k]); last_ord[B[k]] = max(last_ord[B[k]], dates[k])
snap = []
# a player's history starts once he has 100 racks within 2 years; before that the rating is mostly the newcomer starting level
MIN_RACKS = 100
started = np.zeros(N, bool)
y, mth = 2018, 1; rr = None; mf = 0.0   # German CueScore data starts in 2018 (a handful of events before)
while (y, mth) <= (TODAY.year, TODAY.month):
    nm = datetime.date(y + (mth == 12), mth % 12 + 1, 1)
    end = min(nm - datetime.timedelta(days=1), TODAY)
    rr, act, _, _ = solve(end.toordinal(), rr, prior_mu=0.0, iters=3000, mu_f=mf)
    mf = solve.mu_f
    sel = dates <= end.toordinal(); recent = sel & (dates > end.toordinal() - 730)
    rec = np.zeros(N, bool); rec[A[recent]] = True; rec[B[recent]] = True
    nr = WA[recent] + WB[recent]
    started |= (np.bincount(A[recent], nr, N) + np.bincount(B[recent], nr, N)) >= MIN_RACKS
    rec &= started
    cnt = np.bincount(A[sel], None, N) + np.bincount(B[sel], None, N)
    ref = LV & (last_ord <= end.toordinal()) & (cnt >= 20) & (last_ord >= 0)
    corr = float(np.median(r[ref] - rr[ref])) if ref.sum() >= 15 else None
    snap.append((f'{y}-{mth:02d}', rr.copy(), rec, corr, int(ref.sum())))
    y, mth = (y + 1, 1) if mth == 12 else (y, mth + 1)
# months with too few reference players take the correction of the nearest month that has one
known = [k for k, s_ in enumerate(snap) if s_[3] is not None]
# remove one-month jumps in the correction (compare with the centred 7-month median): with few reference players one month can jump by 10 points,
# which would show as a fake spike in everybody's history
_raw = {k: snap[k][3] for k in known}
for k in known:
    win = [_raw[q] for q in known if abs(q - k) <= 3]
    med = float(np.median(win))
    if abs(_raw[k] - med) > 3: snap[k] = snap[k][:3] + (med,) + snap[k][4:]   # only one-month outliers are replaced
rows = 0
for k, (mon, rrm, rec, corr, nref) in enumerate(snap):
    if corr is None: corr = snap[min(known, key=lambda q: abs(q - k))][3] if known else 0.0
    for i in np.where(rec)[0]:
        db.execute('INSERT INTO rating_history VALUES(?,?,?)', (pids[i], mon, round(float(rrm[i] + corr + offset))))
        rows += 1
    if mon.endswith('-12') or k == len(snap) - 1: print('history', mon, 'drift correction', round(corr, 1), 'reference players', nref)
db.commit()
print('history rows', rows)
for row in db.execute('SELECT r.rank, p.first_name||" "||p.last_name, r.rating, r.racks, r.last_played FROM ratings r JOIN players p ON p.id=r.player_id WHERE r.last_played>="2024-10-17" AND r.racks>=150 ORDER BY r.rating DESC LIMIT 30'):
    print(row)
