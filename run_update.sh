#!/bin/sh
# Daily update of the German Pool Rating: collect -> build -> rate -> export -> report.txt
set -e
cd "$(dirname "$0")"
rm -f update_log.txt
cp site/data.json previous_data.json 2>/dev/null || true
cp site/matches.json previous_matches.json 2>/dev/null || true
python3 -I collect_cuescore.py
python3 -I collect_team.py
python3 -I collect_tournamentapp.py || echo "tournamentapp.de could not be read this time (kept the old data)" >> update_log.txt
python3 -I collect_nuliga.py || echo "nuLiga Bavaria could not be read this time (kept the old data)" >> update_log.txt
python3 -I collect_veveto.py || echo "VeVeTo Hessen could not be read this time (kept the old data)" >> update_log.txt
python3 -I build_db.py > build_log.txt 2>&1
python3 -I make_fargo_fixed.py
python3 -I rate.py > rate_log.txt
python3 -I export.py
python3 -I report.py previous_data.json previous_matches.json
