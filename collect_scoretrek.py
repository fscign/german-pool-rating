"""German Pool Rating: collect Score Trek Battle results (battle.score-trek.de) into data/scoretrek_raw.json.gz.

Added 6 Nov 2026. Score Trek Battle is a tournament and league app used mostly by clubs in North Rhine-Westphalia
(some Bavaria, Saarland, Belgium/Eupen, Austria). Everything is stored raw; build_db.py decides what counts.
- The list of tournaments and league match days comes from the public sitemap (https://battle.score-trek.de/sitemap.xml,
  robots.txt allows these pages, checked 6 Nov 2026).
- Each page loads its data from the site's own JSON API with plain POST requests (no login needed), the same calls the
  page makes for every visitor:
    tournaments: /v2/battle/tournament/minimal, /rounds, /teams   {"id": "<tournament id>"}
    league match days: /v2/battle/league/matchday/details          {"id": "<match day id>"}
- Players have their own Score Trek ids (player.id); unlinked entries have only a name.
Daily runs re-read everything that is not finalized yet and everything from the last DAYS days; finished events are kept.

Format: {"tournaments": {id: {"t": tournament, "rounds": [...], "teams": [...], "read": "YYYY-MM-DD"}},
         "matchdays":   {id: {"md": matchday, "rounds": [...], "teams": [...], "read": "YYYY-MM-DD"}}}
Games and teams are slimmed to the fields below (scores, race, game type, handicap, players, dates).
"""
import json, os, re, sys, gzip, time, datetime
import requests

FILE = 'data/scoretrek_raw.json.gz'
API = 'https://api.score-trek.de/v2/battle'
SITEMAP = 'https://battle.score-trek.de/sitemap.xml'
DAYS = int(sys.argv[sys.argv.index('--days') + 1]) if '--days' in sys.argv else 14
LIMIT = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 0    # for testing: read at most N new items
PAUSE = 0.7
TODAY = datetime.date.today()
S = requests.Session()
S.headers.update({'User-Agent': 'Mozilla/5.0 (pool rating updater)', 'Content-Type': 'application/json',
                  'Accept': 'application/json', 'X-Client-Language': 'de-DE'})

GAME_KEYS = ['id', 'roundId', 'roundIndex', 'groupId', 'groupIndex', 'number', 'type', 'gameType', 'gameTarget', 'status',
             'team1', 'team2', 'result1', 'result2', 'handicap1', 'handicap2', 'winner', 'loser', 'isTie', 'tableType',
             'dateTimeStartTimestamp', 'dateTimeEndTimestamp', 'modifiedTimestamp']
T_KEYS = ['id', 'clubId', 'clubName', 'seriesId', 'status', 'statusInfo', 'isFinalized', 'isCancelled', 'isPublic', 'title',
          'locationCity', 'locationZip', 'timeZone', 'dateTimeTournamentDate', 'dateTimeTournamentTimestamp', 'gamesTotal',
          'gamesDone', 'participantsCount', 'teamsCount', 'officialScheme', 'presetId']

stats = {'requests': 0, 'errors': 0}
def post(path, body):
    for i in range(4):
        try:
            stats['requests'] += 1
            r = S.post(API + path, data=json.dumps(body), timeout=60)
            if r.status_code == 429: time.sleep(30 * (i + 1)); continue
            if r.ok:
                j = r.json()
                if j.get('success') and isinstance(j.get('data'), dict): return j['data']
                return None   # the API answered but has no such item (deleted / private)
        except (requests.RequestException, ValueError): pass
        time.sleep(3 * (i + 1))
    stats['errors'] += 1
    raise RuntimeError(f'Score Trek API not reachable: {path} {body}')

def pick(o, keys): return {k: o[k] for k in keys if k in o}

def games_of(x):
    """All game objects anywhere inside x (rounds -> groups -> games, or rounds -> games as a list or dict)."""
    out = []
    if isinstance(x, dict):
        if 'team1' in x and 'result1' in x: return [pick(x, GAME_KEYS)]
        for v in x.values(): out += games_of(v)
    elif isinstance(x, list):
        for v in x: out += games_of(v)
    return out

def slim_player(p):
    if not isinstance(p, dict): return None
    c = p.get('club') or {}
    return {'id': p.get('id'), 'name': p.get('name'), 'club': c.get('official_name') or c.get('name'), 'city': c.get('city'), 'country': c.get('country')}

def slim_teams(teams):
    if isinstance(teams, dict): teams = list(teams.values())
    out = []
    for t in teams or []:
        if not isinstance(t, dict): continue
        out.append({'id': t.get('id'), 'name': t.get('name'), 'rank': t.get('rank'), 'handicap': t.get('handicap'),
                    'surrendered': t.get('isSurrendered'), 'disqualified': t.get('isDisqualified'),
                    'participants': [{'playerId': q.get('playerId'), 'fullName': q.get('fullName'), 'player': slim_player(q.get('player'))}
                                     for q in (t.get('participants') or []) if isinstance(q, dict)]})
    return out

def sitemap_ids():
    r = None
    for i in range(4):
        try:
            r = S.get(SITEMAP, timeout=60, headers={'Accept': 'application/xml,text/xml,*/*'})
            if r.ok: break
        except requests.RequestException: pass
        time.sleep(3 * (i + 1))
    if not r or not r.ok: raise RuntimeError('Score Trek sitemap not reachable')
    locs = re.findall(r'<loc>([^<]+)</loc>', r.text)
    tours = [u.rsplit('/', 1)[1] for u in locs if '/tournament/live/' in u]
    mdays = [u.rsplit('/', 1)[1] for u in locs if '/league/matchday/' in u]
    return tours, mdays

def recent(day):
    try: return datetime.date.fromisoformat(day[:10]) >= TODAY - datetime.timedelta(days=DAYS)
    except Exception: return True

D = json.load(gzip.open(FILE, 'rt', encoding='utf-8')) if os.path.exists(FILE) else {}
D.setdefault('tournaments', {}); D.setdefault('matchdays', {})
tours, mdays = sitemap_ids()
print(f'sitemap: {len(tours)} tournaments, {len(mdays)} league match days')
new = 0

def save():
    with gzip.open(FILE + '.tmp', 'wt', encoding='utf-8') as f: json.dump(D, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(FILE + '.tmp', FILE)

def guard(fn, *a):
    try: return fn(*a)
    except RuntimeError as e:
        print(e)
        if stats['errors'] >= 5:
            save(); print('too many errors, stopping (data read so far is saved)'); sys.exit(1)

def read_tournament(tid):
    m = post('/tournament/minimal', {'id': tid}); time.sleep(PAUSE)
    if not m or not m.get('tournament'): return False
    t = pick(m['tournament'], T_KEYS)
    t['clubCountry'] = (m['tournament'].get('club') or {}).get('country')
    rounds = teams = []
    if t.get('status') in ('running', 'done') or t.get('isFinalized'):
        r = post('/tournament/rounds', {'id': tid}) or {}; time.sleep(PAUSE)
        tm = post('/tournament/teams', {'id': tid}) or {}; time.sleep(PAUSE)
        rounds, teams = games_of(r.get('rounds')), slim_teams(tm.get('teams'))
    D['tournaments'][tid] = {'t': t, 'games': rounds, 'teams': teams, 'read': TODAY.isoformat()}
    return True

def read_matchday(mid):
    x = post('/league/matchday/details', {'id': mid}); time.sleep(PAUSE)
    if not x or not x.get('matchday'): return False
    md = {k: v for k, v in x['matchday'].items() if not isinstance(v, (dict, list))}
    md['clubCountry'] = (x['matchday'].get('club') or {}).get('country')
    D['matchdays'][mid] = {'md': md, 'games': games_of(x.get('rounds')), 'teams': slim_teams(x.get('teams')), 'read': TODAY.isoformat()}
    return True

for tid in tours:
    old = D['tournaments'].get(tid)
    if old and old['t'].get('isFinalized') and not recent(old['t'].get('dateTimeTournamentDate') or ''): continue
    if LIMIT and new >= LIMIT: break
    if not guard(read_tournament, tid): continue
    new += 1
    if new % 50 == 0: save(); print(f'  {new} read')

for mid in mdays:
    old = D['matchdays'].get(mid)
    if old and old['md'].get('isFinalized') and not recent(old['md'].get('dateTimeMatchdayDate') or ''): continue
    if LIMIT and new >= LIMIT: break
    if not guard(read_matchday, mid): continue
    new += 1
    if new % 50 == 0: save(); print(f'  {new} read')

save()
ng = sum(len(v['games']) for v in D['tournaments'].values()) + sum(len(v['games']) for v in D['matchdays'].values())
print(f"read now: {new}; stored: {len(D['tournaments'])} tournaments, {len(D['matchdays'])} match days, {ng} games; "
      f"requests {stats['requests']}, errors {stats['errors']}")
