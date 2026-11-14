"""Export SQLite DB into compact JSON for the site."""
import sqlite3, json, collections, datetime
db = sqlite3.connect('de_pool.sqlite')
# The site only shows German players. Since every match counts in the background (9 Nov 2026), most matches have no German;
# they are left out of the site files (Cloudflare Pages allows at most 25 MiB per file). Kept: matches with a shown player,
# those players' opponents, and the tournaments of these matches.
SHOWN = {r[0] for r in db.execute('SELECT id FROM players WHERE shown = 1')}
SITE_M = 'SELECT date, tournament_id, player_a, player_b, score_a, score_b, stage FROM matches WHERE player_a IN (SELECT id FROM players WHERE shown = 1) OR player_b IN (SELECT id FROM players WHERE shown = 1)'
KEEP_P = set(SHOWN)
for _, _, a, b, *_ in db.execute(SITE_M): KEEP_P.add(a); KEEP_P.add(b)
players = []
for r in db.execute('''SELECT p.id, p.first_name, p.last_name, p.country, p.city, r.rating, r.racks, r.matches, r.last_played, r.eff_racks, p.ts_id, p.cuescore_id, p.shown, p.sex
                       FROM players p JOIN ratings r ON r.player_id=p.id ORDER BY r.rating DESC'''):
    if r[0] not in KEEP_P: continue
    players.append([r[0], r[1], r[2], r[3], r[4], round(r[5], 1), r[6], r[7], r[8], round(r[9]), r[10], r[11], r[12], 1 if r[13] == 'f' else 0])
used_t = {r[1] for r in db.execute(SITE_M)}
import re
# venue shown on the site: club name, else city
def short_place(city, club):
    return (club or city or '').strip()
tours = []
for r in db.execute('SELECT id, name, date, city, club, game, source, url FROM tournaments WHERE excluded_reason IS NULL ORDER BY date'):
    if r[0] not in used_t: continue
    full = ' · '.join(x for x in (r[3], r[4]) if x)
    tours.append([r[0], r[1], r[2], short_place(r[3] or '', r[4] or ''), '', r[5], r[6], r[7], full])
stage_codes = {}
matches = []
for r in db.execute(SITE_M + ' ORDER BY date DESC, id DESC'):
    st = stage_codes.setdefault(r[6] or '', len(stage_codes))
    matches.append([int(r[0].replace('-', '')), r[1], r[2], r[3], r[4], r[5], st])
hist = collections.defaultdict(dict)
months = sorted({m for (m,) in db.execute('SELECT DISTINCT month FROM rating_history')})
mi = {m: i for i, m in enumerate(months)}
for pid, m, r in db.execute('SELECT player_id, month, rating FROM rating_history'):
    if pid not in KEEP_P: continue
    hist[pid][mi[m]] = int(r)
H = {}
for pid, d in hist.items():
    lo, hi = min(d), max(d)
    H[pid] = [lo] + [d.get(i, 0) for i in range(lo, hi + 1)]   # 0 = gap
# two files: Cloudflare Pages allows at most 25 MiB per file, and the page loads both at the same time
out = dict(generated=datetime.date.today().isoformat(), months=months, players=players, tournaments=tours, stages=list(stage_codes), history=H)
s = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
open('site/data.json', 'w').write(s)
s2 = json.dumps(dict(generated=out['generated'], matches=matches), separators=(',', ':'))
open('site/matches.json', 'w').write(s2)
print(len(s), '+', len(s2), 'bytes', len(players), 'players', len(matches), 'matches', len(tours), 'tournaments')
if max(len(s), len(s2)) > 23_000_000: print('WARNING: a site file is close to the 25 MiB Cloudflare limit')
