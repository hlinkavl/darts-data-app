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
 Sources (Darts Orakel free API, Wikipedia/Wikidata, news/RSS, odds)
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
| Day 2 | Analytics: Performance Index, prediction model, backtests | ⏳ in progress (PI done) |
| Day 3 | AI layer, Genie, Streamlit app, deploy, automation | ⬜ |

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

## Day 2: Analytics, Performance Index and predictions

**Goal by end of day:** `gold.performance_index` and the Tournament Overview data (`gold.tournament_predictions`, upcoming matches) populated and backtested.

**Decisions (2026-10-28):**
- Tournament Overview for **all majors**; the World Championship 2027 is the first live test (Grand Slam 14–22 Nov and Players Championship Finals 27–29 Nov serve as a dress rehearsal).
- Refresh: **daily during majors**, otherwise **on demand** via a button in the app showing the time of the last refresh.
- PI scale: **10 × P(beat an average top-32 player)**.
- PI method: **variant A**, a transparent 3-step regression (select predictors → weights → scale), plus Effective Average. Rating named **Opponent-Weighted Elo**; it stays only if it passes the same selection rule.

2.1 [x] **Majors definition** fixed: Orakel categories are not stable (the World Cup shares `WC`, Masters switches between `U` and `MJ`, PC Finals has its own `PCF`). Now an explicit list of 10 `tournament_key`s in `config/majors.yml` → `is_major` in silver + `silver.majors`.
2.2 [x] **Performance Index**: [PERFORMANCE_INDEX.md](PERFORMANCE_INDEX.md). Shared package `src/analytics/` (features, Elo, model, pipeline) + notebooks `04_pi_model`, `05_performance_index` in the job; unit tests in `tests/`. Result of v2026-10-28:
   - Selected: 3-Dart Average (L30) 63 %, Form 18 %, Opponent-Weighted Elo 19 %. Dropped: First-9 (r = 0.94 with average), Win Rate (r = 0.81 with Elo), Checkout %, 180s, Experience.
   - **Big-Stage Delta**: related to results *on majors* (p = 0.004) but not elsewhere (p = 0.95), so it is modelled as a majors-only predictor. It passes 1a and 1b but is significant in only 73 % of bootstrap samples, so it is **out for now** (decision pending, see open questions).
   - Test 2026: AUC 0.686 (vs 0.679 average only, 0.659 Elo only), well calibrated. Top 3: Littler 7.04, Humphries 6.28, Price 5.83.
2.3 [ ] PI backtest on the World Championships 2025 and 2026 (pre-tournament PI vs. how far players got).
2.4 [ ] Match format conversion: "typical match" probability → leg probability → P(win) for best-of-N legs / sets (dynamic programming).
2.5 [ ] **Monte Carlo bracket simulation** (10,000 runs) → `gold.tournament_predictions` (P(reach round), P(title)); parse the draws from the Wikipedia WC pages.
2.6 [ ] **Upcoming matches + live bracket**: ingest Orakel's upcoming-matches feed; match cards (PI vs. PI, win probability, H2H); played matches fixed in the bracket, the rest re-simulated.
2.7 [ ] Season view: majors with dates, winners and the next upcoming major.
2.8 [ ] Odds comparison (if a source exists) → `gold.players_to_watch`.
2.9 [ ] `gold.player_form` (last 5 matches) for player profiles, and **saved queries** in Databricks (`sql/queries/`).

## Day 3: AI layer, app, deploy and automation

**Goal by end of day:** a live Databricks App URL with all pages, Genie Q&A and a working monthly + on-demand refresh.

3.1 [ ] `ai_query` over form + stats → a short narrative per player in `gold.player_ai_summary`. Try 2–3 foundation models on a sample of 20 players first and pick the best (as in the video).
3.2 [ ] Interview and news summaries (sentiment, how the player feels, injuries, equipment changes…) and an AI tournament preview.
3.3 [ ] **Genie space** over the gold tables, with instructions and sample questions ("Who has the best TV average over the last 6 months?").
3.4 [ ] **Streamlit app**: pages as described in [DESIGN.md](DESIGN.md#app-design), developed locally (`streamlit run app/app.py`) against the SQL warehouse.
3.5 [ ] **Refresh data** button → `jobs.run_now` (the app's service principal gets CAN_MANAGE_RUN on the job).
3.6 [ ] Job `darts_refresh` with the full task chain `bronze → silver → quality → pi_model → performance_index → predict → ai_summaries`. Schedule: **daily during majors**, otherwise on demand (replaces the monthly cron).
3.7 [ ] Scheduled ingestion in **GitHub Actions**. Workflow `egress-check` (run 2026-10-25) proved that GitHub-hosted runners get 200 from Orakel (site + API), Wikipedia and Wikidata. `refresh.yml`: monthly cron + `workflow_dispatch` → `python -m ingestion.run --upload` (incremental) → `databricks jobs run-now darts_refresh`. Secrets: `DATABRICKS_HOST` + `DATABRICKS_TOKEN` (PAT or service principal). The "Refresh data" button in the app can dispatch this workflow.
3.8 [ ] Deploy: `databricks bundle deploy -t dev` + `databricks bundle run darts_app`.
3.9 [ ] README: link to the video, infrastructure overview, explanation of the Databricks limits, screenshots.

## After Day 3

- Live run for the **PDC World Championship 2027** once the draw is out (usually late November).
- Re-test Big-Stage Delta as more major matches accumulate (or with a longer backfill).

## Open questions

- App language: English only, or with a Czech toggle?
- Big-Stage Delta: keep the 80 % bootstrap rule (currently out at 73 %), or extend the backfill to 2021 to give it more data?
- Odds source: an API or a manual CSV?
- News/interviews source for the AI narratives (PDC news RSS?).
