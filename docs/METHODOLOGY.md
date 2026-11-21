# Methodology

One model gives three answers:

1. **How strong is a player?** The Performance Index (PI), 0–10.
2. **Who wins a match?** The head-to-head chance from two PIs, adjusted to the match length.
3. **Who wins a tournament?** 10,000 simulations of the draw.

All numbers are recomputed on every refit and stored in Databricks; the app's Methodology page shows them live.
This page describes model `v2026-11-14`.

**Contents:** [1. Performance Index](#1-performance-index) · [2. Head to head](#2-head-to-head) ·
[3. Tournaments](#3-tournament-predictions) · [Limitations](#limitations)

---

## 1. Performance Index

> **PI = 10 × the chance to beat an average top-32 player in a typical match** (first to 6 legs).

5.0 is an average top-32 player, 7.0 wins 70 % of matches against one, 3.0 wins 30 %. The "average top-32 player" is
the average profile of the 32 strongest players on that day.

### What the model learns from

The model has two parts, and they use different data:

| | Data | Why |
|---|---|---|
| **The matches it learns from** (who won) | Every match between two tracked players since March 2021, at any PDC event: **15,930 matches**, of which 2,371 (15 %) on majors, about 55 % Players Championships, the rest European Tour, qualifiers and other events | Every result says something about the two players, and more matches give more reliable weights |
| **The inputs** (what it knows about each player before the match) | Computed from **major matches only**, plus the official Order of Merit | Since November 2026 new results come only from the majors. Inputs computed the same way over the whole history stay comparable with every new match |

Sources: Darts Orakel (all matches, 2021 – 28 Oct 2026), Mastercaller (until 9 Nov 2026), then Wikipedia (majors).
"Tracked" means the 150 best players in the Order of Merit.

### What the PI is made of

| Input | Share of the index | In 3-dart-average points |
|---|---|---|
| **3-dart average on majors**, last 20 major matches | 55 % | 1 point = 1 point |
| **PDC Order of Merit rank** | 35 % | halving the rank number (#20 → #10) = 1.3 points |
| **Order of Merit momentum**, rank change over 12 months | 10 % | halving the rank number within a year = 0.6 points |

The World Grand Prix is left out of the average (it is double-in, which lowers everyone's average). A player needs
5 major matches to get a PI, so about 110 of the 150 tracked players have one.

**Effective Average** puts the whole strength into one familiar number: the average top-32 player's 3-dart average
plus each input's advantage converted into average points. The PI breakdown in a player's profile shows these rows.

### How the inputs were chosen

Eleven candidates were defined before testing. A candidate stays only if it passes three filters:

1. **Not a duplicate:** of two inputs measuring almost the same thing (correlation above 0.8), the better one stays.
2. **Significant and useful:** a positive effect (p < 0.05) that also improves predictions on unseen matches.
3. **Stable:** significant in at least 80 % of 500 resampled datasets.

| Candidate | Result |
|---|---|
| 3-dart average on majors, Order of Merit rank, Order of Merit momentum | **kept** |
| Big-stage Elo, big-stage experience, major results points, best rank in 3 years | duplicates of a kept input |
| Form on majors, major quarter-finals | not significant |
| Major titles, time in the top 32 | negative effect next to the rank: the ranking lags, and momentum covers that |

<details>
<summary>The earlier model (31 Oct 2026, inputs from every event)</summary>

Before majors became the only new data, 19 inputs computed from all events were tested. Kept: 3-dart average over
the last 30 matches, Elo, form and the Order of Merit rank. Left out: first-9 average, checkout %, 180s, win rate,
experience, consistency, activity, head-to-head record and four "big-stage" measures. The strongest big-stage
measure, the average on stage minus floor events, missed the stability rule narrowly (79 % instead of 80 %). That
model beat the Order of Merit by more (+0.024 in log loss on majors), but its inputs would go stale without
results from every event.
</details>

### Does it work?

The key test: does the PI predict winners better than the official PDC Order of Merit? Both are refitted every
quarter since July 2023 on earlier matches only and predict the next quarter.

| Test | Matches | PI | Order of Merit | Result |
|---|---|---|---|---|
| **Majors** | 1,653 | log loss 0.638 | 0.651 | **PI significantly better** (p < 0.001) |
| All matches | 12,785 | 0.659 | 0.668 | PI significantly better (p < 0.001) |
| 2026 majors only | 399 | 0.624 | 0.630 | same direction, too few matches to be sure |

Log loss: lower is better. The probabilities are also honest: on 2026 matches never used for fitting, matches
predicted at 60 % are won about 60 % of the time, and so on.

### Model updates

The model is refitted every 28 days. A new fit replaces the active one only if it selects the same inputs, does not
predict worse, and no input's weight moves by more than 15 points. Otherwise the old model stays, so the PI does
not jump because of noise.

---

## 2. Head to head

Each PI is a strength, s = ln(PI / (10 − PI)), and the chance that A beats B in a typical match is
1 / (1 + e^−(s_A − s_B)). Two players with the same PI have 50 %.

Longer matches favour the stronger player, because luck evens out. The app converts the chance through the chance
to win a single leg. A player with PI 7.0 against one with 5.0:

| Format | First to 6 legs | First to 11 legs | First to 18 legs | First to 4 sets | First to 7 sets |
|---|---|---|---|---|---|
| Chance to win | 70 % | 76 % | 82 % | 79 % | 86 % |

---

## 3. Tournament predictions

**The draw** comes from the event's Wikipedia page, with each round's format. Every player gets a strength: tracked
players from their PI, others estimated from their Elo, and players without any data a low default.

**The simulation** plays the whole draw 10,000 times with each match's chance in its round's format. How often a
player reaches each round gives the chances shown in the app. During an event, played matches are fixed and only
the rest is simulated again.

**Covered:** knockout draws (World Championship from 2026, World Matchplay, World Grand Prix, European
Championship, World Series Finals, Grand Slam knockout stage, Players Championship Finals). **Not covered:** group
stages, the Premier League (a league), the UK Open draw and the 96-player World Championships up to 2025.

### Backtests

Every finished major is predicted again as if before its first dart: strengths and weights from earlier matches
only. Eleven majors of 2025–2026, 451 matches:

- the pre-match favourite won **70.3 %** of matches;
- adjusting to each round's format makes the chances more accurate (log loss 0.595 → 0.583);
- the title favourite won **6 of the 11** events.

<details>
<summary>Every event</summary>

| Event | Matches | Favourite won | Champion | Champion's chance before the event (rank) |
|---|---|---|---|---|
| World Championship 2026 | 126 | 74 % | Luke Littler | 43.3 % (1) |
| European Championship 2026 | 31 | 58 % | Ross Smith | 3.6 % (8) |
| World Grand Prix 2026 | 31 | 74 % | Luke Humphries | 16.2 % (2) |
| World Series Finals 2026 | 31 | 74 % | Ross Smith | 2.0 % (12) |
| World Matchplay 2026 | 30 | 77 % | Luke Littler | 23.3 % (1) |
| Players Championship Finals 2025 | 63 | 68 % | Luke Littler | 23.7 % (1) |
| Grand Slam 2025 (knockout stage) | 15 | 73 % | Luke Littler | 38.9 % (1) |
| European Championship 2025 | 31 | 58 % | Gian van Veen | 3.8 % (7) |
| World Series Finals 2025 | 31 | 68 % | Michael van Gerwen | 3.0 % (10) |
| World Grand Prix 2025 | 31 | 68 % | Luke Littler | 30.6 % (1) |
| World Matchplay 2025 | 31 | 74 % | Luke Littler | 30.1 % (1) |
</details>

---

## Limitations

- **Majors-only inputs** react to form only on the big stage; a player's floor results count only through the
  Order of Merit.
- **Long formats:** treating legs as independent slightly overrates heavy favourites over many legs, because players
  have good and bad days.
- **Eleven backtested events** are too few to judge title chances; every finished major adds one.
- **Only the top 150** are tracked; other players are rated only from their matches against them.
- Throwing first and "two clear legs" are ignored.
