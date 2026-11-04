"""German Pool Rating: collect Bavarian pool results from nuLiga (bbv-billard.liga.nu) into data/bbv_nuliga_data.json.gz.

Python version of the browser collection of 3 Nov 2026 (same file format). Everything is stored raw; build_db.py decides what counts.
- Leagues: leaguePage?championship=BBV Pool YY/YY -> groupPage (meetings) -> groupMeetingReport (single games, nuLiga player ids).
  Single games are public from season 2025/26; older seasons only have team scores.
- Championships: tournamentCalendar (month pages) -> tournamentCalendarDetail -> tournamentMatchesReport (matches, names only).
Daily runs re-read the current and previous season's meeting lists and read reports not stored yet (plus the last DAYS days),
and re-read the calendar of the last few months. robots.txt of the site allows these pages (checked 3 Nov 2026).

Format:
  leagues: [{s, g, name}]   meetings: [{s, g, m (report id or null), c (row cells)}]
  reports: {meeting id: {head, rows: [[cell or [name, person id, club id], ...]]}}
  tcal: [{id, mo, c}]   tdet: {tournament id: {head, text, rows: [{c, comp?}]}}   tmatches: {competition id: {t, rows}}
"""
import json, os, re, sys, gzip, time, datetime
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, quote

FILE = 'data/bbv_nuliga_data.json.gz'
BASE = 'https://bbv-billard.liga.nu/cgi-bin/WebObjects/nuLigaBILLARDDE.woa/wa/'
DAYS = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 21
TODAY = datetime.date.today()
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating updater)', 'Accept-Language': 'de-DE,de;q=0.9'})

def get(path):
    for i in range(4):
        try:
            r = S.get(BASE + path, timeout=60)
            if r.ok: return BeautifulSoup(r.text, 'lxml')
        except requests.RequestException: pass
        time.sleep(2 * (i + 1))
    return None

def q(href, key):
    return (parse_qs(urlparse(href).query).get(key) or [None])[0]

def txt(el): return re.sub(r'\s+', ' ', el.get_text(' ', strip=True)).strip()

def cells(tr):
    out = []
    for c in tr.find_all(['td', 'th'], recursive=False):
        a = c.find('a', href=re.compile('playerPortrait'))
        out.append([txt(c), q(a['href'], 'person'), q(a['href'], 'club')] if a else txt(c))
    return out

def rows(doc):
    t = doc.select_one('table.result-set')
    return [tr for tr in t.find_all('tr')] if t else []

def head(doc): return ' // '.join(txt(x) for x in doc.find_all(['h1', 'h2']))

def season_of(d):   # season starts in July
    y = d.year if d.month >= 7 else d.year - 1
    return f'{y % 100:02d}/{(y + 1) % 100:02d}'

old = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else {}
D = {k: old.get(k, v) for k, v in dict(leagues=[], meetings=[], reports={}, tcal=[], tdet={}, tmatches={}, err=[]).items()}
D['err'] = []
seasons = sorted({season_of(TODAY), season_of(TODAY - datetime.timedelta(days=200))})

# ---------- leagues ----------
for s in seasons:
    doc = get('leaguePage?championship=' + quote('BBV Pool ' + s))
    if not doc: D['err'].append('league ' + s); continue
    for a in doc.find_all('a', href=re.compile('groupPage')):
        g = q(a['href'], 'group')
        if g and not any(x['s'] == s and x['g'] == g for x in D['leagues']): D['leagues'].append(dict(s=s, g=g, name=txt(a)))

def meetings(L):
    out = []
    for t in ('vorrunde', 'rueckrunde'):
        doc = get(f"groupPage?displayTyp={t}&displayDetail=meetings&championship={quote('BBV Pool ' + L['s'])}&group={L['g']}")
        if not doc: D['err'].append('group ' + L['g']); continue
        for tr in rows(doc):
            c = [txt(x) for x in tr.find_all(['td', 'th'], recursive=False)]
            a = tr.find('a', href=re.compile('groupMeetingReport'))
            if len(c) > 3: out.append(dict(s=L['s'], g=L['g'], m=q(a['href'], 'meeting') if a else None, c=c))
    return out
cur = [L for L in D['leagues'] if L['s'] in seasons]
with ThreadPoolExecutor(4) as ex: fresh = [m for lst in ex.map(meetings, cur) for m in lst]
if fresh:
    keep = [m for m in D['meetings'] if m['s'] not in seasons]
    seen = set(); D['meetings'] = keep
    for m in fresh:
        if m['m'] and m['m'] in seen: continue
        if m['m']: seen.add(m['m'])
        D['meetings'].append(m)

def mdate(c):
    for x in c:
        if re.fullmatch(r'\d\d\.\d\d\.\d{4}', x): return datetime.datetime.strptime(x, '%d.%m.%Y').date()
    return None
todo, last = [], None
for m in D['meetings']:
    last = mdate(m['c']) or last
    if m['m'] and m['s'] in seasons and (m['m'] not in D['reports'] or (last and (TODAY - last).days <= DAYS)): todo.append(m)
def report(m):
    doc = get(f"groupMeetingReport?meeting={m['m']}&championship={quote('BBV Pool ' + m['s'])}&group={m['g']}")
    if not doc: D['err'].append('report ' + m['m']); return
    D['reports'][m['m']] = dict(head=head(doc), rows=[cells(tr) for tr in rows(doc)])
with ThreadPoolExecutor(5) as ex: list(ex.map(report, todo))
print('league reports read', len(todo), 'stored', len(D['reports']))

# ---------- championships ----------
months = sorted({(TODAY - datetime.timedelta(days=k)).replace(day=1).isoformat() for k in range(0, 125, 10)})
ids = {t['id'] for t in D['tcal']}
newcal = []
for mo in months:
    doc = get(f'tournamentCalendar?federation=BBV&seasonType=REGULAR&date={mo}')
    if not doc: D['err'].append('calendar ' + mo); continue
    for tr in rows(doc):
        a = tr.find('a', href=re.compile('tournamentCalendarDetail'))
        if not a: continue
        tid = q(a['href'], 'tournament')
        if tid in ids: continue
        ids.add(tid); t = dict(id=tid, mo=mo, c=[txt(x) for x in tr.find_all(['td', 'th'], recursive=False)])
        D['tcal'].append(t); newcal.append(t)
recent = {t['id'] for t in D['tcal'] if t['mo'] >= months[0]}
comps = []
def detail(tid):
    doc = get(f'tournamentCalendarDetail?tournament={tid}&federation=BBV&seasonType=REGULAR')
    if not doc: D['err'].append('tournament ' + tid); return
    rs = []
    for tr in rows(doc):
        a = tr.find('a', href=re.compile('tournamentMatchesReport'))
        c = [txt(x) for x in tr.find_all(['td', 'th'], recursive=False)]
        if a: comp = q(a['href'], 'competition'); comps.append((tid, comp)); rs.append(dict(c=c, comp=comp))
        else: rs.append(dict(c=c))
    content = doc.select_one('#content') or doc.body
    D['tdet'][tid] = dict(head=head(doc), text=txt(content)[:1500], rows=rs)
with ThreadPoolExecutor(4) as ex: list(ex.map(detail, sorted(recent)))
def tmatch(tc):
    tid, comp = tc
    doc = get(f'tournamentMatchesReport?federation=BBV&seasonType=REGULAR&competition={comp}')
    if not doc: D['err'].append('competition ' + comp); return
    D['tmatches'][comp] = dict(t=tid, rows=[cells(tr) for tr in rows(doc)])
with ThreadPoolExecutor(4) as ex: list(ex.map(tmatch, comps))
print('calendar months', len(months), 'new tournaments', len(newcal), 'competitions read', len(comps), 'errors', len(D['err']))

D = dict(collected=datetime.datetime.utcnow().isoformat() + 'Z', source='bbv-billard.liga.nu', **D)
with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
os.replace(FILE + '.tmp', FILE)
