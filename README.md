# Darts Performance Analyzer

End-to-end data app for **PDC darts**: pre-tournament predictions (first target: PDC World Championship 2027) and player profiles with a 0–10 **Performance Index**. Built in Python on **Databricks Free Edition** (Unity Catalog, serverless Jobs, AI Functions, Genie, Databricks Apps) with a **Streamlit** front end.

Inspired by the workflow in [I Built a Real Data App with Claude Code (and It Cost $0)](https://www.youtube.com/watch?v=3rgd2Xx5ceg).

> 🚧 Status: planning and setup done, development starts now.

## Features (planned)

- **Tournament Predictor**: Monte Carlo bracket simulation, P(title) per player, model vs. bookmaker odds, players to watch, AI tournament preview
- **Player Profiles**: last-5 form, background, AI narrative (form + interviews), Performance Index with a component breakdown
- **PI Leaderboard** and head-to-head comparison
- **Ask the data**: natural-language questions via Databricks Genie
- **Automated refresh**: monthly schedule + on-demand trigger (Databricks Jobs)

## Architecture

```
Sources → Python scrapers → UC Volume → bronze → silver → gold (Delta)
                                              ↓            ↓
                                     AI Functions     Genie space
                                              ↓            ↓
                                  Streamlit app (Databricks App, SQL warehouse)
```

Infrastructure details and the Free Edition limits are covered in [docs/DESIGN.md](docs/DESIGN.md) and [docs/PLAN.md](docs/PLAN.md#databricks-free-edition-limits-that-shape-the-design).

## Repo layout

| Path | Purpose |
|---|---|
| `docs/` | Plan, design, setup guide |
| `databricks.yml`, `resources/` | Databricks Asset Bundle (Job + App) |
| `app/` | Streamlit app (deployed as a Databricks App) |
| `ingestion/` | Source scrapers |
| `src/notebooks/`, `src/transform/` | Job notebooks and bronze/silver/gold transforms |
| `sql/queries/` | Saved SQL queries |
| `config/` | Performance Index weights and other settings |
| `scripts/` | Workspace bootstrap and helper scripts |

## Getting started

See [docs/SETUP.md](docs/SETUP.md).

## License

MIT
