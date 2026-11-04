"""German Pool Rating: collect Hessen league results from VeVeTo (hpbv-veveto.de) into data/hessen_veveto.json.gz.

Python version of the browser collection of 3-4 Nov 2026 (same file format). Everything is stored raw; build_db.py decides
what counts (8/9/10-ball singles; 14.1 and no-shows are skipped there).
- Leagues:  /api/1/season/{s}/leagues/public            (season ids: 1 = 2022/23, 3 = 2023/24, 5 = 2024/25, 7 = 2025/26, 9 = 2026/27;
                                                          the even ids are snooker seasons, stored too, they have no pool games)
- Matches:  /api/season/{s}/{league}/league/leg/{1|2}/matches/public   (id, number, date, teams, status "Gespielt")
- Report:   /spielart/1/spielbetrieb/1/saison/{s}/spielergebnisse/{id}/anzeige   (HTML; its text is stored)
The site allows 20 requests a minute (x-ratelimit-limit 20), so requests are spaced 3.1 seconds apart.
Daily runs: the newest seasons are listed again; reports not stored yet, and reports of the last DAYS days, are read.
robots.txt of the site allows everything (checked 3 Nov 2026).

Format: leagues [{s, id, number, name, type}], matches [{s, league, id, number, date, status, home, guest, hr, gr}],
        details {match id: report text}
"""
import json, os, re, sys, gzip, time, datetime
import requests
from bs4 import BeautifulSoup

FILE = 'data/hessen_veveto.json.gz'
BASE = 'https://hpbv-veveto.de'
DAYS = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 14
GAP = 3.1
S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating updater)', 'Accept-Language': 'de-DE,de;q=0.9'})
_last = [0.0]

def get(path, js=False):
    for a in range(6):
        w = _last[0] + GAP - time.time()
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        try:
            r = S.get(BASE + path, timeout=60, headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'} if js else {})
        except requests.RequestException:
            time.sleep(10); continue
        if r.status_code == 429: time.sleep(30 * (a + 1)); continue
        if r.status_code != 200: return None
        return r.json() if js else r.text
    return None

def report_text(html):
    soup = BeautifulSoup(html, 'lxml')
    c = soup.select_one('.content-body') or soup.body
    t = re.sub(r'[ \t]+', ' ', c.get_text()) if c else ''
    return re.sub(r'\s*\n\s*', '\n', t).strip()

D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else dict(leagues=[], matches=[], details={})
D.setdefault('details', {})
known = sorted({x['s'] for x in D['leagues']}) or [1]
# newest seasons: the last two pool seasons we know, plus up to four ids above (a new season appears in late summer)
probe = sorted(set([s for s in known if s >= max(known) - 2] + list(range(max(known) + 1, max(known) + 5))))
fresh_m = []
for s in probe:
    j = get(f'/api/1/season/{s}/leagues/public?draw=1&start=0&length=200', js=True)
    if not j or not j.get('data'): continue
    for L in j['data']:
        if not any(x['s'] == s and x['id'] == L['id'] for x in D['leagues']):
            D['leagues'].append(dict(s=s, id=L['id'], number=L.get('number'), name=L.get('name'),
                                     type=(L.get('league_type') or {}).get('name')))
        for leg in (1, 2):
            m = get(f'/api/season/{s}/{L["id"]}/league/leg/{leg}/matches/public?draw=1&start=0&length=500', js=True)
            for x in (m or {}).get('data') or []:
                hw = x.get('team_winner_id') == x.get('home_team_id')
                fresh_m.append(dict(s=s, league=L['id'], id=x['id'], number=x.get('number'), date=x.get('date'), status=x.get('status'),
                                    home=x.get('home_team'), guest=x.get('guest_team'),
                                    hr=x.get('team_winner_result') if hw else x.get('team_loser_result'),
                                    gr=x.get('team_loser_result') if hw else x.get('team_winner_result')))
if fresh_m:
    ids = {m['id'] for m in fresh_m}
    D['matches'] = [m for m in D['matches'] if m['id'] not in ids] + fresh_m

def mdate(m):
    try: return datetime.datetime.strptime((m.get('date') or '')[:10], '%d.%m.%Y').date()
    except ValueError: return None
cut = datetime.date.today() - datetime.timedelta(days=DAYS)
todo = [m for m in D['matches'] if m.get('status') == 'Gespielt'
        and (str(m['id']) not in D['details'] or (mdate(m) and mdate(m) >= cut))]
read = 0
for m in todo:
    h = get(f"/spielart/1/spielbetrieb/1/saison/{m['s']}/spielergebnisse/{m['id']}/anzeige")
    if h: D['details'][str(m['id'])] = report_text(h); read += 1
print(f'VeVeTo Hessen: seasons {probe}, matches listed {len(fresh_m)}, reports read {read}/{len(todo)}, stored {len(D["details"])}')

D['collected'] = datetime.datetime.utcnow().isoformat() + 'Z'; D['source'] = 'hpbv-veveto.de'
with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
os.replace(FILE + '.tmp', FILE)
