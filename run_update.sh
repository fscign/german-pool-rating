#!/bin/sh
# Daily update of the German Pool Rating: (collect) -> build -> rate -> export -> report.txt
set -e
cd "$(dirname "$0")"
rm -f update_log.txt
cp site/data.json previous_data.json 2>/dev/null || true
cp site/matches.json previous_matches.json 2>/dev/null || true
# On GitHub every source is collected by its own workflow (cuescore.yml, tournamentapp.yml, ...), so one site being down
# never stops the others; the daily workflow runs this script with --no-collect. Locally, plain "sh run_update.sh" does everything.
if [ "$1" != "--no-collect" ]; then
  python3 -I collect_cuescore.py || echo "CueScore could not be read this time (kept the old data)" >> update_log.txt
  python3 -I collect_team.py || echo "CueScore team events could not be read this time (kept the old data)" >> update_log.txt
  python3 -I collect_tournamentapp.py || echo "tournamentapp.de could not be read this time (kept the old data)" >> update_log.txt
  python3 -I collect_nuliga.py || echo "nuLiga Bavaria could not be read this time (kept the old data)" >> update_log.txt
  python3 -I collect_veveto.py || echo "VeVeTo Hessen could not be read this time (kept the old data)" >> update_log.txt
  python3 -I collect_scoretrek.py || echo "Score Trek could not be read this time (kept the old data)" >> update_log.txt
fi
python3 -I build_db.py > build_log.txt 2>&1
python3 -I make_fargo_fixed.py
python3 -I rate.py > rate_log.txt
python3 -I export.py
python3 -I report.py previous_data.json previous_matches.json
