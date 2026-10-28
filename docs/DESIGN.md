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
| bronze | `darts_bronze.raw` (Volume) | raw JSONL files: `raw/<source>/<run_date>/<dataset>.jsonl` |
| bronze | `orakel_rankings`, `orakel_events`, `orakel_matches`, `wiki_tournament_pages`, `wiki_player_background` | files loaded 1:1, plus `_run_date`, `_source_file`, `_ingested_at` |
| silver | `players` | `player_key` (Orakel ID, canonical), name, country, date of birth, 2-year prize money + rank, `is_tracked`, Wikidata nickname / image / intro |
| silver | `events` | `event_key`, tournament, dates, Orakel category, prize fund, event average, winner, `is_major` |
| silver | `majors` | the 10 majors from `config/majors.yml` |
| silver | `matches` | one row per match: date, event, round, category, winner/loser, score |
| silver | `player_matches` (+ view `player_matches_v`) | one row per player per match: opponent, won, score, points/darts, first-9 points/darts, checkouts hit/attempts, 180s; the view adds average, first-9 average, checkout % |
| silver | `rankings` | prize-money ranking snapshots, one per ingestion run |
| silver | `tournament_pages` | Wikipedia wikitext of WC pages (draws are parsed on Day 2) |
| silver | `news`, `odds` | *(planned, Day 2–3)* |
| gold | `player_form` | last 5/10 matches, trend |
| gold | `performance_index` | PI + components, `as_of_date` (history for backtests) |
| gold | `player_ai_summary` | AI narratives (form, interviews) |
| gold | `player_ratings` | Elo rating, P(win leg) |
| gold | `tournament_predictions` | event, player, P(round k), P(title), model vs. market |
| gold | `players_to_watch` | selection + reasoning |
| gold | `refresh_log` | time and status of each refresh |

---

## Performance Index (PI) 0–10.0

**PI = 10 × P(player beats an average top-32 player in a typical match).** Built in three steps (select predictors → regression weights → 0–10 scale). Full methodology: [PERFORMANCE_INDEX.md](PERFORMANCE_INDEX.md).

- Current predictors: **3-Dart Average (L30)**, **Form (L10 vs L30)**, **Opponent-Weighted Elo**. Big-Stage Delta (majors only) is tested on every refit and currently fails the bootstrap stability rule (73 % < 80 %).
- Per player: PI, PI Major (equal to PI while no majors-only predictor is selected), Effective Average, and the contribution of each predictor.
- Head to head: `P(A beats B) = 1 / (1 + e^−(S_A − S_B))` from the two strengths.
- **Majors** = the 10 televised events in [config/majors.yml](../config/majors.yml), keyed by Orakel `tournament_key` (Orakel's categories are not stable across years).

---

## Tournament Overview

For every major (first live test: World Championship 2027, 11 Dec 2026 – 3 Jan 2027):

1. **Pre-tournament predictions:** Monte Carlo simulation (10,000 runs) of the bracket. Match probabilities come from the PI strengths (PI Major), converted from a "typical match" to each round's format (sets/legs). Output: P(reach each round), P(title).
2. **Upcoming matches:** Orakel's free upcoming-matches feed (players, round, start time) plus the Wikipedia draw. Each match card shows PI vs. PI, win probability, Effective Average, form and the head-to-head record from `silver.matches`.
3. **Live bracket:** results already flow in through the player-matches API. After each refresh, played matches are fixed in the bracket and the rest is re-simulated.
4. **Players to watch:** model vs. bookmaker odds (if an odds source is found), rising form, soft section of the draw.
5. **Season view:** list of all majors in the season with dates, winners and the next upcoming major.

---

## Data sources and attribution

- **Darts Orakel** (dartsorakel.com): free public API only, never paywalled pages. Polite use: top 150 players, 1 request / 2 s, a cache, an identifying User-Agent. Credited as "Data: Darts Orakel" in the app.
- **Wikipedia / Wikidata**: CC BY-SA, credited in the app.
- Not used: DartsDatabase (its robots.txt disallows AI agents), pdc.tv (client-side rendered).

## Infrastructure and refresh

- A **Databricks Asset Bundle** (`databricks.yml`) keeps the Job and the App versioned in git. Deploy with `databricks bundle deploy`.
- **Job `darts_refresh`** (serverless): `bronze` → `silver` → `quality` → `pi_model` → `performance_index` (→ tournament predictions, AI summaries). Triggers:
  - **during majors: daily** ("tournament mode": upcoming-matches feed, the draw page and matches of players still in the event)
  - **otherwise on demand**: the **Refresh** button in the app (next to it: time of the last refresh), `make refresh`, or "Run now" in the UI
- **Ingestion** runs outside Databricks (Orakel blocks Databricks IPs): GitHub Actions or locally, then uploads to the Volume and triggers the Job.
- **Secrets**: locally the OAuth profile `darts` in `~/.databrickscfg` (outside the repo). GitHub secrets in Actions. The app uses its automatically created service principal.
