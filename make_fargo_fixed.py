"""fargo_foreign.json (name -> FargoRate) -> fargo_fixed.json (player id -> [rating, robustness, readableId]).
Foreign players (not shown) with 200+ FargoRate games and only one established profile with that name get a fixed rating (decided 3 Nov 2026)."""
import json, sqlite3
F = json.load(open('data/fargo_foreign.json', encoding='utf-8'))['players']
db = sqlite3.connect('de_pool.sqlite')
names = {}
for pid, fn, ln in db.execute('SELECT id, first_name, last_name FROM players WHERE shown = 0'):
    names.setdefault(f'{fn} {ln}'.strip(), []).append(pid)
fixed, ref = {}, {}
for name, (rating, rob, rid, loc, amb) in F.items():
    for pid in names.get(name, []):
        ref[pid] = [rating, rob, rid]
        if rob >= 200 and not amb and len(names[name]) == 1: fixed[pid] = [rating, rob, rid]
json.dump(fixed, open('data/fargo_fixed.json', 'w'))
json.dump(ref, open('data/fargo_ref.json', 'w'))
print('found in database', len(ref), 'fixed (200+ games)', len(fixed))
