# Darts Performance Analyzer

How strong is every top PDC darts player, who wins tomorrow's match, and who lifts the trophy? One transparent model
answers all three, refreshed automatically while the majors are played.

### **▶ [Open the app](https://darts-performance-analyzer.streamlit.app)** (no sign-in, works on a phone)

End-to-end data project in Python: ingestion from official APIs, a medallion lakehouse on **Databricks**, a
statistically tested model, tournament simulations, AI summaries and a **Streamlit** app, all automated with
**GitHub Actions**. Total cost: $0.

## One number, three answers

Everything in the app comes from one model. The **Performance Index** says how strong a player is; two PIs give the
chance of any match; simulating a draw match by match gives every player's chance in a tournament.

**1. How strong is a player? The Performance Index (0–10).**
PI = 10 × the chance to beat an average top-32 player in a typical match (first to 6 legs); 5 is a typical top-32
player. The model may only use inputs that stay fresh with the data it keeps receiving (major results and the Order
of Merit). Of 11 candidates, three survived a strict selection (correlation filter, significance, 80 % of bootstrap
samples): the **3-dart average over the last 20 major matches**, the **Order of Merit rank** and its **momentum** over
12 months. Weights come from a logistic regression on 2021–2026 matches, with no look-ahead. In a walk-forward test
on 1,653 major matches the PI predicts winners significantly better than the official PDC Order of Merit (log loss
0.638 vs 0.651, p < 0.001).

**2. Who wins this match? Head to head, straight from the two PIs.**
Each PI is a strength, s = ln(PI / (10 − PI)), and P(A beats B) = 1 / (1 + e^−(s_A − s_B)) in a typical match. The
chance is then converted to the match's format through the chance to win a single leg: longer matches favour the
stronger player, because luck evens out. A player with PI 7.0 against one with 5.0:

| Format | First to 6 legs | First to 11 legs | First to 18 legs | First to 4 sets | First to 7 sets |
|---|---|---|---|---|---|
| Chance to win | 70 % | 76 % | 82 % | 79 % | 86 % |

**3. Who wins the tournament? 10,000 simulations of the draw.**
Every match of the bracket gets its chance in that round's format; simulating the whole draw 10,000 times gives
each player's chance to reach every round and to win the title. During an event, played matches are fixed and only
the rest is simulated again (live bracket). Tested on 10 majors of 2025–2026, always predicted before the first
dart: the favourite won **70.6 %** of 388 matches, and the title favourite won 5 of the 10 events.

The full method, every tested predictor and the backtests: [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

### In the app

| Page | What it shows |
|---|---|
| **Tournament Overview** | Every major of the season: title chances, the bracket with each match's pre-match chance, players on the rise, upcoming matches; finished events show how the predictions did |
| **Player Profile** | Order of Merit rank and PI, the PI breakdown (the player against an average top-32 player in each input), an AI form summary with the latest PDC news, PI over time, last 5 matches, background, titles |
| **PI Leaderboard** | Rank by PI or by the Order of Merit; head to head for any two players in any format |
| **Methodology**, **Data & Health** | The model's inputs, weights and tests; data freshness and the health report |

## How it is built

```
GitHub Actions (daily while a major is running)
  ingestion/ (official APIs): Wikipedia (Order of Merit, majors' draws + results, players) · PDC news RSS
        │ upload
        ▼
Unity Catalog Volume ──► Databricks Job (serverless)
                         bronze → silver → quality gate → PI model → Performance Index
                                → tournament simulations + AI summaries (ai_query) → health report
                                                                         │
                                                darts_gold (Delta tables) ├──► Databricks App + Genie (private)
                                                                         │ snapshot (parquet)
                                                                         ▼
                              GitHub Actions publish-app → Streamlit Community Cloud (public app)
```

- **Lakehouse:** Databricks Free Edition with Unity Catalog, serverless jobs and an Asset Bundle for deploys;
  bronze (raw JSON) → silver (one player key across sources) → gold (model, index, predictions).
- **Model:** point-in-time features, logistic regression, bootstrap predictor selection, walk-forward validation
  against the official ranking; a refit goes live only if it passes the test.
- **AI:** short form summaries per player written by an LLM through `ai_query`, only from the numbers on the page
  and PDC news; a Genie space answers questions in plain English in the private Databricks app.
- **Runs unattended:** a daily check reads Wikipedia and refreshes only while a major is running; quality gates stop
  bad data before the gold tables, and a red health report (a source failed, a result missing) sends an e-mail.
  The app always shows the last good data.
- **Built for a free tier:** the compute quota shaped the design (refits every 28 days, reused backtests, the public
  app served from a snapshot so it needs no Databricks compute).

## Data sources

History was collected once; the ongoing refresh uses official APIs only.

| Source | Used for |
|---|---|
| Wikipedia / Wikidata (MediaWiki API, CC BY-SA) | **Ongoing:** Order of Merit, majors' draws and results with 3-dart averages, player background and free photos |
| PDC news (RSS) | **Ongoing:** latest news per player, input for the AI summaries |
| Darts Orakel | **History:** every PDC result with match stats, 2021 – Oct 2026 |
| [Mastercaller](https://mastercaller.com) (stats by iDarts) | **History:** results and 3-dart averages, Oct – Nov 2026 |

Non-commercial project. No betting odds: no free and legal source was available.

## Repo layout

| Path | Purpose |
|---|---|
| `ingestion/` | Source clients and the upload to the Volume |
| `src/notebooks/` | The job's notebooks (bronze → health) |
| `src/analytics/` | Features, Elo, model, Performance Index, bracket parsing, simulations, health checks, snapshot export |
| `app/` | Streamlit app (Databricks App and the public copy) |
| `databricks.yml`, `resources/` | Databricks Asset Bundle: job, app, secret scope |
| `.github/workflows/` | `refresh` (daily gate + refresh), `publish-app` (public copy), `start-app`, `egress-check` |
| `config/` | Majors, AI model, Genie space definition |
| `scripts/` | Local snapshot, smoke tests, CI helpers |
| `tests/` | Unit tests (`pytest`) |

## Documentation

| Document | For |
|---|---|
| **[docs/METHODOLOGY.md](docs/METHODOLOGY.md)** | How the numbers are made: the Performance Index (every tested predictor, the key test against the Order of Merit) and the tournament simulations with backtests |
| **[docs/MAINTENANCE.md](docs/MAINTENANCE.md)** | Running the project: links to start the full app and refresh by hand, how the refresh works, the failure runbook, tokens, deploy, setup from scratch, data model, decisions |

Inspired by the workflow in [I Built a Real Data App with Claude Code (and It Cost $0)](https://www.youtube.com/watch?v=3rgd2Xx5ceg).

## License

MIT
