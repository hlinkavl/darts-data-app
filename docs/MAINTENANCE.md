# Maintenance

Everything needed to keep the app running and to fix it: how the refresh works, what to do when it breaks, tokens,
setup from scratch, development and deploy, the data model, and the decisions behind the design.
What the app is and how it is built: [README](../README.md). How the numbers are made: [METHODOLOGY](METHODOLOGY.md).

**Contents:**
[1. How the refresh works](#1-how-the-refresh-works) ·
[2. When something breaks](#2-when-something-breaks) ·
[3. Common fixes](#3-common-fixes) ·
[4. Tokens and their renewal](#4-tokens-and-their-renewal) ·
[5. Develop, test, deploy](#5-develop-test-deploy) ·
[6. Setup from scratch](#6-setup-from-scratch) ·
[7. Data model](#7-data-model) ·
[8. Decisions and known limits](#8-decisions-and-known-limits)

Quick facts: Databricks CLI profile `darts`, catalog `workspace`, SQL warehouse `c7c519d783971c09`, app
`darts-performance-analyzer`, Genie space `01f1ddf6938b1cb19ccfe38d51512b61`, job `darts_refresh` (bundle target `dev`).

---

## 1. How the refresh works

1. **GitHub Actions `refresh`** starts every day (cron 03:23 UTC; GitHub actually starts it around 10:30–12:00 UTC).
   The gate `scripts/should_refresh.py` reads the majors' Wikipedia pages: outside a major (or the day before one) the
   run ends in under a minute and uses no Databricks compute.
2. During a major: `python -m ingestion.run --upload` fetches Mastercaller (results, averages, scheduled matches),
   Wikipedia (Order of Merit, draws, player background and photos) and the PDC news feed, and uploads JSONL files to the
   Volume `/Volumes/workspace/darts_bronze/raw`.
3. `scripts/run_refresh_job.py --start-app` runs the Databricks job `darts_refresh` (~6 min) and starts the app for 24 h:
   `bronze → silver → quality → pi_model → performance_index → narratives + tournaments → health`.
4. Outside majors the app is stopped. Start it with Actions → **start-app** → Run workflow; refresh by hand with
   Actions → **refresh** → Run workflow, or with **Refresh data now** on the app's Data & Health page.

Compute is saved on purpose (Free Edition has a fair-use quota): the PI model refits every 28 days (job parameter
`refit=force` refits now), otherwise only Elo is updated; backtests of finished majors and past monthly PI snapshots
are reused while the model and the tracked players stay the same; AI summaries are regenerated only when their input
changes.

## 2. When something breaks

The refresh is built to fail loudly and never to show wrong numbers:

- **Each source on its own.** One failing source does not stop the others; the run's manifest records rows and
  errors per source.
- **Quality gate before the gold tables.** Hard checks (duplicates, impossible averages, empty tables) stop the job
  before any model or prediction is computed, so the app keeps the last good data.
- **Model promotion gate.** A refit becomes active only if it passes the test; otherwise the previous model stays.
- **Health report** (app → Data & Health), every problem with a "What to do". **Red fails the job** and sends two
  e-mails (Databricks job, GitHub workflow). Red means: a source failed or blocks us, the Order of Merit came back
  empty, no model, or **no new result for more than 4 days while a major is running** (a source answers "ok" but
  delivers nothing new, typically after a page change). **Yellow** shows only in the app: a draw format we don't
  parse, a new series for the config, a refit that was not activated, many players without results.
- During a major the app is started even when the job failed, so it shows the last good data.

What to do when the e-mail arrives:

1. Open the failed run (link in the e-mail) and Data & Health in the app: the red check says what broke.
2. A one-off error (timeout, Databricks quota "please try again later"): wait, then Refresh in the app or
   "Run workflow" on GitHub.
3. A source changed its page, or a new tournament format: open Claude Code in the repo, paste the error and the health
   message, fix, test (section 5), deploy, Refresh.
4. A source blocks us (HTTP 401/403): don't work around it; find a replacement source.
5. An expired token: section 4.

Expect a few fixes a year, mostly when a season starts or a format changes. Never edit code in the Databricks
workspace: `bundle deploy` overwrites it.

## 3. Common fixes

| Symptom (health report) | Fix |
|---|---|
| New series in Mastercaller | A new major → `config/majors.yml` (name, Wikipedia title, Mastercaller slug); any other series → `config/mastercaller_series.yml`. Editing on GitHub is enough; the next refresh picks it up after `bundle deploy`. |
| Tracked players without results (name matching) | A different spelling between sources: create `config/player_aliases.yml` with `names: {"Spelling in source": <player_key>}` or `mastercaller: {<slug>: <player_key>}`. |
| Draw missing for a running major | The Wikipedia bracket format is new: extend `src/analytics/bracket.py` (tests in `tests/test_tournament.py`). Known and accepted: the 2026 Grand Slam group stage (predictions start from the last 16). |
| Order of Merit empty | Wikipedia's `Module:DartsRankings/data/PDC Rankings` changed: `ingestion/wikipedia.py`. |
| Mastercaller error or no new results | `ingestion/mastercaller.py`; compare with the event's results page. |
| Refit not activated | Review `darts_gold.pi_selection_log` and `pi_model_registry`; to force a refit: `databricks bundle run darts_refresh -t dev --profile darts --params refit=force`. |
| AI summary wrong or missing | Model in `config/ai.yml`. Compare models: `--only narratives --params compare_models=<m1>,<m2>` (writes `darts_gold.player_narrative_trials`, 20 players each). |
| Genie answers badly | Edit `config/genie/space.yml` (instructions, example SQL: run each on the warehouse first), then `DATABRICKS_CONFIG_PROFILE=darts python scripts/genie_space.py`. |

## 4. Tokens and their renewal

Two tokens keep the refresh running without a Mac. Neither is stored in the repo.

| Token | Used by | Stored in | Expires |
|---|---|---|---|
| Databricks access token "github-actions" | GitHub Actions (`refresh`, `start-app`): upload data, run the job, start the app | GitHub secret `DATABRICKS_TOKEN` (with `DATABRICKS_HOST`) | **9 Nov 2027** |
| GitHub fine-grained token `darts-app-refresh` (repo `darts-data-app`, Actions: read and write) | The app's **Refresh data now** button | Databricks secret scope `darts`, key `github_token` | about one year from 9 Nov 2026; exact date at github.com/settings/personal-access-tokens |

An expired token shows up as a failed `refresh` run or as an error after pressing Refresh. Renew a week ahead.

**Databricks token**
1. Databricks → Settings → Developer → Access tokens → **Generate new token**: comment `github-actions`, 365 days.
2. GitHub → repo → Settings → Secrets and variables → Actions → `DATABRICKS_TOKEN` → **Update**, paste the token.
3. Revoke the old token in Databricks.
4. Check: Actions → **start-app** → Run workflow; it must start the app or report "already running".

**GitHub token**
1. github.com/settings/personal-access-tokens → `darts-app-refresh` → **Regenerate token** (one year).
2. `databricks secrets put-secret darts github_token --profile darts`, paste the token.
3. Restart the app (it reads secrets at start): `databricks apps stop darts-performance-analyzer --profile darts`,
   then `databricks apps start darts-performance-analyzer --profile darts`.

**CLI login** on the Mac is OAuth and expires after some idle time: `databricks auth login --profile darts`.

## 5. Develop, test, deploy

```bash
make setup                                          # local venv (.venv)
.venv/bin/python -m pytest -q                       # unit tests, incl. the Python 3.11 syntax check for the app
python scripts/build_local_snapshot.py              # local Parquet snapshot of the data
cd app && DARTS_DATA=local streamlit run app.py     # app on the snapshot, http://localhost:8501
```

Deploy:

```bash
databricks bundle deploy -t dev --profile darts     # job, notebooks, configs, app settings
# app code: smoke-test against the warehouse first, then deploy the source
DATABRICKS_CONFIG_PROFILE=darts DATABRICKS_WAREHOUSE_ID=c7c519d783971c09 python scripts/smoke_app.py databricks
databricks bundle run darts_app -t dev --profile darts
```

Rules that save quota and trouble:
- Run single tasks while developing: `databricks bundle run darts_refresh -t dev --profile darts --only <task>`.
  Avoid repeated full runs on the same day.
- Databricks Apps run Python 3.11 (no backslashes or quotes inside f-string expressions); the warehouse returns
  time-zone-aware timestamps and Decimals (`app/data.py` converts them).
- The app is stopped outside majors; `bundle run darts_app` starts it.

## 6. Setup from scratch

1. Tools: `brew tap databricks/tap && brew install databricks`, Python 3.11+, `make setup`.
2. Databricks Free Edition (databricks.com/learn/free-edition), then "Verify identity" (raises some limits).
3. `databricks auth login --host https://<workspace>.cloud.databricks.com --profile darts`.
4. Optional, for Claude Code: `databricks aitools install --agents claude-code --scope global`.
5. `./scripts/bootstrap_databricks.sh` (schemas `darts_bronze/silver/gold`, Volume `darts_bronze.raw`), then
   `databricks bundle deploy -t dev --profile darts`.
6. First data: `make ingest`, then `databricks bundle run darts_refresh -t dev --profile darts`.
7. GitHub secrets `DATABRICKS_HOST` and `DATABRICKS_TOKEN`; the GitHub token into the secret scope (section 4).
8. Grant the app's service principal `USE CATALOG` on `workspace`, `USE SCHEMA` + `SELECT` on `darts_gold` and
   `SELECT` on `darts_silver.players`; create the Genie space (`scripts/genie_space.py`) and put its id into
   `resources/app.yml`; deploy the app (section 5).

## 7. Data model

Unity Catalog `workspace`. Raw files: `/Volumes/workspace/darts_bronze/raw/<source>/<run>/<dataset>.jsonl`.

| Layer | Tables |
|---|---|
| bronze | one table per source dataset, loaded 1:1 with `_run_date`, `_source_file`, `_ingested_at` |
| silver | `players` (`is_tracked` = Order of Merit top 150, background, photo), `player_crosswalk` (one `player_key` across sources), `events`, `majors`, `matches`, `player_matches` + view `player_matches_v` (averages), `rankings` (Order of Merit snapshots), `tournament_pages`, `upcoming_matches` |
| gold: PI | `performance_index` (monthly snapshots, `is_current`), `pi_model_registry`, `pi_coefficients`, `pi_benchmark`, `pi_selection_log`, `elo_history`, `player_recent_matches` (view) |
| gold: tournaments | `majors_calendar`, `tournament_predictions`, `tournament_draw_matches`, `tournament_backtest_matches`, `tournament_backtest_summary`, `upcoming_matches`, `player_titles` |
| gold: AI | `player_news`, `player_narratives`, `player_narrative_trials` |
| gold: operations | `health_report` (latest), `health_history` |

Saved queries for the workspace: `sql/queries/*.sql` (`scripts/sync_queries.py`).

## 8. Decisions and known limits

- **Sources.** Darts Orakel blocked our client on 30 Oct 2026: never work around it and don't contact them; its data
  until 28 Oct 2026 is kept and deleted only if they ask. Since then: Mastercaller (results with 3-dart averages;
  darts per match estimated from legs, validated against Orakel within ±0.24 points for 95 % of players), Wikipedia /
  Wikidata, PDC news RSS. Excluded: DartsDatabase (robots.txt disallows AI agents), pdc.tv data API (needs
  authentication), bookmaker odds (no free legal source reachable from the Czech Republic).
- **Ingestion runs on GitHub Actions**, not in Databricks: Free Edition restricts outbound internet, and Orakel blocked
  Databricks IPs. No Airflow: GitHub Actions plus a Databricks job cost nothing.
- **Free Edition limits:** serverless only, one 2X-Small SQL warehouse, up to 3 apps (each stops after 24 h), 5
  concurrent job tasks, a fair-use compute quota (when exceeded, jobs, the warehouse and apps cannot start for a
  while; data is kept), no SLA, non-commercial use.
- **Model.** Predictor selection requires stability in 80 % of bootstrap samples; Big-Stage and Stage Delta miss it and
  are shown as information only. Re-tested on every refit.
- **Tournament formats.** The 2026 Grand Slam group stage (16 groups of 3) is not simulated; predictions start from
  the last 16. Revisit if more events adopt group stages. The 96-player World Championship format (2024, 2025) and
  the PC Finals sections have no parser.
- **AI summaries:** Qwen3 Next 80B (chosen on 11 Nov 2026 over Llama 3.3 70B and Llama 4 Maverick), for the PI top 32
  plus players with recent news.
- **Ideas:** a "day form" spread in the simulation to temper heavy favourites in long formats.
