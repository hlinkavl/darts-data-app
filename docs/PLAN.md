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
| Day 2 | Analytics: Performance Index, prediction model, backtests | ✅ done (2026-10-28) |
| Day 3 | Backend robustness (health report, model promotion), GitHub Actions automation, AI layer | ⏳ next |
| Day 4 | Streamlit app, Genie, deploy (ready for the Grand Slam, 14 Nov) | ⬜ |

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

## Day 3: Backend robustness, automation and AI layer

**Goal by end of day:** a fully automatic refresh that runs without the Mac (GitHub Actions + Databricks Job), a green health report, and AI narratives in gold tables.

**Operational robustness first (agreed 2026-10-28):** unattended refreshes must fail loudly, keep the last good data and say what to do.

3.1 [ ] **Health report** `gold.health_report` (🟢/🟡/🔴 + recommended action per check): data freshness, empty or changed source datasets, draw parsed for every running major, name-matching rate in draws, possible new major in Orakel data ("add to config/majors.yml: …").
3.2 [ ] **Model promotion policy**: each refit creates a candidate version; it replaces the active version only if the predictor set is unchanged and test metrics are not worse. Otherwise the active version stays and the health report flags it.
3.3 [ ] **Failure notifications**: Databricks Job e-mail on failure, GitHub Actions failure e-mails.
3.4 [ ] **GitHub Actions `refresh.yml`**: `python -m ingestion.run --upload` (incremental) → `databricks jobs run-now darts_refresh`. Daily during majors (dates from `gold.majors_calendar`), otherwise on demand (`workflow_dispatch`, later the app button). Secrets `DATABRICKS_HOST` + `DATABRICKS_TOKEN`. Verified egress: GitHub runners reach Orakel and Wikipedia.
3.5 [ ] **AI narratives** with `ai_query`: short player assessments from form + stats → `gold.player_ai_summary`. Compare 2–3 foundation models on 20 players first (as in the video).
3.6 [ ] **News and interviews** from the official **PDC news RSS** (`pdc.tv/rss.xml`, decided 2026-10-28): 20 latest articles with full text, about 4–7 days of news. Ingest every article into bronze (deduplicated by link) so history builds up over time. AI summaries per player: how he feels, injuries, equipment changes, quotes. The app shows **only AI summaries with a link to the original article**, never the full text. Because the feed holds only the last 20 items, an on-demand refresh after a long pause can miss articles: the health report warns about such a gap ("news gap since …").
3.8 [x] **Odds: left out** (checked 2026-10-28, rule: only free sources via an API). odds-api.io has no free plan (from £49/month) and lists no darts outright markets. The Odds API (the-odds-api.com) has a free tier but does not cover darts. Scraping (e.g. Livesport) is excluded. So "players to watch" is based on the model only: title chances, rising form, a soft section of the draw. Re-check if a free darts odds API appears.
3.7 [ ] Improve Wikidata matching (76 % of tracked players) for player backgrounds.

How fixes happen: config-only issues (e.g. a new major) can be fixed by editing `config/majors.yml` on GitHub. Code issues (parser, source changes) are fixed in the repo with Claude Code and deployed with the bundle. Never edit code in the Databricks workspace, because `bundle deploy` overwrites it. Genie helps to diagnose (questions over the health report and gold tables), not to fix.

## Day 4: Streamlit app, Genie and deploy

**Goal by end of day:** a live Databricks App URL with all pages, Genie Q&A, the Refresh button and the health badge, ready for the **Grand Slam (14–22 Nov 2026)** as the first live event.

4.1 [ ] **Streamlit app** developed locally (`streamlit run app/app.py`) against the SQL warehouse; pages as in [DESIGN.md](DESIGN.md#app-design): Tournament Overview (calendar, predictions, live bracket, upcoming matches), Player Profile (PI, Effective Average, contributions, last 5, background, AI narrative, Big-Stage Delta as info), PI Leaderboard + head to head, Ask the data (Genie), Methodology (live from `pi_*` tables), Admin.
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
