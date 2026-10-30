# Tournament Predictions: Methodology

For every PDC major the app shows:

- **Season calendar**: all majors with dates, status (completed / in progress / upcoming) and winners.
- **Pre-tournament predictions**: each player's probability of reaching every round and of winning the title, once the draw is published.
- **Live bracket**: after each refresh, matches already played are fixed and the rest of the draw is simulated again.
- **Upcoming matches**: every scheduled match Orakel knows about, with both players' PI, the win probability and their head-to-head record.
- **Backtests**: for finished majors, what the model would have predicted before the event, compared with what happened.

Everything is built on the [Performance Index](PERFORMANCE_INDEX.md): the same strengths and the same head-to-head formula.

---

## 1. From two PIs to one match in a specific format

The PI model gives the probability that A beats B in a **typical match, first to 6 legs** (best of 11):

```
P_typical(A beats B) = 1 / (1 + e^−(S_A − S_B))        S = strength (PI Major for majors)
```

Majors are played in other formats: first to 10 legs at the World Matchplay, first to 7 sets in the World Championship final. The longer the match, the more luck evens out and the more often the stronger player wins. The conversion has two steps:

1. **Back out the leg probability.** Find the probability `p` of winning a single leg that reproduces `P_typical` in a race to 6 legs:
   ```
   P(win a race to n) = Σ_{k=0}^{n−1} C(n−1+k, k) · p^n · (1−p)^k
   ```
   (the player wins n units while the opponent wins k < n).
2. **Rebuild the format from legs.** A race to *n* legs uses the same formula. A set is a race to 3 legs, and a match in sets is a race to *n* sets with the set probability.

Example: a typical-match probability of 71.5 % (Littler vs an average top-32 player):

| Format | P(win) |
|---|---|
| First to 3 legs | 65 % |
| **First to 6 legs (typical)** | **71.5 %** |
| First to 10 legs (World Matchplay) | 77 % |
| First to 3 sets (World Championship round 1) | 77 % |
| First to 7 sets (World Championship final) | 87.5 % |

Simplifications: legs are treated as independent with the same probability, the advantage of throwing first is averaged out, and "two clear legs" in deciding legs or sets is ignored. See [Limitations](#limitations).

---

## 2. Strength of every player in the draw

| Player | Strength used | Share of a typical World Championship field |
|---|---|---|
| Tracked (top 150 of the prize-money ranking) | PI model strength (PI Major) | about 88 % |
| Not tracked, but has played tracked players | estimated from their Opponent-Weighted Elo, via a straight-line fit of strength on Elo across tracked players | about 8 % |
| No data at all (e.g. some international qualifiers) | 5th percentile of tracked players' strength | about 4 % |

Shares are from the World Championship 2026 draw: 113 / 10 / 5 of 128 players.

Players are matched from Wikipedia to Orakel by name, ignoring accents, case and punctuation.

**Which strengths, when:**
- **Pre-tournament and live predictions:** the current PI (latest refresh).
- **Backtests:** strengths as of the first day of the event, with the PI weights **refitted only on matches before that day**. The backtest never uses information from the tournament it predicts.

---

## 3. Simulating the draw

The draw comes from the event's Wikipedia page (parsed from the bracket templates, including each round's format). The simulation plays the whole draw **10,000 times**:

1. In each round, every match is decided at random with the probability from step 1 in that round's format.
2. Winners move on to their slot in the next round.
3. **Live mode:** a match that already has a result is not simulated; the real winner moves on.

Counting how often each player reaches each round gives **P(reach round)** and **P(title)**. A walkover counts as a win in the draw but is left out of backtests, because no match was played.

**Supported draws:** knockout draws of 2^n players without byes. That covers the World Championship from 2026 (128 players), the World Matchplay, the World Grand Prix, the European Championship, the World Series Finals and the Grand Slam knockout stage. A draw needs at least 16 players. Byes (empty first-round slots) are supported. Not supported yet: the 96-player World Championships up to 2025 (seeds start in round 2), the Grand Slam group stage, the Premier League (a league), the UK Open (Wikipedia only has the semi-finals as a bracket) and the Players Championship Finals sections layout (to be verified once the 2026 draw is out).

---

## 4. Upcoming matches

Orakel publishes scheduled matches once a draw or order of play is out. Each one gets a card:

- both players' **PI**, **PI Major**, **Effective Average**, **3-Dart Average (L30)** and **Form**
- **P(A wins)** in a typical match (and in the event's format inside a simulated draw)
- **head-to-head**: wins against each other in all matches since 2021

During majors the data is refreshed daily ("tournament mode"); otherwise on demand from the app.

---

## 5. Backtests

Every finished major with a supported draw is backtested automatically: strengths as of the event's first day, weights refitted on earlier matches only, and the full draw simulated *before* any match was played. Results are stored in `darts_gold.tournament_backtest_summary` and `darts_gold.tournament_backtest_matches` (run 2026-10-31, after the same-day ordering fix described in [PERFORMANCE_INDEX.md](PERFORMANCE_INDEX.md#no-look-ahead)).

**Ten majors, 388 matches (2025–2026):**

| Event | Matches | Favourite won | Log loss | Champion | Champion's pre-event title chance (rank) | Model's favourite |
|---|---|---|---|---|---|---|
| World Championship 2026 | 126 | 71 % | 0.556 | Luke Littler | 67.7 % (1) | Littler 67.7 % |
| European Championship 2026 | 31 | 58 % | 0.642 | Ross Smith | 6.7 % (4) | Littler 22.0 % |
| World Grand Prix 2026 | 31 | 74 % | 0.579 | Luke Humphries | 12.8 % (3) | Littler 34.0 % |
| World Series Finals 2026 | 31 | 71 % | 0.581 | Ross Smith | 2.8 % (8) | Littler 38.4 % |
| World Matchplay 2026 | 30 | 70 % | 0.599 | Luke Littler | 35.1 % (1) | Littler 35.1 % |
| Grand Slam 2025 (knockout stage) | 15 | 73 % | 0.565 | Luke Littler | 34.7 % (1) | Littler 34.7 % |
| European Championship 2025 | 31 | 58 % | 0.668 | Gian van Veen | 6.6 % (3) | Littler 36.3 % |
| World Series Finals 2025 | 31 | 68 % | 0.561 | Michael van Gerwen | 1.6 % (14) | Littler 26.9 % |
| World Grand Prix 2025 | 31 | 68 % | 0.562 | Luke Littler | 22.8 % (1) | Littler 22.8 % |
| World Matchplay 2025 | 31 | 74 % | 0.547 | Luke Littler | 27.5 % (1) | Littler 27.5 % |

**All 388 matches together:**

| | Round format | As typical matches |
|---|---|---|
| Pre-match favourite won | 68.8 % | 68.8 % |
| Log loss | **0.579** | 0.584 |
| Brier score | **0.198** | 0.200 |

Converting each match to its round's format improves both scores.

**Calibration (388 matches, 5 groups by the favourite's predicted chance):**

| Predicted | 55 % | 61 % | 67 % | 75 % | 88 % |
|---|---|---|---|---|---|
| Favourite actually won | 49 % | 61 % | 71 % | 81 % | 83 % |

Each group has about 78 matches, so ±5 points are within chance. The top group (88 % predicted, 83 % observed) suggests that very strong favourites in long formats are rated slightly too high, which fits the limitation below.

**Titles:** the model's favourite won 5 of the 10 events, against 3.45 expected wins from its title probabilities. So there is no sign of overconfidence at the title level yet, but ten events are too few to judge, and Littler's 67.7 % before the World Championship 2026 is a strong claim.

---

## Limitations

- **Strong favourites may be rated slightly too high in long formats.** Treating legs as independent assumes a player's level is the same in every leg. In reality players have good and bad days, so legs within a match are correlated and long matches favour the stronger player less than the formula says. For one match the effect is small (the backtest confirms the format conversion helps), but over 7 rounds it compounds. Planned fix: estimate a "day form" spread from the data and add it to the simulation. Bookmaker odds are not available as a benchmark (no free, legal source reachable from the Czech Republic), so validation uses baselines such as seeding.
- **Ten backtested events** are not enough to judge title probabilities. Each finished major with a supported draw adds a backtest automatically.
- **Throw advantage and "two clear legs"** are ignored.
- **Unsupported formats** (see section 3) have no simulation yet; their matches still get head-to-head cards.

---

## Data and code

| What | Where |
|---|---|
| Format conversion | [src/analytics/formats.py](../src/analytics/formats.py) |
| Draw parser (Wikipedia) | [src/analytics/bracket.py](../src/analytics/bracket.py) |
| Season calendar (Wikipedia infobox) | [src/analytics/calendar.py](../src/analytics/calendar.py) |
| Strengths, simulation, backtest | [src/analytics/tournament.py](../src/analytics/tournament.py), [src/analytics/pipeline.py](../src/analytics/pipeline.py) |
| Databricks notebook | [06_tournaments.py](../src/notebooks/06_tournaments.py) |
| Majors and their Wikipedia pages | [config/majors.yml](../config/majors.yml) |

| Gold table | Contents |
|---|---|
| `darts_gold.majors_calendar` | majors by season: dates, status, winner, whether a draw is available |
| `darts_gold.tournament_predictions` | per event and player: P(reach each round), P(title), strength, its source, mode (pre-tournament / live / backtest) |
| `darts_gold.tournament_draw_matches` | every match of every parsed draw: players, seeds, score, averages, winner, P(A wins) in the round's format |
| `darts_gold.tournament_backtest_matches` | every played match of finished events with its pre-tournament probability |
| `darts_gold.tournament_backtest_summary` | accuracy, log loss, Brier and how the champion was rated, per event |
| `darts_gold.upcoming_matches` | upcoming match cards |
