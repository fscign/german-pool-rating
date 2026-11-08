#!/bin/sh
# Daily update of the German Pool Rating: (download data) -> build -> rate -> export -> report.txt
set -e
cd "$(dirname "$0")"
rm -f update_log.txt
cp site/data.json previous_data.json 2>/dev/null || true
cp site/matches.json previous_matches.json 2>/dev/null || true
# The raw data is collected in fscign/pool-data; get_data.sh downloads it (the daily workflow runs it before this script).
if [ "$1" = "--get-data" ]; then sh get_data.sh; fi
python3 -I build_db.py > build_log.txt 2>&1
python3 -I make_fargo_fixed.py
python3 -I rate.py > rate_log.txt
python3 -I export.py
python3 -I report.py previous_data.json previous_matches.json
