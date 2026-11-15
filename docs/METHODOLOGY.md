# Methodology

How the app's numbers are made. One model gives three answers:

1. **How strong is a player?** The 0–10 Performance Index ([Part 1](#part-1-performance-index-pi)).
2. **Who wins this match?** Two PIs give the head-to-head chance, converted to the match's format in legs or sets ([How to read the PI](#how-to-read-the-pi), [Part 2, section 1](#part-2-tournament-predictions)).
3. **Who wins the tournament?** 10,000 simulations of the draw, match by match, give every player's chance to reach each round and to win the title, before and during the event; checked on 10 past majors ([Part 2](#part-2-tournament-predictions)).

## Part 1: Performance Index (PI)

The Performance Index rates every tracked PDC player on a **0–10 scale**:

> **PI = 10 × the probability that the player beats an average top-32 player in a typical match.**

A PI of 7.0 means a 70 % chance against a typical top-32 opponent. A PI of 5.0 means the player *is* a typical top-32 player. A PI of 2.0 means a 20 % chance. Because the scale is a probability, any two PIs can be turned into a head-to-head prediction.

**Does it work?** The PI predicts match winners significantly better than the official PDC Order of Merit, also **on majors** (1,653 major matches predicted ahead of time, log loss 0.638 vs 0.651, p < 0.001). See [the current model](#the-current-model-inputs-from-the-majors-only-since-14-nov-2026).

The current model and its numbers are in the next section. The sections after it document the full study of 19 candidate predictors from 31 Oct 2026 (data until 28 Oct 2026, inputs from every event): it still explains why each statistic was kept or dropped, but its weights and test results describe the previous model. All numbers are recomputed on every refit and stored in Databricks (tables at the end); the app's *Methodology* page reads those tables.

---

### The current model: inputs from the majors only (since 14 Nov 2026)

**Why it changed.** Since 10 November 2026 new results come only from the majors, through the official Wikipedia API (scraped sites blocked automated clients: Darts Orakel on 30 Oct, Mastercaller on 11 Nov 2026; their data stays as history). The previous inputs, the 3-dart average and form over a player's last 30 and 10 matches of *any* event and an Elo from all matches, would slowly turn into "the last 30 matches over a year or two" and no longer mean what the model was trained on. So the model may only use inputs that new data keeps fresh, and it is trained with the inputs computed exactly that way over the whole history:

All eleven candidates were fixed before testing (the last six added on 14 Nov 2026: recent results on majors and long-term quality).

| Candidate | Definition |
|---|---|
| `avg_major` – 3-Dart Average on Majors (L20) | Points ÷ darts × 3 over the last 20 matches on majors (at least 5). The World Grand Prix is left out: it is double-in, which lowers everyone's average (87.4 there vs 92.6–97.6 at the other majors, 2021–2026) |
| `form_major` – Form on Majors (L6 vs L20) | Average of the last 6 major matches (at least 3) − the L20 average above |
| `major_elo` – Big-Stage Elo | Elo from matches on majors only |
| `major_experience` – Big-Stage Experience | log(1 + major matches played) |
| `oom_rank` – PDC Order of Merit | −ln(rank) before the match; the ranking reflects every event through prize money and stays current |
| `major_qf_12m` – Major Quarter-finals (12 months) | Majors in the last 12 months where the player reached at least the quarter-finals. The Premier League is left out (every night has its own quarter-finals and final) |
| `major_points_12m` – Major Results Points (12 months) | The same runs weighted by depth: quarter-final 1, semi-final 2, final 3, title 4 |
| `major_titles_24m` – Major Titles (24 months) | Major titles in the last 24 months (Premier League left out) |
| `top32_share_5y` – Time in the Top 32 | Share of the last 60 months spent in the Order of Merit top 32 (months before the ranking history starts in 2021 don't count) |
| `oom_best_3y` – Best Order of Merit Rank (3 years) | −ln(best rank) in the monthly rankings of the last 36 months |
| `oom_momentum` – Order of Merit Momentum (12 months) | ln(rank a year ago) − ln(rank now): positive for a climbing player, +0.69 = the rank number halved |

The targets are still **all matches** between tracked players since 2021 (Players Championships included): the outcome of any match says something about the two players, only the inputs come from the majors. A player needs 5 major matches with averages to get a PI, so roughly 110 of the 150 tracked players have one.

**Selection** (same rules as below: correlation filter, significance with an out-of-sample check, 80 % of bootstrap samples):

| Candidate | Result |
|---|---|
| **3-Dart Average on Majors (L20)** | **kept**, weight 55 %, significant in 100 % of bootstrap samples |
| **PDC Order of Merit** | **kept**, weight 35 %, 100 % |
| **Order of Merit Momentum** | **kept**, weight 10 %, 94 % |
| Big-Stage Elo | dropped: r = 0.82 with Major Results Points |
| Big-Stage Experience | dropped: r = 0.84 with the Order of Merit |
| Major Results Points | dropped: r = 0.93 with Major Quarter-finals |
| Best Order of Merit Rank | dropped: r = 0.91 with the Order of Merit |
| Form on Majors | dropped: p = 0.26 |
| Major Quarter-finals | dropped: p = 0.15 |
| Major Titles, Time in the Top 32 | dropped: negative weight next to the others |

**Key test against the PDC Order of Merit** (walk-forward: quarterly refits since July 2023, every major match predicted out of sample):

| Model | Major matches | Log loss | Gain vs Order of Merit [95 % CI] | p |
|---|---|---|---|---|
| **PI model** (avg on majors, Order of Merit, momentum) | 1,653 | **0.638** | **+0.013** [+0.007, +0.019] | < 0.001 |
| PDC Order of Merit | 1,653 | 0.651 | – | – |
| *Previous model, inputs from every event (31 Oct 2026)* | *1,825* | *0.628* | *+0.024* | *< 0.001* |

Over all matches (12,785) the gain is +0.009 (p < 0.001); on the 2026 test period's 399 major matches alone it is +0.005 (p = 0.19, too few matches for significance). Model version `v2026-11-14`, data until 5 Nov 2026.

**What the selection says.** Results on majors (quarter-finals, points, titles) predict wins on their own, but add nothing once the 3-dart average and the ranking are known. *Time in the top 32* and *titles* even get a **negative** weight next to the current rank: at the same rank and average, a long-established player is weaker than a newcomer. The ranking is a two-year rolling total, so it lags: it overrates players on the way down and underrates players on the way up. *Order of Merit Momentum* captures exactly that and is kept.

The edge over the official ranking is smaller than the previous model's with inputs from every event (gain +0.024). That is the price of using only data that keeps coming; the model is still significantly better than the ranking on majors.

---

### How to read the PI

**1. The PI is measured against one benchmark: the average top-32 player.** The benchmark is the average profile of the 32 strongest players, roughly the level of the 14th-best player. Its Order of Merit rank is about **#13, not #16**: the model reads the rank on a log scale (a step from #1 to #2 counts as much as one from #10 to #20), and on that scale ranks 1 to 32 average to their geometric mean, #12.8. Luke Littler's PI of 7.35 means he beats *that* player in 73.5 % of typical matches. It does **not** mean he beats every top-32 player 73.5 % of the time.

**2. Any specific match-up comes from the two PIs.** Each PI encodes a strength. The chance of A beating B depends on the difference between the two strengths:

```
strength from PI:   s = ln( PI / (10 − PI) )            (the log-odds of beating the benchmark)
P(A beats B)      = 1 / (1 + e^−(s_A − s_B))
```

Example, Littler (PI 7.35) vs Beau Greaves (PI 4.10): s = ln(7.35 / 2.65) = 1.02 and ln(4.10 / 5.90) = −0.36, so P = 1 / (1 + e^−1.39) = **80 %**. The PIs are not subtracted directly: 7.35 − 4.10 = 3.25 has no meaning as a probability.

Littler against different opponents:

| Opponent (PI rank) | Opponent's PI | Littler wins |
|---|---|---|
| #2 Luke Humphries | 6.62 | 59 % |
| #3 Gerwyn Price | 6.02 | 65 % |
| #10 Rob Cross | 5.24 | 72 % |
| *average top-32 player* | *5.00* | *73.5 %* |
| #16 Chris Dobey | 4.86 | 75 % |
| #32 Beau Greaves | 4.10 | 80 % |
| #64 Michael Smith | 3.00 | 87 % |
| #100 Adam Lipscombe | 2.01 | 92 % |

Two players with the same PI have a 50 % chance against each other, whatever their PI is.

**3. "Typical match" means first to 6 legs (best of 11 legs).** This is the standard format of the Players Championship and European Tour, and the format of 76 % of the matches the model learned from:

| Format | Share of matches |
|---|---|
| **First to 6 legs (best of 11)** | **76 %** |
| First to 4–5 legs (best of 7–9) | 14 % |
| First to 7–11 legs (best of 13–21), e.g. Grand Slam, Masters, European Championship knockouts | 7 % |
| Sets (World Championship, World Grand Prix) | 2 % |
| Other short formats (first to 2–3 legs) | 1 % |

In longer formats luck evens out more and the favourite's chance rises; in shorter ones it falls. The tournament simulations convert every probability to the format of the round ([Part 2](#part-2-tournament-predictions)).

**4. The probabilities are calibrated.** Each match gets its own probability, from about 50 % for close match-ups to about 90 % for heavy favourites. On the 2026 test data (never used for fitting), matches sorted into 10 groups by predicted probability are won about as often as predicted. For example, in the group where the model predicted 77.4 %, the favourites won 77.6 %. So a probability of X % can be read literally.

---

### The three steps

1. **Select predictors**: keep only the statistics that predict match results, tested on data the model has not seen.
2. **Weight them**: the weights are the coefficients of a logistic regression, not hand-picked numbers.
3. **Convert to the 0–10 scale**: compare each player with the average top-32 player.

---

### What the model learned from

**Sources.**
- **Until 28 Oct 2026: Darts Orakel** (exact points and darts, plus first-9, checkout and 180s). Orakel blocked our client on 30 Oct 2026.
- **From then on: Mastercaller** (3-dart averages, stats by iDarts). Mastercaller has no dart counts, so darts are estimated as `legs × 1503 / average` (sets × 4 legs). Checked on Orakel data, where the exact numbers are known: the 3-Dart Average (L30) moves by −0.06 points on average, 95 % within ±0.24, which is negligible next to a spread of ~4.5 points between players. Matches present in both sources come from Orakel.
- **The official PDC Order of Merit** (tracked players, the Order of Merit predictor and the key test) comes from the Wikipedia data module `Module:DartsRankings/data/PDC Rankings`, current and as of any past date.
- **Since 10 Nov 2026: the majors from Wikipedia.** Every knockout match in a major's draw (score and both 3-dart averages, as shown in the bracket), dated by its round; darts estimated from legs like Mastercaller. Group stages, Players Championships and the European Tour are no longer added.

The selected predictors need only results, averages and the ranking, so the model keeps learning from new matches. First-9, checkout and 180s can only be tested as candidates on data until 28 Oct 2026.

**Coverage.** Every match since **1 January 2021** of the tracked players (the 150 best in the ranking). Besides the PDC Pro Tour and the majors this includes qualifiers, Q-School, the Challenge and Development Tours, the Women's Series and other tours.

**Which matches become observations.** A match is used only if **both** players are tracked and both have enough history: at least 10 earlier matches with stats (for the 3-dart average) and 30 earlier matches (for the Elo). Matches from early 2021 serve only as history, so the first usable match is from 27 February 2021.

**Majors** are the 10 televised PDC events in [config/majors.yml](../config/majors.yml): World Championship, Masters, UK Open, Premier League, World Matchplay, World Series Finals, World Grand Prix, European Championship, Grand Slam and Players Championship Finals.

**The data, split by time** (`darts_gold.pi_training_data`):

| | Training | Validation | Test |
|---|---|---|---|
| Period | 27 Feb 2021 – 31 Mar 2025 | 1 Apr 2025 – 30 Dec 2025 | 1 Jan 2026 – 28 Oct 2026 |
| Used for | Elo tuning, fitting, significance tests, bootstrap | out-of-sample check during selection | final evaluation only |
| Matches | 13,473 | 4,172 | 4,987 |
| of which majors | 1,853 (14 %) | 405 (10 %) | 431 (9 %) |
| Players | 141 | 143 | 144 |

By event type (approximate shares): Players Championship ~50 %, qualifiers and Q-School ~13 %, European Tour ~11 %, majors ~12 %, Challenge/Development Tour and Women's Series ~6 %, other tours ~6 %, other PDC TV events ~2 %. In total **22,632 matches**. The final weights are refitted on all three parts together, after the evaluation.

#### No look-ahead

Every predictor describes a player **before** the match, computed only from earlier matches. Within a day, matches are ordered **by round** (Last 128 before Last 64 … before the final), not by match id. Time-window predictors ignore the whole match day. So the model never sees the result it is trying to predict, and a test (`tests/test_analytics.py`) guards the ordering.

> **Correction, 31 Oct 2026.** Earlier versions ordered same-day matches by Darts Orakel's match id. Orakel numbers single-day Players Championship events *backwards* (the final has the lowest id), so a first-round match could "see" the same player's later rounds that day, which only exist if he won. This mainly inflated *Experience*, which no longer passes selection, and slightly affected Elo and the L30 averages. All numbers in this document were recomputed after the fix.

---

### Candidate predictors

"L30" means the player's last 30 matches before the one being predicted. Averages are pooled, as **total points ÷ total darts × 3**, so a long match counts more than a short one. Every candidate is defined so that **higher is better**. Ten were added on 31 Oct 2026, aimed at majors, and fixed before testing.

| Predictor | Name in the app | Definition |
|---|---|---|
| `avg_l30` | **3-Dart Average (L30)** | Points ÷ darts × 3 over the last 30 matches (at least 10 needed) |
| `first9_l30` | First-9 Average (L30) | Same, using only the first 9 darts of each leg |
| `form` | **Form (L10 vs L30)** | 3-dart average of the last 10 matches − 3-dart average of the last 30 |
| `elo` | **Opponent-Weighted Elo** | Rating from results only: beating a strong player earns many points, beating a weak one few (below) |
| `oom_rank` | **PDC Order of Merit (log rank)** | −ln(rank) in the official Order of Merit before the match (2-year prize money); unranked = rank 500 |
| `big_stage_delta` | Big-Stage Delta (majors only) | 3-dart average on majors − overall 3-dart average, last 24 months, shrunk for small samples (below) |
| `checkout_l30` | Checkout % (L30) | Checkouts hit ÷ checkout attempts, last 30 matches |
| `t180_per100` | 180s per 100 Darts (L30) | Number of 180s per 100 darts thrown, last 30 matches |
| `winrate_l30` | Win Rate (L30) | Share of the last 30 matches won |
| `experience` | Experience (log matches) | log(1 + matches played so far) |
| `major_elo` | Big-Stage Elo | The same Elo, computed from matches on majors only |
| `major_experience` | Big-Stage Experience | log(1 + major matches played so far) |
| `h2h` | Head-to-Head | Share of earlier meetings between the two players won, shrunk toward 50 %: (wins + 2) ÷ (meetings + 4) − 0.5. Describes the match-up, so it would never enter a player's PI |
| `consistency` | Consistency (L30) | − standard deviation of the match averages over the last 30 matches |
| `activity` | Activity | log(1 + matches in the 30 days before the match day) |
| `sharpness` | Match Sharpness | − log(1 + days since the previous match) |
| `stage_delta` | **Stage Delta (majors only)** | 3-dart average on **stage** events (majors, European Tour, World Series, Premier League) − average on **floor** events (Players Championship, qualifiers, other tours), last 24 months, shrunk like Big-Stage Delta |
| `long_format_delta` | Long-Format Delta (majors only) | 3-dart average in long matches (15+ legs, sets count as 4 legs) − overall average, last 24 months, shrunk |
| `major_results_oe` | Big-Stage Results over Expectation (majors only) | On majors in the last 24 months: (wins − Elo-expected wins) ÷ (major matches + 10) |

#### Opponent-Weighted Elo in detail

A classic Elo rating, replayed over every match since 2021 in chronological order. Everyone starts at 1500.

```
expected win chance of A = 1 / (1 + 10^((Elo_B − Elo_A) / 400))
new Elo_A = Elo_A + K × m × (result − expected)        result = 1 for a win, 0 for a loss
```

- A win over a much stronger player (expected ≈ 0.2) earns 0.8 × K points; a win over a much weaker one (expected ≈ 0.9) only 0.1 × K. That is why it is called *opponent-weighted*.
- **K and m are tuned** on the training period (K ∈ {16, 24, 32, 40, 48}, m = 1 or 1.5 on majors, lowest log loss wins). Current model: **K = 16, m = 1.5**.
- **Burn-in:** a player's Elo is only used after 30 matches.
- Limitation: opponents outside the tracked players are rated only from their matches against tracked players.

#### Big-Stage Delta in detail

Does a player raise (or lose) their level on the big stage? The raw delta is the player's 3-dart average **on majors** minus their 3-dart average **in all matches**, both over the last 24 months, shrunk toward 0 for small samples: `raw delta × n / (n + 10)`, n = major matches in the last 24 months. It is a **majors-only** predictor: it enters the model only for matches on a major.

---

### The model behind every step

Each match becomes one row: **y = 1 if player A won**, and each predictor is the **difference A − B**. Players are assigned to A and B at random. A **logistic regression without an intercept** is fitted:

```
P(A beats B) = 1 / (1 + e^−(S_A − S_B))        S = β₁·x₁/sd₁ + β₂·x₂/sd₂ + …
```

`S` is the player's **strength**. Swapping A and B flips the prediction exactly, which is why there is no intercept. Predictors are divided by their standard deviation (`sd`, from the training data), so each β answers *"how much does a one-standard-deviation advantage change the log-odds of winning?"* and the βs are comparable.

---

### Step 1: Selecting predictors

A candidate must pass **all three** filters.

**1a. Correlation filter.** Two predictors that measure almost the same thing (|r| > 0.8) make the weights unstable. From each such pair we keep the one that predicts better **on its own** (log loss of a one-predictor model over 5 consecutive time blocks of the training data).

**1b. Significance and out-of-sample check.** Backward elimination on training data: remove a predictor with a negative coefficient (a better value must never lower the win chance) or with p ≥ 0.05, one at a time. Then each remaining predictor must improve log loss on the **validation** period; if the model is just as good without it, it goes.

**1c. Bootstrap stability.** Refit on 500 bootstrap samples of the training data. A predictor stays only if it is significant (p < 0.05) and positive in **at least 80 %** of them.

Every decision and its reason is stored in `darts_gold.pi_selection_log`.

#### Result: all 19 tested predictors

**In the index (4):**

| Predictor | Why it is in |
|---|---|
| **3-Dart Average (L30)** | The strongest single predictor of who wins. Significant in 100 % of bootstrap samples. |
| **Opponent-Weighted Elo** | Adds what the average doesn't know: how strong the beaten opponents were. 100 % of samples. |
| **Form (L10 vs L30)** | A player on an upswing wins more than their L30 average suggests. 100 % of samples. |
| **PDC Order of Merit (log rank)** | Adds the long-term record on the stages with the most prize money (majors), which recent averages and Elo don't fully capture. 100 % of samples. |

**Tested and left out (15):**

| Predictor | Out at | Why it is not in |
|---|---|---|
| First-9 Average (L30) | 1a | Measures almost the same as the 3-dart average (r = 0.94); the 3-dart average predicts slightly better alone. |
| Big-Stage Experience | 1a | Nearly the same as the Order of Merit rank (r = 0.83), which predicts better alone. |
| Win Rate (L30) | 1b | Negative coefficient once average and Elo are in: Elo already captures results, and better. |
| Checkout % (L30) | 1b | Not significant (p = 0.92): finishing is part of the 3-dart average already. |
| 180s per 100 Darts (L30) | 1b | Negative coefficient: heavy scoring is part of the 3-dart average already. |
| Experience | 1b | Not significant (p = 0.31). |
| Big-Stage Elo | 1b | Not significant (p = 0.80): adds nothing beyond the overall Elo and the Order of Merit. |
| Head-to-Head | 1b | Not significant (p = 0.11): previous meetings add little beyond the players' current strength. |
| Consistency (L30) | 1b | Negative coefficient: steadier averages don't mean more wins once the level is known. |
| Activity | 1b | Not significant (p = 0.66). |
| Match Sharpness | 1b | Negative coefficient (and no effect without the look-ahead bug, see the correction above). |
| Big-Stage Delta (majors only) | 1a | Nearly the same as Stage Delta (r = 0.92), which predicts better. Alone it was significant in single fits but never stable (61–75 % of bootstrap samples). |
| Long-Format Delta (majors only) | 1a | Nearly the same as Stage Delta (r = 0.81), which predicts better. |
| Big-Stage Results over Expectation (majors only) | 1b | Not significant (p = 0.34): winning more on majors than the Elo expects does not repeat. |
| **Stage Delta (majors only)** | 1c | **Closest miss:** significant and improves validation (1b), but significant in 79 % of bootstrap samples, just under the 80 % threshold. See below. |

**Big-stage ability**, the hypothesis that some players raise their level on the big stage, was tested with four predictors, all entering only matches on majors (31 Oct 2026):

| Test | Stage Delta | Big-Stage Delta | Long-Format Delta | Results over Expectation |
|---|---|---|---|---|
| Selection rule | out at 1c (79 % < 80 %) | out at 1a | out at 1a | out at 1b |
| Majors-only regression on 2,689 major matches: p, share of significant bootstrap samples | **p = 0.001, 91 %** | p = 0.010, 75 % | p = 0.12, 32 % | p = 0.28, 17 % |
| Walk-forward on majors (1,825): log-loss gain when added to the model | **+0.0026 [−0.0004, +0.0058], p = 0.055** | +0.0014, p = 0.16 | +0.0005, p = 0.25 | +0.0006, p = 0.24 |

**Stage Delta** (average on stage events minus average on floor events) is the strongest and most stable big-stage measure, because it uses far more matches than majors alone. The effect is real but small: +2 points of stage delta ≈ +1.5 percentage points of win chance on a major. It misses the selection rule by one percentage point, and the rule is not bent for it. It is therefore **shown as an information-only indicator** in player profiles and on major match cards ("averages +1.8 more on stage than on the floor"), with no effect on the PI, and re-tested automatically on every refit. With more major matches it may pass.

---

### Step 2: Weights

The final weights are the coefficients of the logistic regression with the selected predictors, refitted on **all** matches:

| Predictor | β (per 1 sd) | Share of the index | In 3-dart-average points |
|---|---|---|---|
| 3-Dart Average (L30) | 0.458 | 53 % | 1 point = 1 point |
| Opponent-Weighted Elo | 0.181 | 21 % | 100 Elo points = 1.5 average points |
| Form (L10 vs L30) | 0.128 | 15 % | 1 point of form = 0.48 average points |
| PDC Order of Merit (log rank) | 0.100 | 12 % | halving your rank number (e.g. #20 → #10) = 0.47 average points |

All four have p < 0.001. **Share of the index** = |β| ÷ sum of all |β|. **In 3-dart-average points** converts each predictor into the unit everyone in darts understands. Weights, standard errors, 95 % confidence intervals and bootstrap shares are in `darts_gold.pi_coefficients`.

---

### Step 3: The 0–10 scale

1. Compute every player's strength `S` with the current weights.
2. The **reference player** is the *average profile* of the 32 strongest players at that date (mean of each predictor). Because the model is linear, the reference strength is the mean strength of those 32 players.
3. Convert: `PI = 10 × 1 / (1 + e^−(S − S_ref))`.

`S − S_ref` splits exactly into one **contribution** per predictor, `β × (x − x_ref) / sd`. So every PI can be explained. For example, Littler's PI 7.35 = Elo +0.39, 3-dart average +0.35, Order of Merit +0.19, form +0.09 (log-odds).

**Effective Average** expresses the whole strength in 3-dart-average points: the player's own 3-dart average (L30) plus Elo, form and Order of Merit converted into average points. Example: Littler, 3-Dart Average (L30) 98.2, **Effective Average 104.7**. His Elo, ranking and form are worth about 6.5 extra average points against a typical top-32 field.

**PI Major.** If a majors-only predictor is selected (today none), each player also gets a *PI Major* including it, used for matches on majors. While none is selected, PI Major equals PI.

**Pair-specific predictors** (Head-to-Head) never enter a player's PI. If one is ever selected, it adjusts the probability of the specific match only.

---

### Validation (test period 2026, never used for fitting or selection)

| Model | Matches | AUC | Log loss | Brier |
|---|---|---|---|---|
| **PI model** (average, form, Elo, Order of Merit) | 4,987 | **0.681** | **0.639** | **0.225** |
| 3-dart average only | 4,987 | 0.677 | 0.642 | 0.226 |
| Elo only | 4,987 | 0.661 | 0.652 | 0.230 |
| PI model, majors only | 431 | 0.708 | 0.622 | 0.217 |

- **AUC** (0.5 = coin flip, 1 = perfect): darts has a lot of randomness, so ~0.68 is a strong result for pre-match information alone.
- **Calibration:** in every decile the favourites win about as often as predicted (`darts_gold.pi_calibration`).

---

### Key test: does the PI beat the official PDC ranking?

If the model didn't predict winners better than the PDC Order of Merit, it would add nothing. So it is tested against it on every refit.

- **Baseline:** `P(A beats B) = 1 / (1 + e^−(b · (ln rank_B − ln rank_A)))` with each player's Order of Merit rank **as of the match date**, `b` fitted on the same training matches as the PI model. Unranked players count as rank 500.
- **Walk-forward test:** for every quarter from July 2023, both the PI model and the ranking baseline are refitted on all matches *before* that quarter and predict the quarter's matches. Every prediction is out of sample, and majors get a large enough sample (1,825 matches) for a real test.
- **Significance:** a **paired bootstrap** (1,000 resamples of the same matches for both models) gives a 95 % interval for the log-loss gain. The PI counts as better only if the whole interval is above zero.

**Result** (`darts_gold.pi_benchmark`):

| Test | Matches | PI: log loss / favourite won | Order of Merit: log loss / favourite won | Gain [95 % CI] | p |
|---|---|---|---|---|---|
| **Walk-forward, majors 07/2023 – 10/2026** | **1,825** | **0.628 / 63.9 %** | 0.652 / 62.4 % | **+0.024 [+0.014, +0.034]** | **< 0.001** |
| Walk-forward, all matches | 16,805 | 0.643 / 62.6 % | 0.669 / 58.7 % | +0.027 [+0.023, +0.030] | < 0.001 |
| 2026 test period, all matches | 4,987 | 0.639 / 62.9 % | 0.670 / 57.9 % | +0.031 [+0.025, +0.037] | < 0.001 |
| 2026 test period, majors only | 431 | 0.622 / 64.5 % | 0.636 / 66.4 % | +0.014 [−0.006, +0.034] | 0.08 |

**The PI predicts winners significantly better than the official ranking, on majors and overall.** The strictly untouched 2026 majors alone (431 matches) point the same way but are too few for significance. One caveat: in the walk-forward test the *weights* are always fitted on the past only, but the *choice* of predictors was made on data until December 2025. Only the 2026 test period is clean of that, and it agrees.

---

### Model versions (promotion policy)

Every refresh refits the model, but a new fit is only a **candidate**. It replaces the active model only if ([src/analytics/registry.py](../src/analytics/registry.py)):

1. the selected predictors are the same (a change in what the index is made of needs a human decision),
2. its test log loss is not worse than the active model's by more than 0.005,
3. no predictor's share of the index moved by more than 15 percentage points.

Otherwise the active model stays and the health report shows why, so the PI does not jump because of noise. Decisions are stored in `darts_gold.pi_model_registry`; the PI, the tournament predictions and the app always use the **active** version.

---

### Limitations

- **Coverage:** only the 150 best players in the Order of Merit are tracked. Everyone else appears only as an opponent of a tracked player: their Elo comes from those matches alone, and matches between two untracked players are not in the data.
- **All events count** in the averages, including lower-level events some players play. The Elo and the Order of Merit partly correct for the level of opposition.
- **Mastercaller data** (from 30 Oct 2026) has estimated dart counts (see above) and no first-9, checkout or 180s.
- **Linear model:** effects add up; interactions are not modelled.

---

### Reproducibility

| What | Where |
|---|---|
| Predictor definitions | [src/analytics/features.py](../src/analytics/features.py), round ordering [src/analytics/rounds.py](../src/analytics/rounds.py) |
| Opponent-Weighted Elo | [src/analytics/elo.py](../src/analytics/elo.py) |
| Selection, weights, scale | [src/analytics/model.py](../src/analytics/model.py), [src/analytics/pipeline.py](../src/analytics/pipeline.py) |
| Key test vs Order of Merit | [src/analytics/benchmark.py](../src/analytics/benchmark.py) |
| Promotion policy | [src/analytics/registry.py](../src/analytics/registry.py) |
| Databricks notebooks | [04_pi_model.py](../src/notebooks/04_pi_model.py), [05_performance_index.py](../src/notebooks/05_performance_index.py) |
| Majors list | [config/majors.yml](../config/majors.yml) |

| Gold table | Contents |
|---|---|
| `darts_gold.pi_coefficients` | weights, standard errors, p-values, CIs, bootstrap shares, conversion to average points (per version) |
| `darts_gold.pi_selection_log` | every keep/drop decision with its reason |
| `darts_gold.pi_metrics` | AUC, log loss, Brier on the test period, PI model vs. single-predictor baselines |
| `darts_gold.pi_benchmark` | key test vs the PDC Order of Merit (2026 test period, walk-forward on majors and on all matches) |
| `darts_gold.pi_calibration` | predicted vs. observed win rate by decile |
| `darts_gold.pi_training_data` | matches, players and event mix per part of the split |
| `darts_gold.pi_elo_tuning`, `darts_gold.pi_correlations` | Elo parameter search, correlation matrix of the candidates |
| `darts_gold.pi_model_registry` | candidate / active / rejected versions with the reason |
| `darts_gold.elo_history` | every player's Elo before and after each match (active and latest candidate version) |
| `darts_gold.performance_index` | PI, PI Major, Effective Average, contributions, monthly history |

---

## Part 2: Tournament predictions

For every PDC major the app shows:

- **Season calendar**: all majors with dates, status (completed / in progress / upcoming) and winners.
- **Pre-tournament predictions**: each player's probability of reaching every round and of winning the title, once the draw is published.
- **Live bracket**: after each refresh, matches already played are fixed and the rest of the draw is simulated again.
- **Upcoming matches**: every scheduled match in the Mastercaller match center, with both players' PI, the win probability and their head-to-head record.
- **Backtests**: for finished majors, what the model would have predicted before the event, compared with what happened.

Everything is built on the [Performance Index](#part-1-performance-index-pi): the same strengths and the same head-to-head formula.

---

### 1. From two PIs to one match in a specific format

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

### 2. Strength of every player in the draw

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

### 3. Simulating the draw

The draw comes from the event's Wikipedia page (parsed from the bracket templates, including each round's format). The simulation plays the whole draw **10,000 times**:

1. In each round, every match is decided at random with the probability from step 1 in that round's format.
2. Winners move on to their slot in the next round.
3. **Live mode:** a match that already has a result is not simulated; the real winner moves on.

Counting how often each player reaches each round gives **P(reach round)** and **P(title)**. A walkover counts as a win in the draw but is left out of backtests, because no match was played.

**Supported draws:** knockout draws of 2^n players without byes. That covers the World Championship from 2026 (128 players), the World Matchplay, the World Grand Prix, the European Championship, the World Series Finals and the Grand Slam knockout stage. A draw needs at least 16 players. Byes (empty first-round slots) are supported. Not supported yet: the 96-player World Championships up to 2025 (seeds start in round 2), the Grand Slam group stage, the Premier League (a league), the UK Open (Wikipedia only has the semi-finals as a bracket) and the Players Championship Finals sections layout (to be verified once the 2026 draw is out).

---

### 4. Upcoming matches

Mastercaller's match center lists scheduled matches once a draw or order of play is out. Each one gets a card:

- both players' **PI**, **PI Major**, **Effective Average**, **3-Dart Average (L30)** and **Form**
- **P(A wins)** in a typical match (and in the event's format inside a simulated draw)
- **head-to-head**: wins against each other in all matches since 2021

During majors the data is refreshed daily ("tournament mode"); otherwise on demand from the app.

---

### 5. Backtests

Every finished major with a supported draw is backtested automatically: strengths as of the event's first day, weights refitted on earlier matches only, and the full draw simulated *before* any match was played. Results are stored in `darts_gold.tournament_backtest_summary` and `darts_gold.tournament_backtest_matches`. Numbers below: model `v2026-11-14` (inputs from the majors only), run 15 Nov 2026.

**Ten majors, 388 matches (2025–2026):**

| Event | Matches | Favourite won | Log loss | Champion | Champion's pre-event title chance (rank) | Model's favourite |
|---|---|---|---|---|---|---|
| World Championship 2026 | 126 | 74 % | 0.538 | Luke Littler | 43.3 % (1) | Littler 43.3 % |
| European Championship 2026 | 31 | 58 % | 0.660 | Ross Smith | 3.6 % (8) | Littler 34.8 % |
| World Grand Prix 2026 | 31 | 74 % | 0.594 | Luke Humphries | 16.2 % (2) | Littler 35.1 % |
| World Series Finals 2026 | 31 | 74 % | 0.588 | Ross Smith | 2.0 % (12) | Littler 31.7 % |
| World Matchplay 2026 | 30 | 77 % | 0.574 | Luke Littler | 23.3 % (1) | Littler 23.3 % |
| Grand Slam 2025 (knockout stage) | 15 | 73 % | 0.533 | Luke Littler | 38.9 % (1) | Littler 38.9 % |
| European Championship 2025 | 31 | 58 % | 0.667 | Gian van Veen | 3.8 % (7) | Littler 27.0 % |
| World Series Finals 2025 | 31 | 68 % | 0.572 | Michael van Gerwen | 3.0 % (10) | Littler 32.5 % |
| World Grand Prix 2025 | 31 | 68 % | 0.595 | Luke Littler | 30.6 % (1) | Littler 30.6 % |
| World Matchplay 2025 | 31 | 74 % | 0.594 | Luke Littler | 30.1 % (1) | Littler 30.1 % |

**All 388 matches together:**

| | Round format | As typical matches |
|---|---|---|
| Pre-match favourite won | 70.6 % | 70.6 % |
| Log loss | **0.581** | 0.593 |
| Brier score | **0.199** | 0.203 |

Converting each match to its round's format improves both scores. (The previous model, with inputs from every event: favourite won 68.8 %, log loss 0.579.)

**Calibration (388 matches, 5 groups by the favourite's predicted chance):**

| Predicted | 53 % | 59 % | 65 % | 72 % | 83 % |
|---|---|---|---|---|---|
| Favourite actually won | 60 % | 58 % | 72 % | 74 % | 89 % |

Each group has about 78 matches, so ±5 points are within chance. If anything, the favourites won slightly more often than predicted.

**Titles:** the model's favourite won 5 of the 10 events, against 3.27 expected wins from its title probabilities. Ten events are too few to judge title probabilities; every finished major adds one.

---

### Limitations

- **Strong favourites may be rated slightly too high in long formats.** Treating legs as independent assumes a player's level is the same in every leg. In reality players have good and bad days, so legs within a match are correlated and long matches favour the stronger player less than the formula says. For one match the effect is small (the backtest confirms the format conversion helps), but over 7 rounds it compounds. Planned fix: estimate a "day form" spread from the data and add it to the simulation. Bookmaker odds are not available as a benchmark (no free, legal source reachable from the Czech Republic), so validation uses baselines such as seeding.
- **Ten backtested events** are not enough to judge title probabilities. Each finished major with a supported draw adds a backtest automatically.
- **Throw advantage and "two clear legs"** are ignored.
- **Unsupported formats** (see section 3) have no simulation yet; their matches still get head-to-head cards.

---

### Data and code

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
