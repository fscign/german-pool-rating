# German Pool Rating

A FargoRate-style rating of German pool players (8-ball, 9-ball, 10-ball and Multiball), built the same way as the
Latvian Pool Rating (https://poolrating.horsuns.eu). Non-commercial, for the pool community.

## Sources (everything is collected raw; build_db.py decides what counts)
- CueScore, every pool event held in Germany: `collect_cuescore.py` -> `data/cuescore_raw.json.gz`
- CueScore team events (league match days, team cups), singles read from each team match: `collect_team.py` -> `data/team_raw.json`
- tournamentapp.de: `collect_tournamentapp.py` -> `data/ta_raw.json`
- nuLiga Bavaria (bbv-billard.liga.nu): `collect_nuliga.py` -> `data/bbv_nuliga_data.json.gz` (league singles from 2025/26, BBV championships)
- Hessen leagues (hpbv-veveto.de): `collect_veveto.py` -> `data/hessen_veveto.json.gz` (league singles from 2022/23; the site allows 20 requests a minute, so daily runs read only new reports)
- EPBF (Euro Tour, European Championships) and Matchroom / World Nineball Tour: collected only in the Latvian repo
  (`latvian-pool-rating`); the daily update copies `data/epbf_data.json.gz` and `data/wnt_data.json.gz` from there
  with the read-only token secret `LV_REPO_TOKEN`. If the token is missing or expired, the last copies here are used.
- FargoRate of foreign players: `fargo_update.py` -> `data/fargo_foreign.json` (weekly). Foreign players with 200+ FargoRate games keep their FargoRate as a fixed rating.

## What counts (rules in build_db.py)
- 8/9/10-ball and Multiball singles, races to 3 or more; singles inside team events count, doubles don't.
- Left out: handicap, doubles, straight pool, bank pool, one pocket, walkovers, unfinished matches, tournaments outside
  Germany (except EPBF and Matchroom events, which count in full).
- German players are shown; foreign players are rated in the background.

## Daily update
`run_update.sh`: collect (CueScore, team events, tournamentapp.de, nuLiga Bavaria, VeVeTo Hessen) -> `build_db.py` -> `make_fargo_fixed.py` -> `rate.py`
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
