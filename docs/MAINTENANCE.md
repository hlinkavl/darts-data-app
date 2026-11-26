# Maintenance

Where to find things, how to start the private app, and what to do when something breaks. Code changes are made
with Claude Code in this repository; this page does not repeat technical commands.

**Contents:** [Links](#links) · [Databricks](#where-to-find-things-in-databricks) ·
[Daily refresh](#how-the-daily-refresh-works) · [When something breaks](#when-something-breaks) ·
[Tokens](#tokens) · [Data model](#data-model) · [Decisions](#decisions-and-limits) · [Setup](#setup-from-scratch)

## Links

| What | Where |
|---|---|
| Public app | [darts-performance-analyzer.streamlit.app](https://darts-performance-analyzer.streamlit.app) (always on; admin: [share.streamlit.io](https://share.streamlit.io)) |
| Private app (with "Ask the data") | [darts-performance-analyzer](https://darts-performance-analyzer-7474646547340845.aws.databricksapps.com), Databricks sign-in |
| **Start the private app** | GitHub: [start-app](https://github.com/hlinkavl/darts-data-app/actions/workflows/start-app.yml) → **Run workflow** → **Run workflow**. Ready in ~3 min, stops by itself after 24 h. |
| Refresh the data now | GitHub: [refresh](https://github.com/hlinkavl/darts-data-app/actions/workflows/refresh.yml) → **Run workflow** (runs by itself every day during majors) |
| Republish the public app | GitHub: [publish-app](https://github.com/hlinkavl/darts-data-app/actions/workflows/publish-app.yml) → **Run workflow** (runs by itself after every refresh) |

[![refresh](https://github.com/hlinkavl/darts-data-app/actions/workflows/refresh.yml/badge.svg)](https://github.com/hlinkavl/darts-data-app/actions/workflows/refresh.yml)
[![publish-app](https://github.com/hlinkavl/darts-data-app/actions/workflows/publish-app.yml/badge.svg)](https://github.com/hlinkavl/darts-data-app/actions/workflows/publish-app.yml)
[![start-app](https://github.com/hlinkavl/darts-data-app/actions/workflows/start-app.yml/badge.svg)](https://github.com/hlinkavl/darts-data-app/actions/workflows/start-app.yml)

The private app is off by default: running all day it costs about 3 DBU, twice the daily refresh, and the Free
Edition quota is limited. The public app needs no Databricks compute at all.

## Where to find things in Databricks

Workspace: [dbc-2318ef7e-ac1e.cloud.databricks.com](https://dbc-2318ef7e-ac1e.cloud.databricks.com)

| What | Where |
|---|---|
| Tables (browse, columns, sample rows) | **Catalog** → `workspace` → [darts_silver](https://dbc-2318ef7e-ac1e.cloud.databricks.com/explore/data/workspace/darts_silver) (clean data) or [darts_gold](https://dbc-2318ef7e-ac1e.cloud.databricks.com/explore/data/workspace/darts_gold) (index, predictions, health) |
| Raw downloaded files and the public app's snapshot | **Catalog** → `darts_bronze` → Volumes → [raw](https://dbc-2318ef7e-ac1e.cloud.databricks.com/explore/data/volumes/workspace/darts_bronze/raw) |
| Your own queries | [SQL Editor](https://dbc-2318ef7e-ac1e.cloud.databricks.com/sql/editor), warehouse "Serverless Starter Warehouse" (starts by itself, stops after 10 min) |
| Refresh runs (what ran, what failed) | **Jobs & Pipelines** → [darts_refresh](https://dbc-2318ef7e-ac1e.cloud.databricks.com/jobs/685270245201923) |
| The private app (start, stop, logs) | **Compute** → **Apps** → [darts-performance-analyzer](https://dbc-2318ef7e-ac1e.cloud.databricks.com/apps/darts-performance-analyzer) |
| "Ask the data" space | **Genie** → [Darts](https://dbc-2318ef7e-ac1e.cloud.databricks.com/genie/rooms/01f1ddf6938b1cb19ccfe38d51512b61) |
| Health of the data | App → **Data & Health**, or table `darts_gold.health_report` |
| Quota usage | SQL Editor, table `system.billing.usage` (usage per day and product) |

## How the daily refresh works

1. Every night at 01:17 Prague time GitHub checks the majors' Wikipedia pages (GitHub often starts it a few hours
   late). It works during a major, the day before it and the day after it (for the final's result); otherwise it
   stops within a minute, with no Databricks cost. If the end of a major was missed, it catches up the next night.
2. Then it downloads the new data (Wikipedia, PDC news) and uploads it to Databricks.
3. The Databricks job (~6 min; up to ~45 min the day after a major) processes it: bronze → silver → quality check → model → index → tournaments and AI
   summaries → health report. The model is refitted only every 28 days, to save quota.
4. GitHub then publishes the new data to the public app.

## When something breaks

A failed refresh sends an e-mail (from GitHub and from Databricks). The apps keep showing the last good data, so
nothing wrong is ever shown.

1. Open **Data & Health** in the app: the red check says what broke and what to do.
2. **"The Databricks workspace is asleep"** (or "Triggering new runs … disabled temporarily"): the Free Edition
   workspace sleeps after about 4–5 days without anyone signing in through the browser; the refresh itself does not
   count. Sign in to Databricks (any page wakes it), then run the refresh again from GitHub. Two and three days before
   every major the refresh checks this and e-mails you, so you can sign in in time. **During a long major (the World
   Championship) sign in every few days.**
3. A one-off problem (timeout, quota: "try again later"): wait and run the refresh again from GitHub.
4. Anything else: open Claude Code in this repository, paste the e-mail or the health message and ask for a fix.
5. A source blocks us (HTTP 401, 403, 418): don't work around it; look for another official source.

| Typical problem | What it means |
|---|---|
| Draw missing for a running major | Wikipedia uses a new bracket layout; the parser needs to learn it |
| Overdue results (red) | A match has no result 2 days after its round: usually the same as above |
| Tracked players without results | A name is spelled differently between sources; an alias fixes it |
| A new major in the calendar | It needs to be added to the list of majors |
| Refit not activated | The new model did not pass the test; the previous one stays, nothing to do unless it repeats |
| "timed out" in the GitHub e-mail | GitHub stopped waiting, but the job may still have finished: check the run in Databricks (darts_refresh); if it succeeded, nothing to do |
| Public app out of date | Run publish-app; if the app itself is down: share.streamlit.io → the app → Reboot |

## Tokens

| Token | Used for | Expires | Where to renew |
|---|---|---|---|
| Databricks token "github-actions" | GitHub refresh and start-app | **9 Nov 2027** | Databricks → Settings → Developer → Access tokens → new token (365 days); then GitHub → repo → Settings → Secrets → Actions → `DATABRICKS_TOKEN` → Update |
| GitHub token "darts-app-refresh" | Refresh button in the private app | about Nov 2027 ([check](https://github.com/settings/personal-access-tokens)) | Regenerate on GitHub, then ask Claude to store it in the Databricks secret scope `darts` (key `github_token`) and restart the app |

An expired token shows up as a failed refresh. Renew a week ahead.

## Data model

Catalog `workspace`, three schemas:

| Layer | Main tables |
|---|---|
| `darts_bronze` | raw data as downloaded, one table per source |
| `darts_silver` | `players`, `matches`, `player_matches` (one row per player and match, with names), `rankings`, `events`, `upcoming_matches` |
| `darts_gold` | `performance_index` (current and monthly history), `pi_coefficients`, `pi_benchmark`, `tournament_predictions`, `tournament_draw_matches`, `tournament_backtest_summary`, `player_narratives`, `player_news`, `health_report` |

## Decisions and limits

- **Sources (14 Nov 2026):** official APIs only. Darts Orakel and Mastercaller blocked automated access, so their
  data is one-time history; blocks are never worked around. Since then only majors' knockout matches are added.
- **Model (14 Nov 2026):** only inputs that stay fresh with majors-only data: average on majors, Order of Merit rank
  and its momentum. **22 Nov 2026:** recent form (last 3 major matches vs the last 20) added by an approved
  exception: tied on the validation rule, significant in the walk-forward test. Details: [Methodology](METHODOLOGY.md).
- **Public app (20 Nov 2026):** Databricks apps always need a sign-in, so the public app runs on Streamlit Community
  Cloud from a daily snapshot. "Ask the data" stays in the private app only.
- **Not covered:** group stages (Grand Slam: predictions start from the last 16), the Premier League (a league), the
  UK Open draw and the 96-player World Championships up to 2025.
- **Free Edition limits:** one small SQL warehouse, apps stop after 24 h, a fair-use compute quota, and the
  workspace sleeps after ~4–5 days without a browser sign-in (seen 14 and 26 Nov 2026).
- **AI summaries:** Qwen3 Next 80B, chosen on 11 Nov 2026 from three models.

## Setup from scratch

What a new setup needs (Claude Code can do the technical steps from this repository):

1. A Databricks Free Edition workspace and a GitHub repository with this code.
2. GitHub secrets `DATABRICKS_HOST` and `DATABRICKS_TOKEN`.
3. The job, the app and the Genie space deployed from the repository's bundle; read access for the app.
4. First data load and a first refresh.
5. The public app: run publish-app once, then on share.streamlit.io create an app from branch `public-app`, file
   `app/app.py`, Python 3.12.
