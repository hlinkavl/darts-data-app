# Darts Performance Analyzer: Design

## App design

A Streamlit app deployed as a Databricks App. Navigation sits in the left sidebar, with the tournament or player picker at the top. Data is read from the gold tables through the SQL warehouse.

### Pages

**1. 🏆 Tournament Predictor** (home page)
```
┌──────────────────────────────────────────────────────────────────┐
│ [PDC World Championship 2027 ▾]   Data as of: 2026-12-01  ⟳ Refresh │
├───────────────────────────────┬──────────────────────────────────┤
│ Favourites, P(title)          │ Players to watch                 │
│ 1. L. Littler      31.2 %  ▇▇ │ • Player X: model 6 % vs mkt 2 % │
│ 2. L. Humphries    14.8 %  ▇  │ • Player Y: form ↑, soft section │
│ …                             │                                  │
├───────────────────────────────┴──────────────────────────────────┤
│ Interactive bracket: P(advance) per round, color = probability   │
├──────────────────────────────────────────────────────────────────┤
│ Model vs. odds: implied probability, difference, value          │
├──────────────────────────────────────────────────────────────────┤
│ 🤖 AI tournament preview: favourites, dark horses, toughest      │
│    section of the draw                                           │
└──────────────────────────────────────────────────────────────────┘
```
*(The numbers in the mockups are placeholders.)*

**2. 👤 Player Profile**
```
┌──────────────────────────────────────────────────────────────────┐
│ 🔎 [search player]                                               │
│ Name "Nickname"  🇬🇧  age · OoM #3 · titles              PI  8.7 │
├───────────────────────────────┬──────────────────────────────────┤
│ Form: W W L W W               │ PI breakdown (radar / bar)       │
│ last 5 matches: opponent,     │ Form · Big Stage · Scoring ·     │
│ score, average, event         │ Finishing · Results              │
├───────────────────────────────┴──────────────────────────────────┤
│ Average trend (12 months), TV vs. floor                          │
├──────────────────────────────────────────────────────────────────┤
│ 🤖 Narrative: what's working, what isn't, what he says in       │
│    interviews                                                    │
├──────────────────────────────────────────────────────────────────┤
│ Background: career, biggest wins · outright odds for the WC     │
└──────────────────────────────────────────────────────────────────┘
```

**3. 📊 Performance Index leaderboard**: every player with their PI, filters (country, OoM top N), a PI-over-time sparkline and a head-to-head comparison of two players.

**4. 💬 Ask the data (Genie)**: chat over the gold tables through the Genie Conversation API. Shows the answer plus the generated SQL.

**5. 📖 Methodology**: a public, user-friendly write-up of the PI and the prediction model (this document).

**6. ⚙️ Admin** (in the sidebar): time of the last refresh, status of the last job run, and a *Refresh now* button.

### Visual style
Dark theme with accent colors taken from a dartboard (red / green), large PI numbers, Plotly charts. Usable on mobile (Streamlit `layout="wide"` with columns that wrap).

---

## Data model (Unity Catalog)

Catalog `workspace` (the Free Edition default), three schemas:

| Layer | Table | Contents |
|---|---|---|
| bronze | `darts_bronze.raw` (Volume) | raw JSON/CSV files by source and download date |
| bronze | `orakel_matches`, `oom_rankings`, `wiki_players`, `wiki_brackets`, `news_articles`, `odds_outrights` | sources loaded 1:1, plus `_ingested_at` and `_source_file` |
| silver | `players` | `player_id`, name, nickname, country, date of birth, aliases per source |
| silver | `tournaments` | `tournament_id`, name, year, category (major / European Tour / Players Championship…), format, `is_big_stage` |
| silver | `matches` | `match_id`, date, event, round, players, score, average, 180s, checkout %, format |
| silver | `rankings` | Order of Merit snapshots |
| silver | `news` | article, players mentioned, date |
| silver | `odds` | outright odds, implied probability with the margin removed |
| gold | `player_form` | last 5/10 matches, trend |
| gold | `performance_index` | PI + components, `as_of_date` (history for backtests) |
| gold | `player_ai_summary` | AI narratives (form, interviews) |
| gold | `player_ratings` | Elo rating, P(win leg) |
| gold | `tournament_predictions` | event, player, P(round k), P(title), model vs. market |
| gold | `players_to_watch` | selection + reasoning |
| gold | `refresh_log` | time and status of each refresh |

---

## Performance Index (PI) 0–10.0

> v1 proposal, to be tuned. The idea is that each component is a player's **percentile** within a reference group (the PDC Order of Merit top 128), so every component is on the same scale. Weights are configurable in `config/pi_weights.yml`.

| Component | Weight | Metric | Window |
|---|---|---|---|
| **Form** | 30 % | 3-dart average over the last 10 matches, exponentially weighted by recency (half-life ~30 days), adjusted for opponent strength | 3 months |
| **Big Stage** | 25 % | Win rate + average at TV / major events, plus a "clutch delta" = TV average − floor average | 24 months |
| **Scoring** | 15 % | 180s per leg, average, first-9 average | 6 months |
| **Finishing** | 15 % | Checkout %, share of 100+ checkouts | 6 months |
| **Results** | 15 % | Order of Merit position (2-year prize money), titles, finals | 24 months |

**Calculation**

1. For each metric, compute the percentile `p ∈ [0,1]` within the reference group.
2. **Small-sample shrinkage**: `p_adj = (n·p + k·0.5) / (n + k)`, where `n` = matches in the window and `k` ≈ 5. A player with only a few matches gets pulled toward the middle.
3. `PI = 10 × Σ(wᵢ · p_adjᵢ)`, rounded to one decimal place.
4. Keep the history (`as_of_date`) so we can chart the trend and run backtests.

**Big-stage events (proposal):** World Championship, World Matchplay, World Grand Prix, Grand Slam, Players Championship Finals, UK Open, Masters, Premier League, European Championship, World Series Finals.

**Validation:** (a) sanity check: the current world elite should score PI 8.5+; (b) backtest: does a higher pre-tournament PI predict a better finish (Spearman correlation on WC 2024–2026)?

---

## Tournament prediction model

1. **Leg-level Elo** built from `silver.matches`: every leg counts as a "game", with a higher K-factor for big-stage events and decay for inactive players. Alternative or blend: logistic regression on PI and the difference in averages.
2. `p_leg(A vs B)` → **P(win match)** for the specific format (best-of-N legs, or sets made of legs) via dynamic programming. At the WC the format changes by round.
3. **Monte Carlo**: 10,000 simulations of the bracket (draw from `wiki_brackets`) → P(each round), P(title).
4. **Market vs. model**: implied probability from outright odds (overround normalized), then `value = p_model − p_market`. "Players to watch" combines value, improving form and a soft section of the draw.
5. **Backtest** on WC 2025/2026: Brier score and log loss against the odds.

---

## Infrastructure and refresh

- A **Databricks Asset Bundle** (`databricks.yml`) keeps the Job and the App versioned in git. Deploy with `databricks bundle deploy`.
- **Job `darts_refresh`** (serverless): `ingest` → `transform_silver` → `build_gold` → `predict` → `ai_summaries`. Triggers:
  - automatic: cron `0 0 6 1 * ?` (1st of each month, 06:00 Europe/Prague)
  - on demand: button in the app, `databricks bundle run darts_refresh`, or "Run now" in the UI
- **Fallback if egress is blocked**: GitHub Actions `.github/workflows/refresh.yml` (cron + `workflow_dispatch`) runs the scrapers, uploads the files to the Volume, then triggers the Job without the `ingest` task.
- **Secrets**: locally the OAuth profile `darts` in `~/.databrickscfg` (outside the repo). GitHub secrets in Actions. The app uses its automatically created service principal.
