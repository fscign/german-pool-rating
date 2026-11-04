"""German Pool Rating: collect tournamentapp.de results into data/ta_raw.json.

Python version of the browser collection of 3 Nov 2026. Everything is stored (all disciplines and categories,
unfinished matches marked); build_db.py decides what counts.
- Lists: turnierergebnisse.php?s=&saison=YY (one page per season, 2021 onwards).
- Tournament: kalender-details.php?s=&tID=<id> (lists the result tabs), results: kalender-details.php?s=&tID=<id>&rub=rs&tabID=<tab>.
Re-reads tournaments of the last DAYS days and any still marked LIVE; reads new ones; keeps everything else.

Format (data/ta_raw.json):
  tournaments: [id, name, date dd.mm.yy, kind (WT/OP/FREI), discipline, category, city, status, date text]
  matches: [tournament id, match id, code, game ('' = tournament game), sid A, sid B, score A, score B, unix time, tab, finished 1/0]
  players: sid -> [name ("Surname Firstname"), flag]
"""
import json, os, re, sys, time, datetime
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

FILE = 'data/ta_raw.json'
BASE = 'https://www.tournamentapp.de/'
DAYS = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 60
TODAY = datetime.date.today()
FIRST_SEASON = 21
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating updater)', 'Accept-Language': 'de-DE,de;q=0.9'})
MON = {'januar': 1, 'februar': 2, 'märz': 3, 'maerz': 3, 'april': 4, 'mai': 5, 'juni': 6, 'juli': 7, 'august': 8,
       'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12}

def get(path):
    for i in range(4):
        try:
            r = S.get(BASE + path, timeout=60); r.raise_for_status(); return r.text
        except Exception:
            if i == 3: raise
            time.sleep(4 * (i + 1))

def soup(h): return BeautifulSoup(h, 'html.parser')
def txt(el): return re.sub(r'\s+', ' ', el.get_text()).strip() if el is not None else ''

def tdate(s):
    """'02. November 2026, 20:00 Uhr' | '27. - 30. Dezember 2021, 14:00 Uhr' | '30. Juni - 02. Juli 2023' -> (d, m, y)"""
    m = re.match(r'^(\d{1,2})\.\s*(?:([A-Za-zäöüÄÖÜ]+)\s*)?(?:-\s*\d{1,2}\.\s*(?:([A-Za-zäöüÄÖÜ]+)\s*)?)?(\d{4})', s or '')
    if not m: return None
    mon = MON.get((m.group(2) or m.group(3) or '').lower())
    return (int(m.group(1)), mon, int(m.group(4))) if mon else None

def season_list(yy):
    out = []
    for a in soup(get(f'turnierergebnisse.php?s=&saison={yy}')).select('article[onclick]'):
        m = re.search(r'tID=(\d+)', a.get('onclick') or '')
        if not m: continue
        badges = [txt(b) for b in a.select('.badge-secondary')]
        ti = a.select_one('.post-classic-title')
        name = (ti.contents[0].strip() if ti is not None and ti.contents and isinstance(ti.contents[0], str) else txt(ti)).strip()
        city = txt(ti.select_one('span')) if ti is not None else ''
        st = a.select_one('[class*=badge-widget]')
        dt = a.select_one('.col-sm-8 span')
        out.append(dict(tid=int(m.group(1)), date=txt(dt), kind=(badges + [''])[0], disc=(badges + ['', ''])[1],
                        cat=(badges + ['', '', ''])[2], name=name, city=city, status=txt(st)))
    return out

def parse_results(h, tab, dt):
    out, players = [], {}
    for a in soup(h).select('a[href*="fancy-begegnungskarte"]'):
        tr = a.find_parent('tr')
        if tr is None: continue
        mid = re.search(r'[?&]id=(\d+)', a.get('href') or '')
        tds = tr.find_all('td', recursive=False)
        pl = []
        for x in tr.select('a.link_spielername_resultate'):
            sid = re.search(r'sid=(\d+)', x.get('href') or '')
            pl.append((int(sid.group(1)) if sid else 0, txt(x)))
        imgs = [(i.get('src') or '').split('/')[-1].split('?')[0] for i in tr.find_all('img')]
        flags = [s[:-4] for s in imgs if s.endswith('.jpg')]
        game = next((s[:-4] for s in imgs if s.endswith('.png')), '')
        sc = [txt(x) for x in tr.select('center span')]
        if len(pl) < 2 or not mid: continue
        when = txt(tds[1]) if len(tds) > 1 else ''
        w = re.match(r'^(\d{2})\.(\d{2})\s+(\d{2}):(\d{2})', when)
        d, mo, y = dt
        if w:
            yy = y + (1 if int(w.group(2)) < mo - 6 else 0)
            ts = int(datetime.datetime(yy, int(w.group(2)), int(w.group(1)), int(w.group(3)), int(w.group(4)), tzinfo=datetime.timezone.utc).timestamp())
        else:
            ts = int(datetime.datetime(y, mo, d, 12, tzinfo=datetime.timezone.utc).timestamp())
        out.append([0, int(mid.group(1)), txt(a), '' if game == '0' else game, pl[0][0], pl[1][0],
                    sc[0] if sc else '', sc[1] if len(sc) > 1 else '', ts, tab, 1 if tr.select_one('.fa-check-circle') else 0])
        for (sid, name), fl in zip(pl[:2], (flags + ['', ''])[:2]):
            if sid: players[str(sid)] = [name, fl]
    return out, players

def read_tournament(t):
    dt = tdate(t['date'])
    if not dt: return t, None
    h = get(f"kalender-details.php?s=&tID={t['tid']}")
    tabs = list(dict.fromkeys(re.findall(r'rub=rs&(?:amp;)?tabID=(\d+)', h))) or list(dict.fromkeys(re.findall(r'tabID=(\d+)', h)))
    ms, pl = [], {}
    for tab in tabs:
        rows, p = parse_results(get(f"kalender-details.php?s=&tID={t['tid']}&rub=rs&tabID={tab}"), int(tab), dt)
        for r in rows: r[0] = t['tid']
        ms += rows; pl.update(p)
    return t, (dt, ms, pl)

if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    D = json.load(open(FILE, encoding='utf-8')) if os.path.exists(FILE) else {'tournaments': [], 'matches': [], 'players': {}}
    have = {t[0]: t for t in D['tournaments']}
    yy_now = TODAY.year % 100
    seasons = range(FIRST_SEASON, yy_now + 1) if not have else range(yy_now - 1, yy_now + 1)   # first run: all seasons
    listed = []
    for yy in seasons: listed += season_list(yy); time.sleep(0.5)
    cut = TODAY - datetime.timedelta(days=DAYS)
    todo = []
    for t in listed:
        dt = tdate(t['date'])
        recent = dt and datetime.date(dt[2], dt[1], dt[0]) >= cut
        old = have.get(t['tid'])
        if old is None or recent or 'LIVE' in (t['status'] or '').upper() or (len(old) > 7 and 'LIVE' in (old[7] or '').upper()):
            if 'abgesagt' not in (t['status'] or '').lower(): todo.append(t)
    print('tournaments listed', len(listed), 'to read', len(todo), flush=True)
    with ThreadPoolExecutor(3) as ex: res = list(ex.map(read_tournament, todo))
    new = upd = 0
    for t, r in res:
        if not r: continue
        dt, ms, pl = r
        row = [t['tid'], t['name'], f'{dt[0]:02d}.{dt[1]:02d}.{str(dt[2])[2:]}', t['kind'], t['disc'], t['cat'], t['city'], t['status'], t['date']]
        D['matches'] = [m for m in D['matches'] if m[0] != t['tid']] + ms
        D['tournaments'] = [x for x in D['tournaments'] if x[0] != t['tid']] + [row]
        D['players'].update(pl)
        if t['tid'] in have: upd += 1
        else: new += 1
    json.dump(D, open(FILE, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    msg = f'tournamentapp.de: {new} new tournaments, {upd} re-read; total {len(D["tournaments"])} tournaments, {len(D["matches"])} matches'
    print(msg); open('update_log.txt', 'a').write(msg + '\n')
