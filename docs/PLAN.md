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
 Sources (PDC, Darts Orakel, DartsDatabase, Wikipedia, news/RSS, odds)
        │  Python scrapers (ingestion/)
        ▼
 UC Volume  /Volumes/workspace/darts_bronze/raw/<source>/<date>/*.json|csv
        │  Databricks Job "darts_refresh" (serverless)
        ▼
 bronze (raw Delta)  →  silver (clean, unified player IDs)  →  gold (PI, form, predictions)
        │                                                    │
        │                                       AI Functions (ai_query) → narratives
        ▼                                                    ▼
 Genie space (NL questions)                Streamlit Databricks App (SQL warehouse 2X-Small)
```

**Why not Airflow:** Databricks handles the refresh on its own. A Job supports a cron schedule (monthly) and a "Run now" trigger from the UI, the CLI or the app. Airflow would need an always-on server, which costs money. Free Edition has no managed orchestrator besides Jobs.

**The one real risk:** serverless compute on Free Edition has **restricted outbound internet**. Only a whitelist of "trusted domains" is reachable, and that list is not published and differs by region. If the darts sites aren't reachable from Databricks, scraping moves to **GitHub Actions** (free, cron + `workflow_dispatch`, so monthly *and* on demand). The workflow uploads the files to the Volume and then triggers the Databricks Job for the transformations. Step 1.3 decides which way we go.

## Databricks Free Edition limits that shape the design

- **Serverless** compute only, and a single **2X-Small SQL warehouse**.
- **Up to 3 Databricks Apps**. An app **stops automatically after 24 h** and has to be restarted. That's fine for a demo, and GitHub Actions can restart it if needed.
- **Max 5 concurrent job tasks** and 1 active pipeline per type, so one Job with a few tasks is enough.
- **Restricted outbound internet** (see above).
- Fair-use quotas. Going over shuts compute off for the rest of the day (in extreme cases, the rest of the month). Data is kept.
- No SLA, non-commercial use only, and inactive accounts may be deleted.
- LinkedIn identity verification ("Verify identity") raises some limits. Recommended.

---

## Day 0: Admin (today)

- [x] Read the notes, pull the video transcript, write the plan and design
- [x] Install the Databricks CLI (`brew install databricks`, v1.22.1)
- [x] Scaffold the repo: `.gitignore`, `CLAUDE.md`, Asset Bundle skeleton
- [x] First commit + push to GitHub
- [ ] **(you)** Create the Databricks Free Edition account and workspace: https://www.databricks.com/learn/free-edition
- [ ] **(you)** `databricks auth login --host https://<workspace>.cloud.databricks.com --profile darts`
- [ ] **(you)** `databricks aitools install --agents claude-code --scope global`, then restart Claude Code
- [ ] Verify with `databricks current-user me -p darts`
- [ ] Run `scripts/bootstrap_databricks.sh` to create the `darts_bronze/silver/gold` schemas and the `raw` Volume
- [ ] (recommended) Verify identity via LinkedIn in the workspace

## Phase 1: Data foundation (day 1)

1.1 **Source inventory.** For each source check availability, structure, ToS and robots.txt:
   - PDC Order of Merit (ranking, prize money): pdc.tv
   - Match results + stats (average, 180s, checkout %): Darts Orakel, DartsDatabase
   - Player background (age, nationality, nickname, titles): Wikipedia
   - Tournament draw and bracket: Wikipedia tournament page / PDC
   - Interviews and news: PDC news / RSS
   - Long-term (outright) odds: check for an API (e.g. The Odds API, if it covers darts). Otherwise a manual CSV.

1.2 **Scrapers** in `ingestion/<source>.py`. Same interface for all (`fetch() -> list[dict]`), JSON output to `data/raw/` (local, gitignored), polite rate limits, caching.

1.3 **Egress test from Databricks.** A serverless notebook tries `requests.get` against every source. The result decides whether scraping runs in a Databricks Job or in GitHub Actions.

1.4 **Backfill:** history from at least 2023 to today (needed for form and big-stage history). Upload to the Volume via `databricks fs cp` / the SDK.

1.5 **Bronze → silver:** SQL/PySpark transforms in `src/transform/`. The key step is **unifying player IDs** across sources (fuzzy name matching, with `ai_query` for ambiguous cases) into `silver.players` and `silver.matches`.

## Phase 2: Analytics and the Performance Index (days 2–3)

2.1 Gold table `gold.player_form`: last 5/10 matches, W/L, average, trend.
2.2 Gold table `gold.player_stats_rolling`: rolling 3/6/12-month windows.
2.3 **Performance Index v1** following [DESIGN.md](DESIGN.md#performance-index-pi-0100). We tune the weights together and sanity-check on well-known players (the OoM top 10 should land at PI 8+).
2.4 PI backtest: does pre-tournament PI correlate with how players actually finished? (WC 2024, 2025, 2026)
2.5 Store key SQL as **saved queries** in Databricks (`sql/queries/`).

## Phase 3: Prediction model (days 3–4)

3.1 **Player rating:** leg-level Elo (weighted by recency and event type), or derived from PI.
3.2 Leg win probability → match win probability for the given format (best-of legs / sets) via dynamic programming.
3.3 **Monte Carlo bracket simulation** (10,000 runs) → `gold.tournament_predictions` (P(reach round), P(title)).
3.4 Comparison with odds: implied probability with the margin removed, value = model − market → **players to watch**.
3.5 Backtest on WC 2025 and 2026 (Brier score and log loss vs. the odds).

## Phase 4: AI layer (day 4)

4.1 `ai_query` over form + stats → a short narrative per player, stored in `gold.player_ai_summary`.
4.2 Interview and news summaries (sentiment, how the player feels, injuries, equipment changes…).
4.3 AI tournament preview (top favourites, dark horses, the toughest sections of the draw).
4.4 Try 2–3 foundation models on a sample of 20 players and pick the best (as in the video).
4.5 **Genie space** over the gold tables, with instructions and sample questions ("Who has the best TV average over the last 6 months?").

## Phase 5: Streamlit app (days 5–6)

5.1 Local development (`streamlit run app/app.py`) against the SQL warehouse via `databricks-sql-connector` / the SDK.
5.2 Pages as described in [DESIGN.md](DESIGN.md#app-design).
5.3 **Refresh data** button → `jobs.run_now` (the app's service principal gets CAN_MANAGE_RUN on the job).
5.4 Deploy as a Databricks App via `databricks bundle deploy -t dev` + `databricks bundle run darts_app`.

## Phase 6: Automation and wrap-up (days 6–7)

6.1 Job `darts_refresh`: tasks `ingest → bronze → silver → gold → predictions → ai_summaries`, scheduled for the **1st of each month at 06:00 Europe/Prague**, plus a manual run before big tournaments.
6.2 (if needed) GitHub Actions `refresh.yml`: monthly cron + `workflow_dispatch`, with secrets `DATABRICKS_HOST` / `DATABRICKS_TOKEN`.
6.3 README: link to the video, infrastructure overview, explanation of the Databricks limits, screenshots.
6.4 Live run for the **PDC World Championship 2027** once the draw is out (usually late November).

## Open questions for tomorrow

- App language: English only, or with a Czech toggle?
- Which events count as "big stage" (proposal in DESIGN.md)?
- Odds source: an API or a manual CSV?
- Where the scraping runs (Databricks Job vs. GitHub Actions) gets decided in step 1.3.
