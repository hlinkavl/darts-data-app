# Darts Performance Analyzer

End-to-end data app for **PDC darts**: a transparent 0–10 **Performance Index (PI)** for every top player, and from
it the chance of any head-to-head match and every player's chance to reach each round or win a major. Built in
Python on **Databricks Free Edition** (Unity Catalog, serverless Jobs, SQL warehouse, Databricks Apps) with a
**Streamlit** front end, refreshed automatically by **GitHub Actions**. Total cost: $0.

Inspired by the workflow in [I Built a Real Data App with Claude Code (and It Cost $0)](https://www.youtube.com/watch?v=3rgd2Xx5ceg).

## ▶ Open the app

| | |
|---|---|
| **Public copy** | **[darts-performance-analyzer.streamlit.app](https://darts-performance-analyzer.streamlit.app)**: for anyone, no sign-in, always on. Everything except "Ask the data"; updated after every refresh. |
| **Full app** | **[darts-performance-analyzer](https://darts-performance-analyzer-7474646547340845.aws.databricksapps.com)** (Databricks sign-in), with "Ask the data" (Genie). Start it first: **[▶ Start the app](https://github.com/hlinkavl/darts-data-app/actions/workflows/start-app.yml)** → **Run workflow** → **Run workflow** (green button). Ready in about 3 minutes, stops by itself after 24 h. |

[![start-app](https://github.com/hlinkavl/darts-data-app/actions/workflows/start-app.yml/badge.svg)](https://github.com/hlinkavl/darts-data-app/actions/workflows/start-app.yml)
[![refresh](https://github.com/hlinkavl/darts-data-app/actions/workflows/refresh.yml/badge.svg)](https://github.com/hlinkavl/darts-data-app/actions/workflows/refresh.yml)
[![publish-app](https://github.com/hlinkavl/darts-data-app/actions/workflows/publish-app.yml/badge.svg)](https://github.com/hlinkavl/darts-data-app/actions/workflows/publish-app.yml)

The Databricks app is stopped unless started: a running app costs more Free Edition quota than the daily data
refresh, which runs on its own during majors. Without GitHub access: Databricks → Compute → Apps →
darts-performance-analyzer → Start. The public copy runs on Streamlit Community Cloud from a snapshot of the
gold tables, so it uses no Databricks quota and stays up when the workspace is stopped.

## Documentation

| Document | Read it when |
|---|---|
| **[docs/MAINTENANCE.md](docs/MAINTENANCE.md)** | something broke, a token expires, you deploy a change, or you set the project up from scratch: how the refresh works, the failure runbook, common fixes, tokens, data model, decisions and known limits |
| **[docs/METHODOLOGY.md](docs/METHODOLOGY.md)** | you want to know how the numbers are made: the Performance Index (all tested predictors, the key test against the Order of Merit) and the tournament simulations with backtests |

## One number, three answers

Everything in the app comes from one model. The **Performance Index** says how strong a player is; two PIs give the
chance of any match; simulating a draw match by match gives every player's chance in a tournament.

**1. How strong is a player? The Performance Index (0–10).**
PI = 10 × the chance to beat an average top-32 player in a typical match (first to 6 legs); 5 is a typical top-32
player. New results come only from the majors (official APIs, see below), so the model may only use inputs that
stay fresh: computed from major matches, plus the Order of Merit. Of 11 candidates, three survived a strict
selection (correlation filter, significance, 80 % of bootstrap samples): the **3-dart average over the last 20 major
matches**, the **Order of Merit rank** and its **momentum** over 12 months. Weights come from a logistic regression on
2021–2026 matches between tracked players, with no look-ahead. In a walk-forward test on 1,653 major matches the PI
predicts winners significantly better than the PDC Order of Merit (log loss 0.638 vs 0.651, p < 0.001).

**2. Who wins this match? Head to head, straight from the two PIs.**
Each PI is a strength, s = ln(PI / (10 − PI)), and P(A beats B) = 1 / (1 + e^−(s_A − s_B)) in a typical match. The
chance is then converted to the match's format through the chance to win a single leg: longer matches favour the
stronger player, because luck evens out. A player with PI 7.0 against one with 5.0:

| Format | First to 6 legs | First to 11 legs | First to 18 legs | First to 4 sets | First to 7 sets |
|---|---|---|---|---|---|
| Chance to win | 70 % | 76 % | 82 % | 79 % | 86 % |

**3. Who wins the tournament? 10,000 simulations of the draw.**
Every match of the bracket gets its chance in that round's format; simulating the whole draw 10,000 times gives
each player's chance to reach every round and to win the title. Before the event this is the outlook; during it,
played matches are fixed and only the rest is simulated again (live bracket). Tested on 10 majors of 2025–2026,
always predicted before the first dart: the favourite won **70.6 %** of 388 matches, the round formats make the
probabilities more accurate (log loss 0.593 → 0.581), and the title favourite won 5 of the 10 events.

How each step works, and its limits (players without a PI get a strength estimated from their Elo; independent legs
slightly favour heavy favourites in long formats): [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

### Where to find it in the app

| Page | What it shows |
|---|---|
| **Tournament Overview** | Every major of the season: title chances, the bracket with each match's pre-match chance (undecided spots show the most likely player), players on the rise, upcoming matches; finished events show the backtest |
| **Player Profile** | Order of Merit rank and PI, the PI breakdown (the player against an average top-32 player in each input), an AI form summary with the latest PDC news, PI over time, last 5 matches, background, titles |
| **PI Leaderboard** | Rank by PI or by the Order of Merit; head to head for any two players in any format |
| **Ask the data** | Questions in plain English, answered by a Databricks Genie space with the SQL behind the answer (Databricks app only) |
| **Methodology**, **Data & Health** | The model's inputs, weights and tests; data freshness, the health report and a Refresh button |

## Architecture

```
GitHub Actions (daily during majors, or by hand / from the app)
  ingestion/ (official APIs): Wikipedia (Order of Merit, majors' draws + results, players) · PDC news RSS
        │ upload
        ▼
Unity Catalog Volume ──► Databricks Job darts_refresh (serverless)
                         bronze → silver → quality → PI model → Performance Index
                                → tournaments + AI summaries (ai_query) → health
                                                                         │
                                                       darts_gold (Delta) │ SQL warehouse
                                                                         ▼
                                              Streamlit app (Databricks App) + Genie space
                                                                         │ health task exports a snapshot (parquet)
                                                                         ▼
                              GitHub Actions publish-app → branch public-app → Streamlit Community Cloud (public)
```

Why ingestion runs on GitHub Actions: Free Edition limits outbound internet from Databricks compute. The clients
are polite (identified User-Agent, one request per second or slower), which suits a small runner.

### Free Edition limits that shaped the design

- Serverless only, one 2X-Small SQL warehouse, up to 3 apps (stopped after 24 h), 5 concurrent job tasks.
- A **fair-use compute quota**: when it runs out, jobs, the warehouse and apps cannot start for a while. So the
  PI model is refit only every 28 days (otherwise only Elo is updated), backtests of finished majors are reused,
  the daily "is a major running?" check reads Wikipedia instead of the warehouse, and the app runs only when
  started by hand (running all day it took about 3 DBU a day, twice the daily refresh; measured Nov 2026).

### Running without anyone watching

- **Automatic during majors:** a daily GitHub Actions check reads Wikipedia; while a major runs it ingests and runs
  the job (~6 min), then publishes the new snapshot to the public copy. Outside majors nothing runs. The Databricks
  app is started by hand (start-app workflow) when needed.
- **Fails loudly, never shows wrong numbers:** sources are fetched independently, hard quality checks stop the job
  before the gold tables, a refit is activated only if it passes the test, and a red health report (a source failed,
  or a draw match still without a result 2 days after its round) fails the job and sends an e-mail. The app keeps
  the last good data.
- **Needs a person** only when the outside world changes (a source changes its page, a new tournament format) and
  for the yearly token renewal (next: Databricks token on 9 Nov 2027). Runbook: [docs/MAINTENANCE.md](docs/MAINTENANCE.md).

## Data sources

Historical data was collected once; the ongoing refresh uses official APIs only.

| Source | Used for | How |
|---|---|---|
| Wikipedia / Wikidata | **Ongoing:** Order of Merit (current and monthly history), majors' dates, draws and results with 3-dart averages, player background and free photos | Official MediaWiki / Wikidata APIs, CC BY-SA |
| PDC news (RSS) | **Ongoing:** latest news per player, input for the AI form summaries | Official feed |
| Darts Orakel | **History:** every PDC result with match stats, 2021 – 28 Oct 2026 | Free public API; ended when the site blocked our client, its earlier data is kept |
| [Mastercaller](https://mastercaller.com) (stats by iDarts) | **History:** results and 3-dart averages, Oct – 9 Nov 2026 | Public pages; ended when the site started refusing our cloud runners, not worked around |

Non-commercial project. No betting odds: no free and legal source was available.

## Repo layout

| Path | Purpose |
|---|---|
| `ingestion/` | Source clients and the upload to the Volume (`python -m ingestion.run --upload`) |
| `src/notebooks/` | The job's notebooks (bronze → health) |
| `src/analytics/` | Features, Elo, model, Performance Index, bracket parsing, simulations, health checks |
| `app/` | Streamlit app (deployed as a Databricks App) |
| `databricks.yml`, `resources/` | Databricks Asset Bundle: job, app, secret scope |
| `.github/workflows/` | `refresh` (daily gate + refresh), `start-app`, `egress-check` |
| `config/` | Majors, Mastercaller series (history), AI model, Genie space definition |
| `scripts/` | Local snapshot for app development, smoke tests, CI helpers |
| `docs/` | Maintenance (runbook) and methodology |
| `tests/` | Unit tests (`pytest`) |

## Getting started

Full setup, deploy and test steps: [docs/MAINTENANCE.md](docs/MAINTENANCE.md#5-develop-test-deploy). The short version:

```bash
make setup                                   # local venv
make deploy                                  # validate and deploy the bundle (job + app)
make refresh                                 # ingest + run the Databricks job
cd app && DARTS_DATA=local streamlit run app.py   # app on a local snapshot (scripts/build_local_snapshot.py)
```

## License

MIT
