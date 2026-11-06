"""German Pool Rating: build the cleaned SQLite DB from cuescore_raw.json (German CueScore tournaments).
Same rules as the Latvian site (build_db.py there); Tournament Service is not used for Germany."""
import json, re, sqlite3, collections, unicodedata, datetime, os

DB = 'de_pool.sqlite'
d = {'tournaments': [], 'players': {}, 'matches': []}
P = d['players']

s = lambda v: v if isinstance(v, str) else ''

# ---------- CueScore: German tournaments ----------
CS_GAME = {'8-Ball': '8-ball', '9-Ball': '9-ball', '10-Ball': '10-ball', 'Multiball': 'multiball'}
SOURCE = {}            # tournament id -> 'cuescore'
CSIDS = set()          # player ids that come from CueScore
CS_GERMAN = set()      # CueScore ids of German players with another flag (to fill in)
CS_EXCLUDE = set()     # placeholder profiles
CS_MATCH_OFFSET = 0    # only one source, so CueScore match ids are used as they are
CS_CC = {'LTU': 'LIT', 'GBR': 'ENG', 'DEU': 'GER', 'NLD': 'NED', 'CHE': 'SUI', 'DNK': 'DEN'}   # CueScore codes -> the codes used on the site
import gzip
cs = json.load(gzip.open('data/cuescore_raw.json.gz', 'rt', encoding='utf-8') if os.path.exists('data/cuescore_raw.json.gz') else open('data/cuescore_raw.json', encoding='utf-8'))
NOT_POOL_GAME = re.compile(r'straight|14|one ?pocket|bank|snooker|black ?ball|heyball|^5$|^6$|^7$', re.I)   # games inside mixed events that are not counted
def add_cs_tournament(t, kind=''):
    tid, name, date, disc, dr, dsets, hc, typ, city, owner, nm, kept, ctry = t[:13]
    club = t[13] if len(t) > 13 else ''
    if hc: return                                    # handicap tournaments
    y, mo, dd = date.split('-')
    d['tournaments'].append([tid, name, f'{dd}.{mo}.{y[2:]}', f'{city}БК «{club}»' if club else city, CS_GAME.get(disc, disc), owner, 0, {}])
    SOURCE[tid] = 'cuescore'
def add_cs_player(cid, v):
    fn, ln, cc = v[0], v[1], v[2]
    if cid in CS_EXCLUDE or cid in P: return
    P[cid] = [ln or '', fn or '', 'GER' if cc == 'DEU' or cid in CS_GERMAN else CS_CC.get(cc, cc or '?'), '', None, 'm']
    CSIDS.add(cid)
def add_cs_match(x, pid=str):
    tid, mid, a, b, sa, sb, race, date, rnd, pen = x[:10]
    game = x[10] if len(x) > 10 else ''
    if tid not in SOURCE: return
    if len(x) > 11:
        if isinstance(x[11], str):                   # team file: column 11 = match type ('0' singles, '2' doubles)
            if x[11] != '0': return
        else:                                        # event file: column 11 = best-of-sets, column 12 = match status
            if x[11]: return
            if len(x) > 12 and x[12] and x[12] != 'finished': return
    if race and race < 3: return                     # CueScore stores the race per match
    if game and NOT_POOL_GAME.search(str(game)): return
    ts = int(datetime.datetime(*map(int, date.split('-')), 12).timestamp()) if date else 0
    d['matches'].append([tid, CS_MATCH_OFFSET + mid, pid(a), pid(b), str(sa), str(sb), race, ts, rnd, ''])
for t in cs['tournaments']: add_cs_tournament(t)
for cid, v in cs['players'].items(): add_cs_player(cid, v)
for x in cs['matches']: add_cs_match(x)

# ---------- CueScore team events: singles inside league match days (decided 3 Nov 2026) ----------
TEAM_SINGLES = set()   # team events whose singles count (the team-event name rules below do not apply to them)
NAME_ONLY = {}         # 'n:<name>' (team player not found in a roster) -> synthetic id
def name_id(k):
    if not str(k).startswith('n:'): return str(k)
    return NAME_ONLY.setdefault(k, str(9_000_000_000 + len(NAME_ONLY)))
if os.path.exists('data/team_raw.json'):
    tm = json.load(open('data/team_raw.json', encoding='utf-8'))
    for t in tm['tournaments']: add_cs_tournament(t, 'team'); TEAM_SINGLES.add(t[0])
    for k, v in tm['players'].items(): add_cs_player(name_id(k), v)
    for x in tm['matches']: add_cs_match(x, name_id)

# ---------- tournamentapp.de (Germany, mostly the south): its player profiles play the role of Tournament Service in the Latvian build ----------
TA_T, TA_P, TA_M = 7_000_000_000, 8_000_000_000, 7_000_000_000   # id offsets, so ids never clash with CueScore
TA_GAME = {'8': '8-ball', '9': '9-ball', '10': '10-ball', '8910': 'multiball', 'Multiball': 'multiball', 'Diverse': 'multiball',
           '8-Ball': '8-ball', '9-Ball': '9-ball', '10-Ball': '10-ball'}
TA_ABROAD = {'Ettelbruck', 'Wien', 'Tallinn', 'Worben', 'Eupen / Belgien', 'Demo'}   # tournamentapp.de events outside Germany (checked 3 Nov 2026)
TA_CC = {'ger': 'GER', 'aut': 'AUT', 'sui': 'SUI', 'ned': 'NED', 'lux': 'LUX', 'fra': 'FRA', 'ita': 'ITA', 'pol': 'POL', 'tur': 'TUR'}
if os.path.exists('data/ta_raw.json'):
    ta = json.load(open('data/ta_raw.json', encoding='utf-8'))
    for t in ta['tournaments']:
        tid, name, date, kind, disc, cat, city = t[:7]
        if cat == 'DP' or disc not in TA_GAME: continue
        if city in TA_ABROAD or re.search(r'\btest\b|\bdemo\b', name, re.I): continue   # only tournaments held in Germany
        if cat in ('DAM', 'MAD'): name += ' (Damen)'
        d['tournaments'].append([TA_T + tid, name, date, city, TA_GAME[disc], 'tournamentapp.de', 0, {}])
        SOURCE[TA_T + tid] = 'tournamentapp'
    for sid, (name, cc) in ta['players'].items():
        w = name.split()
        if len(w) < 2: continue
        P[str(TA_P + int(sid))] = [w[0], ' '.join(w[1:]), TA_CC.get(cc, cc.upper() or '?'), '', None, 'm']   # "Surname Firstname"
    for x in ta['matches']:
        tid, mid, code, game, a, b, sa, sb, ts = x[:9]
        if len(x) > 10 and not x[10]: continue           # not finished
        if TA_T + tid not in SOURCE: continue
        if game and game not in TA_GAME: continue        # straight pool or unknown game inside a mixed event
        d['matches'].append([TA_T + tid, TA_M + mid, str(TA_P + a), str(TA_P + b), str(sa), str(sb), 0, ts, code, ''])

# ---------- EPBF (Euro Tour, European Championships) and Matchroom / WNT: all matches of these events (decided 3 Nov 2026) ----------
# Their players play the Tournament Service role too (name matching to CueScore profiles); foreign players with an
# established FargoRate (200+ games) get it as a fixed rating in rate.py (fargo_fixed.json).
EP_T, EP_P, WN_T, WN_P = 6_000_000_000, 6_500_000_000, 5_000_000_000, 5_500_000_000
A2 = dict(lv='LVA', ee='EST', lt='LTU', fi='FIN', se='SWE', no='NOR', dk='DNK', de='DEU', pl='POL', gb='GBR', us='USA', nl='NLD', be='BEL', fr='FRA',
          es='ESP', pt='PRT', it='ITA', at='AUT', ch='CHE', cz='CZE', sk='SVK', hu='HUN', ro='ROU', bg='BGR', gr='GRC', hr='HRV', si='SVN', rs='SRB',
          ba='BIH', al='ALB', xk='XKX', mk='MKD', ua='UKR', by='BLR', ru='RUS', tr='TUR', il='ISR', ie='IRL', ph='PHL', cn='CHN', tw='TWN',
          hk='HKG', jp='JPN', kr='KOR', vn='VNM', id='IDN', my='MYS', sg='SGP', th='THA', au='AUS', nz='NZL', ca='CAN', mx='MEX', ar='ARG',
          br='BRA', cl='CHL', sa='SAU', ae='ARE', kw='KWT', qa='QAT', iq='IRQ', gy='GUY', za='ZAF', ma='MAR', eg='EGY', lu='LUX', me='MNE',
          md='MDA', ge='GEO', am='ARM', az='AZE', kz='KAZ', mt='MLT', cy='CYP', ad='AND', ly='LBY')
A2['is'] = 'ISL'
def cc3(x):
    x = (x or '').strip()
    if len(x) == 2: x = A2.get(x.lower(), '')
    x = x.upper() if len(x) == 3 else ''
    return 'GER' if x == 'DEU' else CS_CC.get(x, x or '?')
EXT_URL = {}
EP_SKIP = re.compile(r'14\.1|14/1|straight|heyball|team|wheelchair|snooker|blackball|doubles|mixed', re.I)
MON = {m: i for i, m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}
if os.path.exists('data/epbf_data.json.gz'):
    import gzip
    ep = json.load(gzip.open('data/epbf_data.json.gz', 'rt', encoding='utf-8'))
    for e in ep['events']:
        disc = e.get('disc') or ''
        g = re.search(r'\b(8|9|10)-Ball', disc)
        if not g or EP_SKIP.search(disc + ' ' + (e.get('name') or '')) or not e.get('matches'): continue
        try: sd = datetime.datetime.strptime(e['start'], '%b %d, %Y').date()
        except Exception: continue
        tid = EP_T + int(e['id'])
        d['tournaments'].append([tid, f"{e.get('name', '')} – {disc}", sd.strftime('%d.%m.%y'), '', f"{g.group(1)}-ball", 'EPBF', 0, {}])
        SOURCE[tid] = 'epbf'; EXT_URL[tid] = f"https://www.epbf.com/tournaments/{e.get('ser') or 'eurotour'}/id/{e['id']}/draw-results/"
        ts = int(datetime.datetime(sd.year, sd.month, sd.day, 12).timestamp())
        for k, m in enumerate(e['matches']):
            na, ia, fa, sa, sb, nb, ib, fb = m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11]
            if not ia or not ib or not str(sa).isdigit() or not str(sb).isdigit(): continue
            for n, i, f in ((na, ia, fa), (nb, ib, fb)):
                pid = str(EP_P + int(i))
                if pid not in P:
                    w = (n or '').split(); sur = [x for x in w if x.upper() == x and re.search(r'[^\W\d_]', x)]; fst = [x for x in w if x not in sur]
                    P[pid] = [' '.join(sur), ' '.join(fst), cc3(f), '', None, 'm']
            d['matches'].append([tid, tid * 1000 + k, str(EP_P + int(ia)), str(EP_P + int(ib)), str(sa), str(sb), int(m[3]) if str(m[3]).isdigit() else 0, ts, m[1], ''])
if os.path.exists('data/wnt_data.json.gz'):
    import gzip
    wn = json.load(gzip.open('data/wnt_data.json.gz', 'rt', encoding='utf-8'))
    WN_IDS = {}
    for k_e, e in enumerate(sorted(wn['events'], key=lambda e: e['slug'])):
        if not e['matches']: continue
        m0 = re.match(r'(\w{3}) (\d+)(?: - (?:(\w{3}) )?(\d+))?, (\d{4})', e['date'] or '')
        if not m0: continue
        y = int(m0.group(5)); sd = datetime.date(y, MON[m0.group(1)], int(m0.group(2)))
        tid = WN_T + k_e
        d['tournaments'].append([tid, e['name'], sd.strftime('%d.%m.%y'), e.get('location') or '', '9-ball', 'Matchroom', 0, {}])
        SOURCE[tid] = 'wnt'; EXT_URL[tid] = f"https://www.wntlivescores.com/events/{e['slug']}"
        for k, m in enumerate(e['matches']):
            st, no, rnd, when, tbl, na, fa, sa, sb, nb, fb = m[:11]
            if not str(sa).isdigit() or not str(sb).isdigit() or not na or not nb or 'Wildcard' in na + nb: continue
            w0 = re.match(r'(\w{3}) (\d+)', when or '')
            md = datetime.date(y, MON[w0.group(1)], int(w0.group(2))) if w0 and w0.group(1) in MON else sd
            if md < sd - datetime.timedelta(days=40): md = md.replace(year=y + 1)
            ids = []
            for n, f in ((na, fa), (nb, fb)):
                pid = WN_IDS.setdefault(n, str(WN_P + len(WN_IDS)))
                if pid not in P:
                    w = n.split(); P[pid] = [w[-1], ' '.join(w[:-1]), cc3(f), '', None, 'm']
                ids.append(pid)
            race = re.search(r'Race to (\d+)', rnd or '')
            d['matches'].append([tid, tid * 1000 + k, ids[0], ids[1], str(sa), str(sb), int(race.group(1)) if race else 0,
                                 int(datetime.datetime(md.year, md.month, md.day, 12).timestamp()), rnd, ''])

# ---------- Predator Pro Billiard Series (PBS, WPA world championships): CueScore tournaments, collected in the Latvian repo ----------
# Every set is a separate match (decided 4 Nov 2026). Used rows: race, set, set_3_3 (3:3 racks, shootout ignored), set_fixed.
# Not used: bad, shootout, no_racks. Player ids are CueScore ids, so they join the German CueScore profiles directly.
PB_M = 2_000_000_000_000
PB_USE = {'race', 'set', 'set_3_3', 'set_fixed'}
PB_SKIP = re.compile(r'parasport|wheelchair|exhibition|doubles|one ?pocket|bank', re.I)
if os.path.exists('data/pbs_data.json.gz'):
    pb = json.load(gzip.open('data/pbs_data.json.gz', 'rt', encoding='utf-8'))
    for e in pb['events']:
        g = re.search(r'\b(8|9|10)-Ball', e.get('discipline') or '', re.I)
        tid = int(e['id'])
        if not g or PB_SKIP.search(e.get('name') or '') or tid in SOURCE or not e.get('matches'): continue
        sd = datetime.date.fromisoformat(e['start'][:10])
        d['tournaments'].append([tid, e['name'], sd.strftime('%d.%m.%y'), e.get('venue') or '', f"{g.group(1)}-ball", 'PBS', 0, {}])
        SOURCE[tid] = 'cuescore'
        for m in e['matches']:
            mid, setno, rnd, when, race, ia, na, ca, sa, sb, nb, ib, cb, flag = m[:14]
            if flag not in PB_USE or sa is None or sb is None or not ia or not ib: continue
            for i, n, c in ((ia, na, ca), (ib, nb, cb)):
                w = (n or '').split()
                add_cs_player(str(i), [' '.join(w[:-1]), w[-1] if w else '', c])
            md = datetime.date.fromisoformat(when[:10]) if when else sd
            d['matches'].append([tid, PB_M + int(mid) * 10 + int(setno), str(ia), str(ib), str(sa), str(sb), int(race or 0),
                                 int(datetime.datetime(md.year, md.month, md.day, 12).timestamp()), rnd + (f' set {setno}' if setno else ''), ''])

# ---------- profile merges and fixes (Germany: none yet; add confirmed ones here) ----------
MANUAL_MERGES = []
EXCLUDE_PLAYERS = set()     # rated in the background, not shown
NAME_OVERRIDE = {}          # id: (first, last)
NOT_SAME = set()

def ph(t):
    t = unicodedata.normalize('NFKD', t.lower()); t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.translate(str.maketrans('аеосрхуі', 'aeocpxyi'))
    t = re.sub(r'[^a-z]', '', t)
    for a, b in [('sch', 's'), ('sh', 's'), ('ch', 'c'), ('zh', 'z'), ('kh', 'h'), ('ts', 'c'), ('y', 'i'), ('j', 'i'), ('w', 'v'), ('ph', 'f')]:
        t = t.replace(a, b)
    t = re.sub(r'(.)\1', r'\1', t)
    return re.sub(r'(s|is|us|a|e|ie|ijs|ij|i)$', '', t)

def is_person(v):
    return (v and v[5] in ('m', 'f') and s(v[0]) and s(v[1]) and 'izloze' not in (s(v[0]) + s(v[1])).lower()
            and '/' not in s(v[0]) + s(v[1]) and not s(v[0]).lower().startswith(('dbl', 'trpl')))


# ---------- nuLiga Bavaria (bbv-billard.liga.nu): league singles from match reports + BBV championships (added 3 Nov 2026) ----------
# League match reports with single games are public only from season 2025/26; 2022/23-2024/25 show team scores only.
# Each league match day (group + date) is one entry. 14.1 and doubles are not counted. nuLiga has no nationality:
# a player gets the country of a player with the same name in the other sources, otherwise GER.
BB_T, BB_P, BB_M = 4_000_000_000, 4_500_000_000, 4_000_000_000_000
if os.path.exists('data/bbv_nuliga_data.json.gz'):
    import gzip
    bb = json.load(gzip.open('data/bbv_nuliga_data.json.gz', 'rt', encoding='utf-8'))
    known = {}
    for k, v in P.items():
        if is_person(v): known.setdefault(tuple(sorted([ph(s(v[0])), ph(s(v[1]))])), v[2])
    BB_NAMES = {}
    def bb_player(name, person=None):
        name = re.sub(r'\s+', ' ', name).strip()
        if ',' not in name: return None
        last, first = [x.strip() for x in name.split(',', 1)]
        if not last or not first: return None
        pid = BB_NAMES.get(name)
        if pid is None:
            pid = str(BB_P + int(person)) if person else str(BB_P + 400_000_000 + len(BB_NAMES))
            BB_NAMES[name] = pid
        if pid not in P:
            P[pid] = [last, first, known.get(tuple(sorted([ph(last), ph(first)])), 'GER'), '', None, 'm']
        return pid
    for r in bb['reports'].values():                 # register league players first, so championship names find their nuLiga id
        for row in r['rows']:
            for c in row[1:3]:
                if isinstance(c, list) and ',' in c[0] and c[0].count(',') == 1: bb_player(c[0], c[1])
    LG = {(x['s'], x['g']): x['name'] for x in bb['leagues']}
    k_m = 0
    for mid, r in sorted(bb['reports'].items()):
        hm = re.match(r'BBV Pool (\d{4})/(\d\d) (.+?) (.+?) - (.+?) , (\d\d)\.(\d\d)\.(\d{4})', r['head'])
        if not hm: continue
        season = hm.group(1)[2:] + '/' + hm.group(2); league = hm.group(3)
        day = datetime.date(int(hm.group(8)), int(hm.group(7)), int(hm.group(6)))
        g = next((x['g'] for x in bb['meetings'] if x['m'] == mid), '0')
        tid = BB_T + int(g) * 100_000 + (day - datetime.date(2020, 1, 1)).days
        if tid not in SOURCE:
            d['tournaments'].append([tid, f'BBV Pool {season} {LG.get((season, g), league)}, Spieltag', day.strftime('%d.%m.%y'), 'Bayern', 'multiball', 'BBV nuLiga', 0, {}])
            SOURCE[tid] = 'nuliga'; TEAM_SINGLES.add(tid)
            EXT_URL[tid] = f"https://bbv-billard.liga.nu/cgi-bin/WebObjects/nuLigaBILLARDDE.woa/wa/groupPage?displayTyp=vorrunde&displayDetail=meetings&championship=BBV%20Pool%20{season.replace('/', '%2F')}&group={g}"
        for row in r['rows']:
            if len(row) < 5 or not isinstance(row[1], list) or not isinstance(row[2], list): continue
            gm = re.fullmatch(r'(8|9|10)-Ball', row[0] or '')
            if not gm: continue                       # 14.1, doubles
            sc = next((c for c in row[3:6] if isinstance(c, str) and re.fullmatch(r'\d+:\d+', c)), None)
            if not sc: continue
            a, b = bb_player(row[1][0], row[1][1]), bb_player(row[2][0], row[2][1])
            if not a or not b: continue
            sa, sb = sc.split(':'); k_m += 1
            d['matches'].append([tid, BB_M + k_m, a, b, sa, sb, 0, int(datetime.datetime(day.year, day.month, day.day, 12).timestamp()), f'{gm.group(1)}-Ball', ''])
    # championships (Bezirks-/Bayernmeisterschaften): matches listed with names only
    for comp, tmv in sorted(bb['tmatches'].items()):
        det = bb['tdet'].get(tmv['t'])
        if not det or len(tmv['rows']) < 3: continue
        name = det['head'].split(' // ')[0].replace(' Bayerischer Billard-Verband e.V.', '').strip()
        dm = re.search(r'(\d\d)\.(\d\d)\.(\d{4}) bis', det['text'])
        if not dm: continue
        day0 = datetime.date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
        comp_name = next((x['c'][0] for x in det['rows'] if x.get('comp') == comp), '')
        if re.search(r'Doppel|Mannschaft|Team', comp_name, re.I): continue
        gm = re.search(r'\b(8|9|10)[ -]?Ball', name, re.I)
        tid = BB_T + 90_000_000 + int(comp)
        d['tournaments'].append([tid, f'{name} ({comp_name})' if comp_name and 'Herren' not in comp_name else name, day0.strftime('%d.%m.%y'), 'Bayern',
                                 f'{gm.group(1)}-ball' if gm else '', 'BBV nuLiga', 0, {}])
        SOURCE[tid] = 'nuliga'
        EXT_URL[tid] = f"https://bbv-billard.liga.nu/cgi-bin/WebObjects/nuLigaBILLARDDE.woa/wa/tournamentMatchesReport?federation=BBV&seasonType=REGULAR&competition={comp}"
        stage = ''
        for row in tmv['rows']:
            if len(row) == 1: stage = row[0]; continue
            if len(row) < 5 or not re.fullmatch(r'\d+', str(row[1])): continue
            sc = row[4] if isinstance(row[4], str) else ''
            if not re.fullmatch(r'\d+:\d+', sc): continue
            na, nb = (x[0] if isinstance(x, list) else x for x in row[2:4])
            a, b = bb_player(na), bb_player(nb)
            if not a or not b: continue
            dd = re.search(r'(\d\d)\.(\d\d)\.(\d{4})', str(row[0]))
            md = datetime.date(int(dd.group(3)), int(dd.group(2)), int(dd.group(1))) if dd else day0
            sa, sb = sc.split(':'); k_m += 1
            d['matches'].append([tid, BB_M + k_m, a, b, sa, sb, 0, int(datetime.datetime(md.year, md.month, md.day, 12).timestamp()), stage, ''])


# ---------- Hessen league (hpbv-veveto.de, HPBV "VeVeTo"): single games from match reports, seasons 2022/23 onwards (added 3 Nov 2026) ----------
# Every team match lists 14.1, 8-, 9- and 10-ball singles twice (Hinrunde/Rückrunde of the match) with names and racks.
# Names only (no ids, no nationality): country from a same-name player in the other sources, otherwise GER.
HV_T, HV_P, HV_M = 3_000_000_000, 3_500_000_000, 3_000_000_000_000
HV_SEASON = {1: '22/23', 3: '23/24', 5: '24/25', 7: '25/26', 9: '26/27'}
if os.path.exists('data/hessen_veveto.json.gz'):
    import gzip
    hv = json.load(gzip.open('data/hessen_veveto.json.gz', 'rt', encoding='utf-8'))
    known_hv = {}
    for k, v in P.items():
        if is_person(v): known_hv.setdefault(tuple(sorted([ph(s(v[0])), ph(s(v[1]))])), v[2])
    HV_NAMES = {}
    def hv_player(name):
        name = re.sub(r'\s+', ' ', name).strip()
        w = name.split(' ')
        if len(w) < 2 or not re.search(r'[^\W\d_]', name): return None
        pid = HV_NAMES.setdefault(name, str(HV_P + len(HV_NAMES)))
        if pid not in P:
            P[pid] = [w[-1], ' '.join(w[:-1]), known_hv.get(tuple(sorted([ph(w[-1]), ph(' '.join(w[:-1]))])), 'GER'), '', None, 'm']
        return pid
    LGN = {(x['s'], x['id']): (x.get('type') or x['name'], x['number']) for x in hv['leagues']}
    k_m = 0
    for m in sorted(hv['matches'], key=lambda m: m['id']):
        txt = hv['details'].get(str(m['id']))
        if not txt: continue
        pn = re.search(r'Partie-Nr\.:\n(\d+)', txt)   # report ids are shared with the snooker seasons: the report must be this match (6 Nov 2026)
        if not pn or str(m.get('number')) != pn.group(1): continue
        dm = re.search(r'Datum:\n(\d\d)\.(\d\d)\.(\d{4})', txt)
        if not dm: continue
        day = datetime.date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
        lt, ln = LGN.get((m['s'], m['league']), ('Liga', ''))
        tid = HV_T + int(m['league']) * 100_000 + (day - datetime.date(2020, 1, 1)).days
        if tid not in SOURCE:
            d['tournaments'].append([tid, f"HPBV Pool {HV_SEASON.get(m['s'], '')} {lt} {ln}, Spieltag", day.strftime('%d.%m.%y'), 'Hessen', 'multiball', 'HPBV VeVeTo', 0, {}])
            SOURCE[tid] = 'veveto'; TEAM_SINGLES.add(tid)
            EXT_URL[tid] = f"https://hpbv-veveto.de/spielart/1/spielbetrieb/1/saison/{m['s']}/spielergebnisse/{m['id']}/anzeige"
        lines = txt.split('\n')
        for i, ln_ in enumerate(lines):
            g = re.fullmatch(r'(8|9|10) Ball', ln_)
            if not g or i + 9 >= len(lines): continue
            blk = lines[i + 1:i + 10]   # Auspielziel, W/L, name, score, vs., W/L, name, score
            if not blk[0].startswith('Auspielziel') or blk[4] != 'vs.': continue
            na, sa, nb, sb = blk[2], blk[3], blk[6], blk[7]
            if not (sa.isdigit() and sb.isdigit()): continue
            a, b = hv_player(na), hv_player(nb)
            if not a or not b: continue
            race = re.search(r'(\d+)', blk[0])
            k_m += 1
            d['matches'].append([tid, HV_M + k_m, a, b, sa, sb, int(race.group(1)) if race else 0,
                                 int(datetime.datetime(day.year, day.month, day.day, 12).timestamp()), f'{g.group(1)}-Ball', ''])

# ---------- Score Trek Battle (battle.score-trek.de): tournaments and league match days (added 6 Nov 2026) ----------
# Mostly North Rhine-Westphalia clubs. Players have Score Trek ids (some entries are names only). No nationality:
# country from a same-name player in the other sources, otherwise GER. All events count, also those in Belgium (Eupen) and
# Austria (Aleksandrs 6 Nov 2026: add everything, the data will also be used for a European rating).
# Singles only (a side with two players is doubles), 8/9/10-ball only (14.1 and others skipped), no handicap games.
ST_T, ST_P, ST_M = 1_000_000_000, 2_000_000_000, 1_000_000_000_000
ST_GAME = {'game08': '8-Ball', 'game09': '9-Ball', 'game10': '10-Ball'}
if os.path.exists('data/scoretrek_raw.json.gz'):
    import hashlib
    st = json.load(gzip.open('data/scoretrek_raw.json.gz', 'rt', encoding='utf-8'))
    def st_hash(x, mod): return int(hashlib.sha1(x.encode('utf-8')).hexdigest()[:15], 16) % mod
    known_st = {}
    for k, v in P.items():
        if is_person(v): known_st.setdefault(tuple(sorted([ph(s(v[0])), ph(s(v[1]))])), v[2])
    def st_player(q):
        name = re.sub(r'\s+', ' ', s(q.get('fullName')) or s((q.get('player') or {}).get('name'))).strip()
        w = name.split(' ')
        if len(w) < 2 or not re.search(r'[^\W\d_]', name): return None
        key = s(q.get('playerId')) or s((q.get('player') or {}).get('id')) or 'name:' + name.lower()
        pid = str(ST_P + st_hash(key, 1_000_000_000))
        if pid not in P:
            P[pid] = [w[-1], ' '.join(w[:-1]), known_st.get(tuple(sorted([ph(w[-1]), ph(' '.join(w[:-1]))])), 'GER'), '', None, 'm']
        return pid
    st_skipped = collections.Counter()
    def st_event(kind, eid, ev, name, day, city, org, url, team_singles):
        teams = {t['id']: t for t in ev.get('teams') or []}
        games = []
        for gm in ev.get('games') or []:
            gt = ST_GAME.get(gm.get('gameType'))
            if not gt: st_skipped['other game'] += 1; continue
            if gm.get('handicap1') or gm.get('handicap2'): st_skipped['handicap'] += 1; continue
            ta, tb = teams.get(gm.get('team1')), teams.get(gm.get('team2'))
            if not ta or not tb: continue                                   # bye
            if len(ta['participants']) != 1 or len(tb['participants']) != 1: st_skipped['doubles'] += 1; continue
            a, b = st_player(ta['participants'][0]), st_player(tb['participants'][0])
            if not a or not b: continue
            games.append((gm, gt, a, b))
        if not games: return
        tid = ST_T + st_hash(kind + eid, 900_000_000)
        kinds = {gt for _, gt, _, _ in games}
        disc = next(iter(kinds)).lower() if len(kinds) == 1 else 'multiball'
        d['tournaments'].append([tid, name, day.strftime('%d.%m.%y'), city, disc, org, 0, {}])
        SOURCE[tid] = 'scoretrek'; EXT_URL[tid] = url
        if team_singles: TEAM_SINGLES.add(tid)
        for gm, gt, a, b in games:
            ts = gm.get('dateTimeStartTimestamp') or int(datetime.datetime(day.year, day.month, day.day, 12).timestamp())
            d['matches'].append([tid, ST_M + st_hash(gm['id'] + eid, 999_000_000_000), a, b, str(gm.get('result1')), str(gm.get('result2')),
                                 int(gm.get('gameTarget') or 0), int(ts), gt if team_singles else '', ''])
    for eid, ev in sorted(st['tournaments'].items()):
        t = ev['t']
        if t.get('isCancelled') or not t.get('dateTimeTournamentDate'): continue
        st_event('t', eid, ev, s(t.get('title')).strip() or 'Score Trek Turnier', datetime.date.fromisoformat(t['dateTimeTournamentDate'][:10]),
                 s(t.get('locationCity')), s(t.get('clubName')) or 'Score Trek', f'https://battle.score-trek.de/tournament/live/{eid}', False)
    for eid, ev in sorted(st['matchdays'].items()):
        md = ev['md']
        if not md.get('dateTimeMatchdayDate'): continue
        st_event('m', eid, ev, f"{s(md.get('groupLabel'))} {s(md.get('seasonLabel'))}, {s(md.get('title'))}".strip(),
                 datetime.date.fromisoformat(md['dateTimeMatchdayDate'][:10]), s(md.get('locationCity')), 'Score Trek Liga',
                 f'https://battle.score-trek.de/league/matchday/{eid}', True)
    print('Score Trek skipped', dict(st_skipped))

# ---------- tournaments ----------
# BPL MINI events checked on CueScore (description / handicap setting): 2024-2025 MINIs were played without handicap
MINI_NO_HCP = {40348549, 41569429, 46429630, 49205425, 50947813, 56092414, 60456046}
TEAM_EVENT = re.compile(r'komand|\bteam\b|mannschaft', re.I)   # team championships: results inside are unreliable (decided 2026-10-23)
EXCLUDE_TOURNAMENTS = {   # team / pair events whose entrants are team names (Aleksandrs 6 Nov 2026: not counted)
    7_000_003_329: 'team event (team names)',   # tournamentapp.de Halloween Turnier 2026, Augsburg
    84481438: 'team event (team names)',        # CueScore BCQ Sommerfest (vereinsintern) 2026
}
PAIR = re.compile(r'pār|paru|pair|dubult|parn|mix ?pār|doppel|doubles?\b|scotch|\bpaar|pärchen|\bduo\b|\bmixed\b|\bteams\b', re.I)
EXCL_NAME = re.compile(r'bank ?pool|one ?pocket|14\+1|14/1|14\.1|straight|hcp|handi?cap|handikap|vorgabe|фора|marat|sn[uū]k|snooker|test', re.I)
def game_of(t):
    disc, name = t[4], t[1]
    if disc == 'multiball': return 'multiball'          # Multiball / mixed events count in Germany (decided 3 Nov 2026)
    if re.search(r'8\s*/\s*9\s*/\s*10|8910|pool9-pool8-pool10|p8/9/10', name, re.I): return 'multiball'
    if disc in ('8-ball', 'Puls8', 'Puls 8', 'Пул 8', 'Pulas-8', 'Aštuonukė'): return '8-ball'
    if disc in ('9-ball', 'Puls9', 'Devyniukė', 'Пул 9', 'Pulas-9'): return '9-ball'
    if disc in ('10-ball', 'Puls10', 'Пул 10', 'Pulas-10', 'Dešimtukė'): return '10-ball'
    # Sigulda weekly events with discipline 'Pool' (game not stated on TS) count, decided 31 Oct 2026
    if disc == 'Pool' and re.search(r'sigu\w*das? b\w+ čempionāts', name, re.I): return 'pool'
    if disc in ('Pool', 'all-around pool'): return 'multiball'
    return None

def parse_date(ddmmyy):
    dd, mm, yy = ddmmyy.split('.')
    return datetime.date(2000 + int(yy), int(mm), int(dd))

T = {}
for t in d['tournaments']:
    tid, name, date, place, disc, org = t[:6]
    name = re.sub(r'^[2-6](?=[A-ZĀČĒĢĪĶĻŅŠŪŽ])', '', name)   # stray digit from the site's icon markup
    g = game_of(t)
    excl = None
    plain = ''.join(c for c in unicodedata.normalize('NFKD', name.lower()) if not unicodedata.combining(c))
    if PAIR.search(name): excl = 'doubles'
    elif TEAM_EVENT.search(name) and tid not in TEAM_SINGLES: excl = 'team event'
    # Sigulda weekly championship is included (decided 2026-10-17)
    elif tid in EXCLUDE_TOURNAMENTS: excl = EXCLUDE_TOURNAMENTS[tid]
    elif EXCL_NAME.search(name): excl = 'other discipline'
    elif g is None: excl = 'other discipline'
    elif g == 'mixed': excl = 'mixed 8/9/10 or unknown game'
    city, club = (place.split('БК «') + [''])[:2] if 'БК «' in place else (place, '')
    city = city.replace('г. ', '').strip(); club = club.replace('»', '').strip()
    if 'клуб не назначен' in city: city = city.replace('клуб не назначен', '').strip()
    T[tid] = dict(id=tid, name=name, date=parse_date(date), city=city, club=club, disc=disc, game=g, org=org, excl=excl)

# ---------- valid matches (before player filtering) ----------
def score(x):
    try: a, b = int(x[4]), int(x[5])
    except ValueError: return None
    if a < 0 or b < 0 or (a == 0 and b == 0): return None   # forfeits (0:-1) and unplayed
    if max(a, b) < 3: return None   # races shorter than 3 are not rated (races to 3 count since 26 Oct 2026)
    return a, b

# A long match inside a round that was otherwise played to 2-3 is a typo (e.g. one 4:1 among race-to-3 group games).
# Keep long matches only when at least half of the played matches in the same round/stage are long too
# (so a longer final, semifinals or play-off rounds still count). Tournament Service only: CueScore stores the race per match.
def played(x):
    try: a, b = int(x[4]), int(x[5])
    except ValueError: return None
    return None if a < 0 or b < 0 or a + b == 0 else max(a, b)
stage_all, stage_long = collections.Counter(), collections.Counter()
for x in d['matches']:
    if x[0] in SOURCE: continue
    w = played(x)
    if w is None: continue
    stage_all[(x[0], x[8])] += 1
    if w >= 3: stage_long[(x[0], x[8])] += 1
odd_long = collections.Counter()
raw_valid = []
for x in d['matches']:
    t = T[x[0]]
    if t['excl']: continue
    sc = score(x)
    if not sc: continue
    k = (x[0], x[8])
    if x[0] not in SOURCE and stage_long[k] < 0.5 * stage_all[k]:
        odd_long[x[0]] += 1; continue
    a, b = x[2], x[3]
    if a == b or not is_person(P.get(a)) or not is_person(P.get(b)): continue
    ts = x[7]
    md = datetime.datetime.utcfromtimestamp(ts).date() if ts else t['date']
    if abs((md - t['date']).days) > 20: md = t['date']
    raw_valid.append(dict(tid=x[0], mid=x[1], a=a, b=b, sa=sc[0], sb=sc[1], race=x[6], date=md, stage=x[8]))

# ---------- canonical player mapping ----------
cnt = collections.Counter()
for m in raw_valid: cnt[m['a']] += 1; cnt[m['b']] += 1
canon = {}
def find(k):
    while canon.get(k, k) != k: k = canon[k]
    return k
# Player ids already on the site keep their id when profiles are merged, so page links never break
try: KEEP_IDS = {str(p[0]) for p in json.load(open('site/data.json', encoding='utf-8'))['players']}
except Exception: KEEP_IDS = set()
def union(ids):
    roots = sorted({find(k) for k in ids}, key=lambda k: (k not in KEEP_IDS, -cnt[k], int(k)))   # fixed order, so ids stay the same between runs
    for r in roots[1:]: canon[r] = roots[0]
groups = collections.defaultdict(list)
for k, v in P.items():
    if is_person(v) and cnt[k] and k not in CSIDS:
        groups[(v[2] or '?',) + tuple(sorted([ph(s(v[0])), ph(s(v[1]))]))].append(k)
for ids in groups.values():
    if len(ids) > 1 and frozenset(ids) not in NOT_SAME: union(ids)
for ids in MANUAL_MERGES: union(ids)

# CueScore profiles -> Tournament Service players (exact name match, or confirmed by Aleksandrs)
CS_MANUAL = {}   # CueScore id -> main id (confirmed merges)
def attach(cid, ts):
    canon[find(cid)] = find(ts)       # Tournament Service profile stays the main one
ts_index = collections.defaultdict(list)
for k, v in P.items():
    if k not in CSIDS and is_person(v): ts_index[tuple(sorted([ph(s(v[0])), ph(s(v[1]))]))].append(k)
cs_new = collections.defaultdict(list)
ABBREV = lambda v: any(len(x.strip('.')) <= 2 or x.endswith('.') for x in (s(v[0]) + ' ' + s(v[1])).split())
for cid in sorted(CSIDS, key=int):
    v = P[cid]
    if cid in CS_MANUAL: attach(cid, CS_MANUAL[cid]); continue
    key = tuple(sorted([ph(s(v[0])), ph(s(v[1]))]))
    if key in ts_index:
        roots = sorted({find(k) for k in ts_index[key]}, key=lambda r: (-cnt[r], int(r)))
        attach(cid, roots[0])
    elif is_person(v) and not ABBREV(v): cs_new[(v[2],) + key].append(cid)   # same name and country: merged (abbreviated names like "Alex W." are not)
for ids in cs_new.values():
    if len(ids) > 1: union(ids)
LATE_MERGES = []   # [main id, other id] confirmed by Aleksandrs
for ids in LATE_MERGES: union(ids)
C = lambda k: find(k)

# ---------- everyone in the counted events is rated; only German players are shown on the site ----------
def country(k): return P[k][2]
eligible = set(C(k) for k in cnt)
SHOWN = {k for k in eligible if country(k) == 'GER' and k not in EXCLUDE_PLAYERS}

# ---------- final matches; a tournament entry that repeats another entry (>=50% same results) is a duplicate ----------
def rkey(m, a, b): return tuple(sorted([(a, m['sa']), (b, m['sb'])]))
cand = []
for m in sorted(raw_valid, key=lambda m: (m['date'], m['tid'], m['mid'])):
    a, b = C(m['a']), C(m['b'])
    if a in eligible and b in eligible and a != b: cand.append((m, a, b))
by_t = collections.defaultdict(set)
for m, a, b in cand: by_t[m['tid']].add(rkey(m, a, b))
dup_of = {}
SAME_GAMES = collections.defaultdict(set)   # nuLiga league day -> results also stored in a CueScore team event
tids = sorted(by_t)
for i, t1 in enumerate(tids):
    for t2 in tids[i + 1:]:
        if abs((T[t1]['date'] - T[t2]['date']).days) > 3: continue
        ov = len(by_t[t1] & by_t[t2])
        if ov and ov >= 0.5 * min(len(by_t[t1]), len(by_t[t2])):
            sp = [t for t in (t1, t2) if T[t]['name'].endswith(', Spieltag')]   # nuLiga league day: drop only the repeated games, not the day
            if len(sp) == 2: continue   # two league match days are never copies of each other
            if sp and len(sp) == 1:
                other = t2 if sp[0] == t1 else t1
                SAME_GAMES[sp[0]] |= by_t[other]
                continue
            dup_of[t2] = t1
DUPLICATE_ENTRIES = {t2: t1 for t2, t1 in dup_of.items()}
matches = []
for m, a, b in cand:
    if m['tid'] in DUPLICATE_ENTRIES: continue   # the whole event is a copy of another entry; keep only the original
    if rkey(m, a, b) in SAME_GAMES.get(m['tid'], ()): continue
    matches.append(dict(m, a=a, b=b))
print('duplicate entries', [(T[t2]['name'], T[t1]['name']) for t2, t1 in DUPLICATE_ENTRIES.items()])

# team events: keep their singles only when there are enough of them to mean something
TEAM = re.compile(r'koman|team', re.I)
per_t = collections.Counter(m['tid'] for m in matches)
small_team = {t for t, n in per_t.items() if TEAM.search(T[t]['name']) and n < 10 and t not in TEAM_SINGLES}
for t in small_team: T[t]['excl'] = 'team event, fewer than 10 matches'
matches = [m for m in matches if m['tid'] not in small_team]
used = collections.Counter()
for m in matches: used[m['a']] += 1; used[m['b']] += 1

# ---------- write SQLite ----------
if os.path.exists(DB): os.remove(DB)
db = sqlite3.connect(DB)
db.executescript('''
CREATE TABLE players(id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, country TEXT, city TEXT, birth TEXT, sex TEXT,
  ts_id INTEGER, cuescore_id INTEGER, fargo_id INTEGER, shown INTEGER);
CREATE TABLE player_profiles(source TEXT, source_id TEXT, player_id INTEGER, name_on_source TEXT, PRIMARY KEY(source, source_id));
CREATE TABLE tournaments(id INTEGER PRIMARY KEY, source TEXT, source_id TEXT, name TEXT, date TEXT, city TEXT, club TEXT,
  game TEXT, discipline_raw TEXT, organizer TEXT, excluded_reason TEXT, url TEXT);
CREATE TABLE matches(id INTEGER PRIMARY KEY, source TEXT, source_id TEXT, tournament_id INTEGER, date TEXT, stage TEXT, race_to INTEGER,
  player_a INTEGER, player_b INTEGER, score_a INTEGER, score_b INTEGER, game TEXT);
CREATE TABLE ratings(player_id INTEGER PRIMARY KEY, rating REAL, racks INTEGER, eff_racks REAL, matches INTEGER, last_played TEXT, rank INTEGER);
CREATE TABLE rating_history(player_id INTEGER, month TEXT, rating REAL, PRIMARY KEY(player_id, month));
''')
TRL = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'a b v g d e jo zh z i j k l m n o p r s t u f h c ch sh shch _ y _ e ju ja'.split()))
def translit(t):
    out = ''.join(TRL.get(ch.lower(), ch) for ch in t).replace('_', '')
    return out[:1].upper() + out[1:]
LOOK = str.maketrans('АаВЕеКМНОоРрСсТуХх', 'AaBEeKMHOoPpCcTyXx')   # Cyrillic look-alike letters inside Latin names
CYR = re.compile('[А-Яа-яЁё]')
last_seen = {}
for m in raw_valid:
    for p in (m['a'], m['b']): last_seen[p] = max(last_seen.get(p, m['date']), m['date'])
group = collections.defaultdict(list)
for k in P:
    if is_person(P[k]) and C(k) in used: group[C(k)].append(k)
PARTICLE = {'von', 'van', 'de', 'der', 'den', 'zu', 'vom', 'zum', 'da', 'di', 'del', 'la', 'le'}
def cap(x):   # all-capital or all-small names get normal capitals ("MIKHAIL" -> "Mikhail"); other names keep their CueScore spelling
    x = x.strip(' .')
    if x != x.upper() and x != x.lower(): return x
    return ' '.join(w if w.lower() in PARTICLE and i else '-'.join(p[:1].upper() + p[1:].lower() for p in w.split('-')) for i, w in enumerate(x.split()))
def display(root):
    f, l = display_raw(root); return cap(f), cap(l)
def display_raw(root):
    for k in group[root]:
        if k in NAME_OVERRIDE: return NAME_OVERRIDE[k]
    latin = [k for k in group[root] if not CYR.search(s(P[k][0]) + s(P[k][1]))]
    cands = [k for k in latin if k in CSIDS and not k.startswith('9000')] or latin or group[root]   # Germany: prefer CueScore spelling
    best = max(cands, key=lambda k: last_seen.get(k, datetime.date.min))
    f, l = s(P[best][1]), s(P[best][0])
    f2, l2 = f.translate(LOOK), l.translate(LOOK)
    if not CYR.search(f2 + l2): return f2, l2
    return translit(f), translit(l)
# Men / women: CueScore has no gender, so a player who played in a women's event (Damen, Frauen, Ladies...) is shown as a woman
WOMEN_EVENT = re.compile(r'damen|frauen|ladies|women|female|girls|m[äa]dchen|juniorinnen|seniorinnen|spielerinnen', re.I)
SEX_OVERRIDE = {}   # id: 'f' or 'm' (corrections)
women = set()
for m in matches:
    if WOMEN_EVENT.search(T[m['tid']]['name']): women.add(m['a']); women.add(m['b'])
def plain(x): return ''.join(c for c in unicodedata.normalize('NFKD', x.lower()) if not unicodedata.combining(c)).strip()
def sex_of(k, first, last):
    if k in SEX_OVERRIDE: return SEX_OVERRIDE[k]
    return 'f' if k in women else 'm'
for k in sorted(used, key=int):
    v = P[k]; first, last = display(k)
    v = list(v); v[5] = sex_of(k, first, last)
    if v[2] in ('', '?', 'TBA', None):   # placeholder country on the main profile: take the one from another merged profile
        cc_ = collections.Counter(P[x][2] for x in group[k] if P[x][2] not in ('', '?', 'TBA', None))
        if cc_: v = list(v); v[2] = cc_.most_common(1)[0][0]
    city = next((s(P[x][3]) for x in sorted(group[k], key=lambda x: -cnt[x]) if s(P[x][3])), '')
    birth = next((s(P[x][4]) for x in sorted(group[k], key=lambda x: -len(s(P[x][4]))) if s(P[x][4])), '')
    cs_id = next((int(x) for x in group[k] if x in CSIDS and int(x) < 9_000_000_000), None)
    ts_id = next((int(x) - TA_P for x in group[k] if TA_P <= int(x) < 9_000_000_000), None)   # tournamentapp.de player id (sid)
    db.execute('INSERT INTO players VALUES(?,?,?,?,?,?,?,?,?,NULL,?)', (int(k), first, last, v[2], city, birth, v[5], ts_id, cs_id, int(k in SHOWN)))
for k, v in P.items():
    if is_person(v) and C(k) in used:
        db.execute('INSERT INTO player_profiles VALUES(?,?,?,?)', ('cuescore' if k in CSIDS else 'tournamentapp' if TA_P <= int(k) < 9_000_000_000 else 'epbf' if EP_P <= int(k) < TA_T else 'wnt' if WN_P <= int(k) < EP_T else 'nuliga' if BB_P <= int(k) < WN_T else 'veveto' if HV_P <= int(k) < BB_T else 'scoretrek' if ST_P <= int(k) < ST_P + 1_000_000_000 else 'other', k, int(C(k)), f'{s(v[1])} {s(v[0])}'))
for t in T.values():
    src = SOURCE.get(t['id'], 'tournamentservice')
    url = f"https://cuescore.com/tournament/x/{t['id']}" if src == 'cuescore' else EXT_URL.get(t['id']) or f"https://www.tournamentapp.de/kalender-details.php?tID={t['id'] - TA_T}"
    excl = t['excl'] or ('duplicate of ' + str(DUPLICATE_ENTRIES[t['id']]) if t['id'] in DUPLICATE_ENTRIES and not any(m['tid'] == t['id'] for m in matches) else None)
    db.execute('INSERT INTO tournaments VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (t['id'], src, str(t['id']), t['name'], t['date'].isoformat(),
               t['city'], t['club'], t['game'], t['disc'], t['org'], excl, url))
for m in matches:
    msrc = SOURCE.get(m['tid'], 'tournamentservice')
    db.execute('INSERT INTO matches VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (m['mid'], msrc, str(m['mid'] - CS_MATCH_OFFSET if msrc == 'cuescore' else m['mid']), m['tid'], m['date'].isoformat(), m['stage'],
               int(m['race']) if str(m['race']).isdigit() else None, int(m['a']), int(m['b']), m['sa'], m['sb'], T[m['tid']]['game']))
db.commit()
print('tournaments total', len(T), 'used', len({m['tid'] for m in matches}))
print('excluded', collections.Counter(t['excl'] for t in T.values()))
print('dropped odd long matches', sum(odd_long.values()), 'in', len(odd_long), 'events')
print('raw valid', len(raw_valid), 'final matches', len(matches), 'players', len(used))
print('shown players', sum(1 for k in used if k in SHOWN), 'background (foreign) players', sum(1 for k in used if k not in SHOWN))
print('merged profiles', sum(1 for k in canon if canon[k] != k))
print('games', collections.Counter(T[m['tid']]['game'] for m in matches))
