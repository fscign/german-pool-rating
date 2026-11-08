# German Pool Rating

A FargoRate-style rating of German pool players (8-ball, 9-ball, 10-ball and Multiball), built the same way as the
Latvian Pool Rating (https://poolrating.horsuns.eu). Non-commercial, for the pool community.

## Sources
All raw data is collected in https://github.com/fscign/pool-data (since 9 Nov 2026): CueScore (Germany and 9 other
countries, tournaments and team events), tournamentapp.de, nuLiga Bavaria, VeVeTo Hessen, Score Trek Battle, EPBF,
Matchroom / WNT and PBS. `get_data.sh` downloads the files the build uses (release "data" of pool-data).
- FargoRate of foreign players: `fargo_update.py` -> `data/fargo_foreign.json` (weekly).

## What counts (rules in build_db.py)
- 8/9/10-ball and Multiball singles, races to 3 or more; singles inside team events count, doubles don't.
- Left out: handicap, doubles, straight pool, bank pool, one pocket, walkovers, unfinished matches, tournaments outside
  Germany (except EPBF and Matchroom events, which count in full).
- German players are shown; foreign players are rated in the background.

## Daily update
`get_data.sh` (download from pool-data) -> `run_update.sh`: `build_db.py` -> `make_fargo_fixed.py` -> `rate.py`
-> `export.py` (`site/data.json` + `site/matches.json`, two files because Cloudflare Pages allows 25 MiB per file) -> `report.py`.
GitHub Actions runs it every day (`.github/workflows/daily.yml`); the summary of each run shows the report.

## Setup (once)
1. Create a new private GitHub repository, e.g. `german-pool-rating`, and upload all files of this folder.
   Upload `.github/workflows/*.yml` directly into `.github/workflows` (the web upload skips folders starting with a dot).
2. Settings > Secrets and variables > Actions: add `LV_REPO_TOKEN`, a fine-grained personal access token limited to the
   repository `latvian-pool-rating` with "Contents: Read-only" (GitHub profile > Settings > Developer settings >
   Personal access tokens > Fine-grained tokens). Settings > Actions > General: "Read and write permissions".
3. Cloudflare Pages: new project from this repository, build output directory `site`, no build command.
4. Actions tab: run "Daily rating update" once by hand and check its summary.
