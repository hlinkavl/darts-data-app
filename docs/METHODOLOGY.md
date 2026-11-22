# Methodology

One model gives three answers:

1. **How strong is a player?** The Performance Index (PI), 0–10.
2. **Who wins a match?** The head-to-head chance from two PIs, adjusted to the match length.
3. **Who wins a tournament?** 10,000 simulations of the draw.

All numbers are recomputed on every refit and stored in Databricks; the app's Methodology page shows them live.
This page describes model `v2026-11-22`.

**Contents:** [1. Performance Index](#1-performance-index) · [2. Head to head](#2-head-to-head) ·
[3. Tournaments](#3-tournament-predictions) · [Limitations](#limitations)

---

## 1. Performance Index

> **PI = 10 × the chance to beat an average top-32 player in a typical match** (first to 6 legs).

5.0 is an average top-32 player, 7.0 wins 70 % of matches against one, 3.0 wins 30 %. The "average top-32 player" is
the average profile of the 32 strongest players on that day.

### What the model learns from

Two different things, from two different sets of data:

| | What it is | Data |
|---|---|---|
| **The weights** | How much each input matters (the model's coefficients) | **All matches** between two tracked players since March 2021, at any PDC event: **15,930 matches**, of which 2,371 (15 %) on majors, about 55 % Players Championships, the rest European Tour, qualifiers and other events |
| **A player's numbers** | The inputs the weights are applied to: today for the current PI, and before every historical match for training | **3-dart average from the last 20 major matches**, plus the official **Order of Merit rank** and its change over 12 months |

So the weights are learned from all of history, while a player's current strength comes from major matches and
the ranking. The ranking itself is two years of prize money from all PDC events, so floor results still count
through it.

Why it is built this way: since November 2026 new results come only from the majors. Inputs computed from majors
stay up to date with every new result; inputs from all events would slowly go stale. The outcome of any match still
says something about the two players, so the weights keep using every match.

Sources: Darts Orakel (all matches, 2021 – 28 Oct 2026), Mastercaller (until 9 Nov 2026), then Wikipedia (majors).
"Tracked" means the 150 best players in the Order of Merit.

### What the PI is made of

Four inputs, from the long term to right now:

| | Input | Share of the index | In 3-dart-average points |
|---|---|---|---|
| Long-term record | **PDC Order of Merit rank** (two years of prize money) | 30 % | halving the rank number (#20 → #10) = 1.3 points |
| Trend | **Order of Merit momentum**, rank change over 12 months | 8 % | halving the rank number within a year = 0.5 points |
| Current level | **3-dart average on majors**, last 20 major matches | 48 % | 1 point = 1 point |
| Form right now | **Recent form on majors**: average of the last 3 major matches minus the last 20 | 14 % | 1 point = 0.3 points |

The four barely overlap (correlations of 0.25 or less, except rank and average at 0.77), so each adds its own
information: momentum is the trend of the ranking over a year, recent form how the player throws this week.

The World Grand Prix is left out of the average (it is double-in, which lowers everyone's average). A player needs
5 major matches to get a PI, so about 110 of the 150 tracked players have one.

**Effective Average** puts the whole strength into one familiar number: the average top-32 player's 3-dart average
plus each input's advantage converted into average points. The PI breakdown in a player's profile shows these rows.

### How the inputs were chosen

Twelve candidates were defined before testing. A candidate stays only if it passes three filters:

1. **Not a duplicate:** of two inputs measuring almost the same thing (correlation above 0.8), the better one stays.
2. **Significant and useful:** a positive effect (p < 0.05) that also improves predictions on unseen matches.
3. **Stable:** significant in at least 80 % of 500 resampled datasets.

| Candidate | Result |
|---|---|
| 3-dart average on majors, Order of Merit rank, Order of Merit momentum | **kept** |
| Recent form on majors (last 3 vs last 20) | **kept by a person's decision**, see below |
| Big-stage Elo, big-stage experience, major results points, best rank in 3 years | duplicates of a kept input |
| Form on majors (last 6 vs last 20), major quarter-finals | not significant |
| Major titles, time in the top 32 | negative effect next to the rank: the ranking lags, and momentum covers that |

**Recent form, an approved exception (22 Nov 2026).** The last 3 major matches against the last 20 is a real
effect (p < 0.000001 over all matches; 5 points above the usual level lift a 50 % chance to 53 %) and is stable in
98 % of resampled datasets. It missed filter 2 only by a tie: on the 2025 validation period the model predicted
exactly as well with it as without it. The stronger quarterly walk-forward test (2023–2026) shows a small but
significant gain on majors (+0.0019 in log loss, p = 0.02) and on all matches (+0.0016, p < 0.001), so it was added
by a documented decision rather than by the rules. It replaces the 6-match form, which it beats. A variant that counts only the last 60 days (older form set to 0) was weaker (+0.0014 on majors, 75 % stable): on average even an older recent form still tells something.

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
| **Majors** | 1,665 | log loss 0.637 | 0.651 | **PI significantly better** (p < 0.001) |
| All matches | 12,797 | 0.657 | 0.668 | PI significantly better (p < 0.001) |
| 2026 majors only | 411 | 0.627 | 0.632 | same direction, too few matches to be sure |

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

- the pre-match favourite won **70.1 %** of matches;
- adjusting to each round's format makes the chances more accurate (log loss 0.595 → 0.584);
- the title favourite won **6 of the 11** events.

<details>
<summary>Every event</summary>

| Event | Matches | Favourite won | Champion | Champion's chance before the event (rank) |
|---|---|---|---|---|
| World Championship 2026 | 126 | 75 % | Luke Littler | 48.6 % (1) |
| European Championship 2026 | 31 | 61 % | Ross Smith | 3.6 % (9) |
| World Grand Prix 2026 | 31 | 74 % | Luke Humphries | 15.7 % (2) |
| World Series Finals 2026 | 31 | 74 % | Ross Smith | 1.9 % (11) |
| World Matchplay 2026 | 30 | 73 % | Luke Littler | 27.5 % (1) |
| Players Championship Finals 2025 | 63 | 70 % | Luke Littler | 23.8 % (1) |
| Grand Slam 2025 (knockout stage) | 15 | 73 % | Luke Littler | 35.8 % (1) |
| European Championship 2025 | 31 | 58 % | Gian van Veen | 3.4 % (9) |
| World Series Finals 2025 | 31 | 65 % | Michael van Gerwen | 2.7 % (10) |
| World Grand Prix 2025 | 31 | 65 % | Luke Littler | 29.2 % (1) |
| World Matchplay 2025 | 31 | 71 % | Luke Littler | 29.8 % (1) |
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
