# Darts Performance Analyzer

End-to-end data app for **PDC darts**: title chances for every major, a live bracket, and player profiles with a
transparent 0–10 **Performance Index (PI)**. Built in Python on **Databricks Free Edition** (Unity Catalog,
serverless Jobs, SQL warehouse, Databricks Apps) with a **Streamlit** front end, refreshed automatically by
**GitHub Actions**. Total cost: $0.

Inspired by the workflow in [I Built a Real Data App with Claude Code (and It Cost $0)](https://www.youtube.com/watch?v=3rgd2Xx5ceg).

**App:** https://darts-performance-analyzer-7474646547340845.aws.databricksapps.com (Databricks sign-in needed).
Outside majors the app is stopped to save compute: start it for 24 h with the
[start-app workflow](https://github.com/hlinkavl/darts-data-app/actions/workflows/start-app.yml) → **Run workflow**.

<!-- Screenshots: Tournament Overview, Player Profile, PI Leaderboard (added before the Grand Slam 2026) -->

## What it does

- **Tournament Overview**: every major of the season. Before and during an event: chance to win the title, the
  bracket with each match's pre-match chance (undecided spots show the most likely player), players on the rise,
  upcoming matches. Finished events show what the model predicted before the first dart (backtest).
- **Player Profile**: current PDC Order of Merit rank and PI, the **PI breakdown** (the player against an average
  top-32 player in each input), PI over time, last 5 matches, background from Wikipedia, titles.
- **PI Leaderboard**: rank by PI or by the Order of Merit, head-to-head chances in any format (legs or sets).
- **Methodology** and **Data & Health**: the model's weights and tests, data freshness and a health report.

## The Performance Index in one paragraph

PI = 10 × the chance to beat an average top-32 player in a typical match (first to 6 legs); 5 is a typical top-32
player. Four inputs survived a strict selection (correlation filter, significance, 80 % of bootstrap samples):
the 3-dart average over the last 30 matches, form (last 10 vs last 30), an opponent-weighted Elo rating and the
Order of Merit rank. Weights come from a logistic regression on matches between tracked players, with no
look-ahead. In a walk-forward test on 1,825 major matches the model predicts winners significantly better than the
PDC Order of Merit (log loss 0.628 vs 0.652, p < 0.001). Every tested and rejected predictor, and why, is in
[docs/PERFORMANCE_INDEX.md](docs/PERFORMANCE_INDEX.md); tournament simulations in
[docs/TOURNAMENT_PREDICTIONS.md](docs/TOURNAMENT_PREDICTIONS.md).

## Architecture

```
GitHub Actions (daily during majors, or by hand / from the app)
  ingestion/: Mastercaller results · Wikipedia (Order of Merit, draws, players) · PDC news RSS
        │ upload
        ▼
Unity Catalog Volume ──► Databricks Job darts_refresh (serverless)
                         bronze → silver → quality → PI model → Performance Index → tournaments → health
                                                                         │
                                                       darts_gold (Delta) │ SQL warehouse
                                                                         ▼
                                              Streamlit app (Databricks App)
```

Why ingestion runs on GitHub Actions: Free Edition limits outbound internet from Databricks compute, and the
scrapers are polite (one request every few seconds, identified User-Agent), which suits a small runner.

### Free Edition limits that shaped the design

- Serverless only, one 2X-Small SQL warehouse, up to 3 apps (stopped after 24 h), 5 concurrent job tasks.
- A **fair-use compute quota**: when it runs out, jobs, the warehouse and apps cannot start for a while. So the
  PI model is refit only every 28 days (otherwise only Elo is updated), backtests of finished majors are reused,
  the daily "is a major running?" check reads Wikipedia instead of the warehouse, and the app runs only during
  majors.

## Data sources

| Source | Used for | How |
|---|---|---|
| [Mastercaller](https://mastercaller.com) (stats by iDarts) | Results and 3-dart averages since Oct 2026 | Public pages, 1 request / 3 s |
| Darts Orakel | Results and match stats until 28 Oct 2026 | Free public API; access ended when the site blocked our client, its earlier data is kept |
| Wikipedia / Wikidata | Order of Merit (current and monthly history), majors' dates and draws, player background and free photos | Official APIs, CC BY-SA |
| PDC news (RSS) | News for AI summaries (planned) | Official feed |

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
| `config/` | Majors and Mastercaller series |
| `scripts/` | Local snapshot for app development, smoke tests, CI helpers |
| `docs/` | Plan, design, methodology, setup |
| `tests/` | Unit tests (`pytest`) |

## Getting started

Setup (Databricks CLI profile, bundle, GitHub secrets) is in [docs/SETUP.md](docs/SETUP.md). The short version:

```bash
make setup                                   # local venv
make deploy                                  # validate and deploy the bundle (job + app)
make refresh                                 # ingest + run the Databricks job
cd app && DARTS_DATA=local streamlit run app.py   # app on a local snapshot (scripts/build_local_snapshot.py)
```

## License

MIT
