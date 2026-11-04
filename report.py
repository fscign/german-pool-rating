"""Compare the previous site data with the new one and write a short update report (report.txt)."""
import json, sys, difflib, unicodedata, re
import os
old = json.load(open(sys.argv[1], encoding='utf-8')) if os.path.exists(sys.argv[1]) else {'players': [], 'tournaments': []}
new = json.load(open('site/data.json', encoding='utf-8'))
def n_matches(path):
    try: return len(json.load(open(path, encoding='utf-8'))['matches'])
    except Exception: return 0
old['matches'] = [0] * n_matches(sys.argv[2] if len(sys.argv) > 2 else 'previous_matches.json'); new['matches'] = [0] * n_matches('site/matches.json')
def norm(t):
    t = unicodedata.normalize('NFKD', t.lower()); return re.sub(r'[^a-z ]', '', ''.join(c for c in t if not unicodedata.combining(c)))
shown = lambda p: len(p) < 13 or p[12]
po = {p[0]: p for p in old['players']}; pn = {p[0]: p for p in new['players'] if shown(p)}
to = {t[0] for t in old['tournaments']}
lines = []
log = open('update_log.txt').read().strip() if __import__('os').path.exists('update_log.txt') else ''
if log: lines.append(log)
newt = [t for t in new['tournaments'] if t[0] not in to]
lines.append(f"Counted matches: {len(old['matches'])} -> {len(new['matches'])}; tournaments: {len(old['tournaments'])} -> {len(new['tournaments'])}; players: {len(old['players'])} -> {len(new['players'])}")
if newt:
    lines.append('New tournaments in the rating:')
    for t in sorted(newt, key=lambda t: t[2]): lines.append(f"  {t[2]}  {t[1]}  ({t[6]})")
newp = [p for p in new['players'] if p[0] not in po and shown(p)]
newf = [p for p in new['players'] if p[0] not in po and not shown(p)]
if newp:
    lines.append('New players (check whether any of them is an existing player under another spelling):')
    names = {norm(p[1] + ' ' + p[2]): p for p in old['players'] if shown(p)}
    for p in newp:
        close = difflib.get_close_matches(norm(p[1] + ' ' + p[2]), list(names), n=2, cutoff=0.75)
        hint = '; maybe ' + ', '.join(f"{names[c][1]} {names[c][2]}" for c in close) if close else ''
        lines.append(f"  {p[1]} {p[2]} ({p[7]} matches){hint}")
if newf: lines.append(f'New foreign players rated in the background: {len(newf)}')
moves = sorted(((pn[i][5] - po[i][5], pn[i]) for i in pn if i in po), key=lambda x: -abs(x[0]))[:5]
if moves and abs(moves[0][0]) >= 1:
    lines.append('Biggest rating changes: ' + ', '.join(f"{p[1]} {p[2]} {d:+.0f}" for d, p in moves))
open('report.txt', 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
