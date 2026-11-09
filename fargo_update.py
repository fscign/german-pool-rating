"""German Pool Rating: weekly FargoRate refresh for foreign players (data/fargo_foreign.json).

Looks up every foreign (not shown) player with 10+ counted matches in de_pool.sqlite on FargoRate's public search
(dashboard.fargorate.com/api/indexsearch) and keeps the best-established profile with exactly the same name.
Run after build_db.py. If FargoRate cannot be reached, the old file is kept.
Format: {"players": {name: [rating, robustness, readableId, location, two established profiles with this name 1/0]}}
"""
import json, sqlite3, time, unicodedata, re, os, datetime
import requests
from concurrent.futures import ThreadPoolExecutor

FILE = 'data/fargo_foreign.json'
S = requests.Session(); S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating updater)'})

def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower().replace('ø', 'o').replace('ł', 'l').replace('ß', 'ss')
    return ' '.join(sorted(t for t in re.sub(r'[^a-z ]', ' ', s).split() if t))

db = sqlite3.connect('de_pool.sqlite')
# only foreign players who played a German (9 Nov 2026): since every match counts, there are ~15,000 foreign players with
# 10+ matches; those who never met a German are rated from their own history and are not looked up
names = [r[0] for r in db.execute('''SELECT TRIM(p.first_name || ' ' || p.last_name) FROM players p
    JOIN matches m ON p.id IN (m.player_a, m.player_b) WHERE p.shown = 0 GROUP BY p.id HAVING COUNT(*) >= 10
    AND p.id IN (SELECT m2.player_a FROM matches m2 JOIN players q ON q.id = m2.player_b WHERE q.shown = 1
                 UNION SELECT m2.player_b FROM matches m2 JOIN players q ON q.id = m2.player_a WHERE q.shown = 1)''')]

def look(n):
    for i in range(3):
        try:
            j = S.get('https://dashboard.fargorate.com/api/indexsearch', params={'q': n}, timeout=30).json()
            c = [x for x in j.get('value') or [] if norm((x.get('firstName') or x.get('name') or '') + ' ' + (x.get('lastName') or '')) == norm(n)]
            c.sort(key=lambda x: -int(x.get('robustness') or 0))
            if not c: return n, None
            amb = 1 if len(c) > 1 and int(c[1].get('robustness') or 0) >= 200 else 0
            x = c[0]
            return n, [int(x.get('rating') or 0), int(x.get('robustness') or 0), x.get('readableId') or '', x.get('location') or '', amb]
        except Exception:
            time.sleep(3)
    return n, 'error'

try:
    S.get('https://dashboard.fargorate.com/api/indexsearch', params={'q': 'Filler'}, timeout=30).raise_for_status()
except Exception as e:
    print('FargoRate not reachable, keeping the old file:', e); raise SystemExit(0)
with ThreadPoolExecutor(4) as ex: res = list(ex.map(look, names))
errors = sum(1 for _, r in res if r == 'error')
old = json.load(open(FILE, encoding='utf-8'))['players'] if os.path.exists(FILE) else {}
players = dict(old)
for n, r in res:
    if r == 'error': continue
    if r: players[n] = r
    else: players.pop(n, None)
json.dump({'collected': datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z', 'source': 'https://dashboard.fargorate.com/api/indexsearch',
           'format': ['rating', 'robustness', 'readableId', 'location', 'two established profiles with this name (1/0)'], 'players': players},
          open(FILE, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
msg = f'FargoRate: {len(names)} foreign players looked up, {sum(1 for _, r in res if r and r != "error")} found, {errors} errors'
print(msg); open('update_log.txt', 'a').write(msg + '\n')
