#!/bin/sh
# Downloads the raw data from fscign/pool-data (release "data", replaced by every collection run).
# If a release file can't be downloaded, the starting copy in the pool-data repo is used.
mkdir -p data status
FILES="de_cuescore_raw.json.gz de_team_raw.json ta_raw.json bbv_nuliga_data.json.gz hessen_veveto.json.gz scoretrek_raw.json.gz
epbf_data.json.gz wnt_data.json.gz pbs_data.json.gz"
for c in pl cz nl be lu at ch it fr fi se dk no; do FILES="$FILES ${c}_cuescore_raw.json.gz ${c}_team_raw.json"; done
for f in $FILES; do
  if curl -fsSL --retry 3 -o "data/$f.new" "https://github.com/fscign/pool-data/releases/download/data/$f"; then mv "data/$f.new" "data/$f"
  elif curl -fsSL --retry 3 -o "data/$f.new" "https://raw.githubusercontent.com/fscign/pool-data/main/data/$f"; then mv "data/$f.new" "data/$f"; echo "$f: release file missing, used the starting copy"
  else rm -f "data/$f.new"; echo "$f: NOT downloaded"; fi
done
gh release download data -R fscign/pool-data -p 'status_*' -D status --clobber 2>/dev/null || echo "status files not downloaded"
