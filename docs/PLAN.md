# Darts Performance Analyzer: Step-by-Step Plan

> Working plan for the project. Based on the original notes and on the workflow from the video
> *"I Built a Real Data App with Claude Code (and It Cost $0)"* ([YouTube](https://www.youtube.com/watch?v=3rgd2Xx5ceg)).
> App design, data model and methodology live in [DESIGN.md](DESIGN.md). Environment setup is in [SETUP.md](SETUP.md).

## Goal

An end-to-end data app about PDC darts with two core features:

1. **Pre-tournament predictions**: probabilities of reaching each round and winning big events. The first live target is the **PDC World Championship 2027** (starts December 2026). Includes draw/bracket analysis, "players to watch" and a comparison with bookmakers' outright odds.
2. **Player profiles**: current form (last 5 matches), background, an AI-written narrative (what's working, what isn't, what the player says in interviews) and a **Performance Index (PI) on a 0–10.0 scale** with a published methodology.

## The video's workflow and how we adapt it

| Step in the video | Our version |
|---|---|
| Plan mode in Claude Code, plan before code | ✅ this document |
| `databricks auth login --host …` + `databricks current-user me` | Day 0, see SETUP.md |
| `databricks aitools install --agents claude-code` | Day 0, see SETUP.md |
| Download data locally, upload to Databricks, create a table | Scrapers in `ingestion/` upload to a UC Volume, which feeds Delta tables (bronze) |
| AI Functions (`ai_extract`, `ai_query`) inside SQL | Form narratives, interview summaries, name and tournament normalization |
| Test AI on 20 rows first, then run on everything | Same: sample first, compare models |
| React + FastAPI app, test locally, deploy as a Databricks App | **Streamlit** app (`app/`), test locally, deploy via an Asset Bundle |
| Genie agent for natural-language questions | Genie space over gold tables, embedded in the app via the Genie Conversation API |
| One-time backfill | Backfill + **automated refresh** (monthly + on demand) |

## Architecture at a glance

```
 Sources (Mastercaller results, Wikipedia: PDC Order of Merit + draws + background, PDC news RSS;
          Darts Orakel until 28 Oct 2026)
        │  Python scrapers (ingestion/), run outside Databricks
        ▼
 UC Volume  /Volumes/workspace/darts_bronze/raw/<source>/<date>/*.jsonl
        │  Databricks Job "darts_refresh" (serverless)
        ▼
 bronze (raw Delta)  →  silver (clean, unified player IDs)  →  gold (PI, form, predictions)
        │                                                    │
        │                                       AI Functions (ai_query) → narratives
        ▼                                                    ▼
 Genie space (NL questions)                Streamlit Databricks App (SQL warehouse 2X-Small)
```

**Why not Airflow:** Databricks handles the refresh on its own. A Job supports a cron schedule (monthly) and a "Run now" trigger from the UI, the CLI or the app. Airflow would need an always-on server, which costs money. Free Edition has no managed orchestrator besides Jobs.

**Where scraping runs (decided in step 1.2):** Databricks serverless *can* reach the internet (PDC, Wikipedia and PyPI returned 200), but **Darts Orakel's Cloudflare returns 403 to Databricks IPs**, while the same request from a home connection works. We don't work around that block. So scraping runs **outside Databricks**: locally on demand (`make ingest`) and monthly in **GitHub Actions**, whose runners Orakel does accept (verified by the `egress-check` workflow). The Databricks Job then does all transformations.

## Databricks Free Edition limits that shape the design

- **Serverless** compute only, and a single **2X-Small SQL warehouse**.
- **Up to 3 Databricks Apps**. An app **stops automatically after 24 h** and has to be restarted. That's fine for a demo, and GitHub Actions can restart it if needed.
- **Max 5 concurrent job tasks** and 1 active pipeline per type, so one Job with a few tasks is enough.
- **Restricted outbound internet**: a non-public whitelist. In practice our blocker was the source site, not Databricks (see above).
- Fair-use quotas. Going over shuts compute off for the rest of the day (in extreme cases, the rest of the month). Data is kept.
- No SLA, non-commercial use only, and inactive accounts may be deleted.
- LinkedIn identity verification ("Verify identity") raises some limits. Recommended.

---

## Progress

| Day | Focus | Status |
|---|---|---|
| Day 0 | Admin and setup | ✅ done (2026-10-24) |
| Day 1 | Data foundation: sources, ingestion, bronze → silver | ✅ done (2026-10-25) |
| Day 2 | Analytics: Performance Index, prediction model, backtests | ✅ done (2026-10-28) |
| Day 3 | Source switch (Orakel blocked → Mastercaller + Wikipedia), health report, model promotion, GitHub Actions, key test vs PDC ranking, AI layer | ⏳ in progress |
| Day 4 | Streamlit app, Genie, deploy (ready for the Grand Slam, 14 Nov) | ⏳ app done locally (2026-10-31) |

---

## Day 0: Admin and setup ✅

- [x] Read the notes, pull the video transcript, write the plan and design
- [x] Install the Databricks CLI (`brew install databricks`, v1.22.1)
- [x] Scaffold the repo: `.gitignore`, `CLAUDE.md`, Asset Bundle skeleton
- [x] First commit + push to GitHub
- [x] Create the Databricks Free Edition account and workspace
- [x] `databricks auth login --profile darts` (OAuth), verified with `databricks current-user me -p darts`
- [x] `databricks aitools install --agents claude-code --scope global` (Databricks plugin v0.2.32), Claude Code reloaded
- [x] `scripts/bootstrap_databricks.sh`: schemas `workspace.darts_bronze/silver/gold` + Volume `workspace.darts_bronze.raw`
- [x] `databricks bundle validate -t dev` passes
- [x] Verify identity via LinkedIn in the workspace (raises some Free Edition limits)

## Day 1: Data foundation ✅

**Goal by end of day:** real data in `silver.players`, `silver.matches`, `silver.tournaments` and `silver.rankings`, plus the decision on where scraping runs.

1.1 [x] **Source inventory.** Decisions:
   - ✅ **Darts Orakel, free public API only** (primary source). Endpoints: `/api/rankings` (2-year prize money = Order of Merit equivalent, DOB, country), `/api/events` (every event with category, prize fund, event average), `/api/player/matches/{player_key}` (every match with one stat per call: average, first-9 average, checkout %, 180s, each with numerator/denominator). Event results pages are **behind a subscription paywall, so we don't use them**. Their robots.txt allows everything, but Orakel sells data commercially, so we run it **gently**: top 150 players, 1 request / 2 s, a disk cache, an identifying User-Agent, and a "Data: Darts Orakel" credit in the app. Non-commercial use.
   - ✅ **Wikipedia / Wikidata** via the official APIs: WC pages 2024–2027 (draws for backtests and the 2027 bracket) and player background (DOB, citizenship, nickname, image, intro). CC BY-SA, credited in the app.
   - ❌ **DartsDatabase**: its robots.txt explicitly disallows AI agents (`anthropic-ai`, `ClaudeBot`, `GPTBot`…). Excluded.
   - ❌ **pdc.tv Order of Merit**: rendered client-side. Not needed, because Orakel rankings cover it.
   - ⏸ **Mastercaller**: blocks scripted clients (418/403). Not needed.
   - ⏸ **News/interviews and outright odds**: postponed to Day 2/3 (the AI layer and the odds comparison).

1.2 [x] **Egress test from Databricks** (job `darts_egress_check`): PDC 200, Wikipedia 200, PyPI 200, DartsDatabase 200, **Darts Orakel 403**, Mastercaller 418. Orakel works locally with the same honest User-Agent, so it's an IP block on its side. **Decision: ingestion runs outside Databricks, transformations inside.**

1.3 [x] **Scrapers** in `ingestion/`: `http.py` (polite client: rate limit, retries, disk cache in `data/cache/`), `orakel.py`, `wikipedia.py`, `run.py` (CLI that writes `data/raw/<source>/<run_date>/*.jsonl` and uploads them to the Volume with `--upload`).
   **Incremental by default** (`make ingest`): players tracked in the previous run get matches from (previous run − 14 days), players new to the top 150 get full history, and Wikipedia background is fetched for new players only. Each run writes its own folder `raw/<source>/<YYYY-MM-DDTHHMMSS>/`, so no run overwrites another. Silver deduplicates across runs (newest wins). Full re-pull: `make backfill`.
   Note: the request count stays about the same (1 request per player per stat, ~600 per run, ~20 min); what shrinks is the data volume per run.

1.4 [x] **Backfill:** top 150 players, matches since 2023-01-01 → Volume `raw/orakel/2026-10-25/`, `raw/wikipedia/2026-10-25/`. About 615 Orakel requests in 26 min; 290k raw stat rows (240 MB JSONL, 5.8 MB as Delta).

1.5 [x] **Bronze tables** (`src/notebooks/01_bronze.py`): `read_files` over the Volume with `_run_date`, `_source_file` and `_ingested_at`. Tables: `orakel_rankings`, `orakel_events`, `orakel_matches`, `wiki_tournament_pages`, `wiki_player_background`.

1.6 [x] **Bronze → silver** (`src/notebooks/02_silver.py`): `events`, `player_matches` (one row per player per match, stats pivoted, plus view `player_matches_v` with average / first-9 / checkout %), `matches`, `players` (tracked players + every opponent, with Wikidata background), `rankings` (snapshot history), `tournament_pages`. **Player ID = Orakel `player_key`**. Wikipedia is matched to it at ingestion, so no fuzzy matching is needed.

1.7 [x] **Data quality checks** (`src/notebooks/03_quality.py`): 7 hard checks that fail the job (duplicates, winner ≠ loser, averages in range, checkouts ≤ attempts…) + soft metrics (missing stats, Wikidata match rate, date range).

1.8 [x] Full run of `darts_refresh` (bronze → silver → quality) on the backfill, all hard checks green, ~1.5 min:
   - `player_matches` 72,861 · `matches` 54,146 · `players` 5,106 (150 tracked + opponents) · `events` 3,908 · range 2023-01-01 .. 2026-10-24
   - The source contains ~0.01 % impossible values (checkouts hit > attempts, a 14.3 average in an exhibition). Silver nulls the broken stat and keeps the match.
   - Sanity check, last 180 days: Littler 100.55, Humphries 99.29, Price 97.37 ✔
   - Follow-up: only 76 % of tracked players matched to Wikidata. Improve the name search on Day 3 (needed for player backgrounds).

## Day 2: Analytics, Performance Index and predictions ✅

**Goal by end of day:** `gold.performance_index` and the Tournament Overview data (`gold.tournament_predictions`, upcoming matches) populated and backtested.

**Decisions (2026-10-28):**
- Tournament Overview for **all majors**; the World Championship 2027 is the first live test (Grand Slam 14–22 Nov and Players Championship Finals 27–29 Nov serve as a dress rehearsal).
- Refresh: **daily during majors**, otherwise **on demand** via a button in the app showing the time of the last refresh.
- PI scale: **10 × P(beat an average top-32 player)**.
- PI method: **variant A**, a transparent 3-step regression (select predictors → weights → scale), plus Effective Average. Rating named **Opponent-Weighted Elo**; it stays only if it passes the same selection rule.

2.1 [x] **Majors definition** fixed: Orakel categories are not stable (the World Cup shares `WC`, Masters switches between `U` and `MJ`, PC Finals has its own `PCF`). Now an explicit list of 10 `tournament_key`s in `config/majors.yml` → `is_major` in silver + `silver.majors`.
2.2 [x] **Performance Index**: [PERFORMANCE_INDEX.md](PERFORMANCE_INDEX.md). Shared package `src/analytics/` (features, Elo, model, pipeline) + notebooks `04_pi_model`, `05_performance_index` in the job; unit tests in `tests/`. The training-data summary is stored per model version (`darts_gold.pi_training_data`).
   - Backfill extended to **2021–2022** (separate run, 22.8k rows per stat): the model now learns from 22,456 matches between tracked players (Feb 2021 – Oct 2026).
   - Selected (v2026-10-28): 3-Dart Average (L30) 58 %, Opponent-Weighted Elo 21 %, Form 18 %, Experience 3 % (borderline: exactly 80 % in the bootstrap). Dropped: First-9 (r = 0.94 with average), Win Rate and Checkout % (negative coefficients), 180s (p = 0.69).
   - **Big-Stage Delta** (majors only, decided 2026-10-28: keep the 80 % rule): 73 % of bootstrap samples with data since 2023, **61 %** with data since 2021, so the longer history weakened the evidence. Out of the index, re-tested on every refit, shown descriptively in profiles.
   - Test 2026: AUC 0.684 (0.707 on majors), well calibrated. Top 3: Littler 7.15, Humphries 6.36, Price 5.88.
2.3 [x] **Backtests** of the PI on 10 majors (2025–2026, 388 matches): favourite won 69.1 %, log loss 0.582, calibrated (slight overconfidence above ~85 %). Details in [TOURNAMENT_PREDICTIONS.md](TOURNAMENT_PREDICTIONS.md#5-backtests).
2.4 [x] **Format conversion** (`analytics.formats`): typical match → leg probability → first to N legs / sets. It improves log loss (0.588 → 0.582).
2.5 [x] **Monte Carlo** of the draw (10,000 runs) from Wikipedia brackets (`analytics.bracket`: sections + finals, byes, walkovers, round formats) → `gold.tournament_predictions`, `gold.tournament_draw_matches`.
2.6 [x] **Upcoming matches + live bracket**: Orakel upcoming feed → `gold.upcoming_matches` (PI vs PI, P(win), H2H); live mode fixes played matches and re-simulates the rest. The feed is empty today; the empty case is handled (never shows stale matches). Tested in `tests/test_tournament.py`.
2.7 [x] **Season calendar** `gold.majors_calendar`: Wikipedia infobox dates + Orakel winners, status, placeholder for majors without data yet (e.g. Players Championship Finals 2026).
2.8 [ ] Odds comparison → `gold.players_to_watch`: **no odds source yet** (moved to open questions).
2.9 [x] `gold.player_recent_matches` (last N matches per player) and **8 saved queries** in Databricks (`sql/queries/*.sql`, synced by `scripts/sync_queries.py` into the workspace folder `darts-data-app/queries`).

## Day 3: Backend robustness, automation and AI layer ⏳

**Goal by end of day:** a fully automatic refresh that runs without the Mac (GitHub Actions + Databricks Job), a green health report, the key test "model vs PDC ranking", and AI narratives in gold tables.

### What happened on 2026-10-30
- **Darts Orakel blocked our client** (403 on our identified User-Agent, even on robots.txt). We don't circumvent it and don't contact them; if they ask us to delete their data, we will. Their data until 28 Oct 2026 stays in the Volume and in the model.
- **New sources** (all free and allowed):
  - **Mastercaller** (`mastercaller.com`, robots.txt allows all, stats by iDarts) gives PDC results with 3-dart averages, incrementally through the daily match center + tournament results pages, ~5–20 requests per refresh. Scheduled matches in the match center replace Orakel's upcoming feed.
  - **Wikipedia `Module:DartsRankings/data/PDC Rankings`** is the official PDC Order of Merit, current and **historical** (revision at any date since 2020) through the official API.
  - **pdc.tv**: not usable, because its data API requires authentication (401).
- **The model needs only results and 3-dart averages** (selected predictors: 3-dart average, form, Elo, experience), so Mastercaller covers it. Darts per match are estimated from legs (`legs × 1503 / average`). Validated on Orakel data: the 3-dart average (L30) moves by −0.06 points on average, 95 % within ±0.24.
- **Databricks Free Edition fair-use quota** reached (too many job runs today): new job runs are paused until the quota resets. Code is tested locally meanwhile, and everything is deployed and verified in **one** run afterwards.

### Steps

3.0 [ ] **Source switch**: code done and data ingested, **waiting for one verification run in Databricks**
   - [x] `ingestion/mastercaller.py` (results, upcoming), `wikipedia.fetch_rankings_at` (Order of Merit at any date), `ingestion/pdc_news.py`, `run.py` rewritten (each source isolated, manifest per run), Orakel ingestion removed
   - [x] ingested: Oct 2026 complete (11 PDC tournaments incl. PC 31–32), Order of Merit history 2021–2026, first PDC news
   - [x] silver rewritten: Orakel + Mastercaller unified, `player_crosswalk`, tracked players and rankings from the PDC Order of Merit
   - [x] all sources reachable from GitHub runners (egress-check 2026-10-30: Mastercaller, PDC RSS, Wikipedia, Wikidata)
   - [ ] **verify in Databricks**: full job run; Orakel vs Mastercaller averages on the overlap; crosswalk report
3.1 [x] **Health report** (code): `analytics/health.py` + notebook `07_health` + job task `health`. Checks: ingestion (manifest, blocked source → red with "don't work around it"), freshness, draws of running majors, name matching, unknown series ("possible new major → config"), model promotion, key test, upcoming matches. Red fails the job → e-mail. Tests: `tests/test_health.py`. *First real run with the verification run.*
3.2 [x] **Model promotion policy** (code): `analytics/registry.py`, registry `darts_gold.pi_model_registry`; PI and tournaments use the active version. Tests: `tests/test_registry.py`. Documented in PERFORMANCE_INDEX.md.
3.3 [x] **Failure notifications**: the job e-mails the workspace user on failure (incl. a red health report). The GitHub workflow fails visibly (GitHub e-mails on failed workflow runs by default).
3.4 [ ] **GitHub Actions `refresh.yml`**: written and pushed (daily 06:00 UTC, works only while a major is running or starts tomorrow; manual "Run workflow" otherwise; skips quietly until secrets exist). **Needs from you:** Databricks token + GitHub secrets (step 3 in "Next steps" below).
3.9 [x] **Key test: the model beats the PDC ranking, also on majors** (updated 2026-10-31 after 3.10):
   - walk-forward majors 07/2023–10/2026 (1,825 matches, quarterly refits): log loss **0.628 vs 0.652**, gain +0.024 [+0.014, +0.034], **p < 0.001**
   - walk-forward all matches (16,805): 0.643 vs 0.669, p < 0.001; 2026 test period: 0.639 vs 0.670, p < 0.001
   - 2026 majors alone (431): 0.622 vs 0.636, p = 0.08 (same direction, too few matches for significance)
   - computed on every refit (`pi_benchmark`), watched by the health report
3.10 [x] **Model tuning (2026-10-31)**:
   - **Look-ahead bug found and fixed**: Orakel numbers single-day Players Championships backwards, so ordering same-day matches by id let early rounds see later ones. Matches are now ordered by round (`analytics/rounds.py`) with a regression test. All numbers recomputed.
   - **7 new candidates**, fixed before testing: PDC Order of Merit (log rank), Big-Stage Elo, Big-Stage Experience, Head-to-Head, Consistency, Activity, Match Sharpness.
   - **New selection: 3-Dart Average 53 %, Elo 21 %, Form 15 %, PDC Order of Merit 12 %**. Experience is out (its earlier pass came from the bug). All other new candidates fail the rules; Big-Stage Delta is still unstable (71 % < 80 %).
   - Current PI: Littler 7.35, Humphries 6.62, Price 6.02, Clayton 5.85, Ross Smith 5.84.
   - Tournament backtests recomputed: 388 matches, favourite won 68.8 %, log loss 0.579.
   - Docs: PERFORMANCE_INDEX.md rewritten (all 16 predictors with reasons, key test, correction note), TOURNAMENT_PREDICTIONS.md updated.
   - **Big-stage ability, 3 more predictors** (Stage Delta, Long-Format Delta, Results over Expectation, all majors-only): none passes the rule. Stage Delta misses by 1 pp (79 % vs 80 % in the bootstrap; walk-forward gain on majors +0.0026, p = 0.055; majors-only regression p = 0.001). Decision: rule unchanged; **Stage Delta replaces Big-Stage Delta as the information-only indicator** in the app (Day 4), re-tested on every refit.
3.5 [ ] **AI narratives** with `ai_query`: short player assessments from form + stats → `gold.player_ai_summary`. Compare 2–3 foundation models on 20 players first (as in the video). *Needs Databricks.*
3.6 [ ] **News and interviews**: ingestion done (`pdc_news`, kept forever in bronze); still to do: silver (players mentioned per article), AI summaries per player, news-gap check in the health report. *AI part needs Databricks.*
3.7 [ ] Improve Wikidata matching for player backgrounds.
3.8 [x] **Odds: left out for good** (decided 2026-10-28). Nothing meets the conditions "free, legal from the Czech Republic, no manual work": Betfair and Smarkets are geo-blocked for CZ (403), odds-api.io is paid, The Odds API has no darts, Livesport/Tipsport/Betano forbid scraping (Livesport terms art. 2.9/2.10), and no free historical darts odds dataset exists. Re-check only if a free darts odds API reachable from CZ appears.

### Next steps (in this order)
1. **When the Databricks quota resets** (still paused on 2026-10-31): `make deploy` + **one** full run of `darts_refresh`. Check: silver with both sources, crosswalk report, Orakel vs Mastercaller overlap, health report, key test in `pi_benchmark`, `pi_model_registry` has the first active version.
2. Fix whatever the verification run shows (expect a few small issues in the new silver).
3. **You:** create a Databricks access token (User Settings → Developer → Access tokens → Generate, e.g. 90 days) and add two GitHub secrets (repo → Settings → Secrets and variables → Actions): `DATABRICKS_HOST` = `https://dbc-2318ef7e-ac1e.cloud.databricks.com`, `DATABRICKS_TOKEN` = the token. Then start "refresh" once by hand in the GitHub Actions tab. From then on no Mac is needed.
4. 3.6 news → players + 3.5 AI narratives (Databricks `ai_query`, compare models on 20 players).
5. 3.7 backgrounds, then **Day 4** (app, Genie, deploy) before the Grand Slam (14 Nov).

**Free Edition quota:** a full run is ~7 tasks. Avoid repeated full runs on the same day: use `--only <task>` while developing and test locally first.

How fixes happen: config-only issues (e.g. a new major) can be fixed by editing `config/majors.yml` on GitHub. Code issues (parser, source changes) are fixed in the repo with Claude Code and deployed with the bundle. Never edit code in the Databricks workspace, because `bundle deploy` overwrites it. Genie helps to diagnose (questions over the health report and gold tables), not to fix.

## Day 4: Streamlit app, Genie and deploy

**Goal by end of day:** a live Databricks App URL with all pages, Genie Q&A, the Refresh button and the health badge, ready for the **Grand Slam (14–22 Nov 2026)** as the first live event.

4.1 [x] **Streamlit app** done locally (2026-10-31) against a Parquet snapshot (`DARTS_DATA=local`, built by `scripts/build_local_snapshot.py`); the same code reads the SQL warehouse in production. Pages: Tournament Overview (status banner finished / live / upcoming, match cards with score and winner first, player photos, predictions, upcoming matches with PI and Effective Average, season calendar), Player Profile (photo, current PDC Order of Merit rank, PI, Effective Average, Stage Delta as info, PI over time, recent form, structured profile facts, titles from `gold.player_titles`), PI Leaderboard (name search with autocomplete, head to head), Ask the data, Methodology, Data & Health. Feedback round 1 applied (seed `&nbsp;` fix, Effective Average tooltip, contributions chart dropped). Still open: warehouse mode test on Day A, AI narrative (3.5), Genie (4.3).
4.2 [ ] **Refresh button + health badge**: dispatches the GitHub Actions refresh, shows the last refresh time and the health status with warnings.
4.3 [ ] **Genie space** over the gold tables with instructions and sample questions, embedded via the Conversation API.
4.4 [ ] **Deploy** as a Databricks App via the bundle (the app's service principal gets the permissions it needs), end-to-end test.
4.5 [ ] **README**: link to the video, infrastructure overview, Free Edition limits, screenshots.

## After Day 4

- Live run for the **PDC World Championship 2027** once the draw is out (usually late November).
- Re-test Big-Stage Delta as more major matches accumulate (automatic on every refit).

## Open questions

- App language: English only, or with a Czech toggle?
- Day-form spread in the simulation to correct overconfidence for heavy favourites in long formats.
- Parsers for the 96-player WC format (2024, 2025), the Grand Slam groups and the PC Finals sections.
