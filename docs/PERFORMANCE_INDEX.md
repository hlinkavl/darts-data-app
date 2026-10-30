# Performance Index (PI): Methodology

The Performance Index rates every tracked PDC player on a **0–10 scale**:

> **PI = 10 × the probability that the player beats an average top-32 player in a typical match.**

A PI of 7.0 means a 70 % chance against a typical top-32 opponent. A PI of 5.0 means the player *is* a typical top-32 player. A PI of 2.0 means a 20 % chance. Because the scale is a probability, any two PIs can be turned into a head-to-head prediction (see [Step 3](#step-3-the-0-10-scale)).

## How to read the PI

**1. The PI is measured against one benchmark: the average top-32 player.** The benchmark is the average profile of the 32 strongest players, roughly the level of the 14th-best player. Luke Littler's PI of 7.15 means he beats *that* player in 71.5 % of typical matches. It does **not** mean he beats every top-32 player 71.5 % of the time.

**2. Any specific match-up comes from the two PIs.** Each PI encodes a strength. The chance of A beating B depends on the difference between the two strengths:

```
strength from PI:   s = ln( PI / (10 − PI) )            (the log-odds of beating the benchmark)
P(A beats B)      = 1 / (1 + e^−(s_A − s_B))
```

Example, Littler (PI 7.15) vs Cameron Menzies (PI 4.25): s = ln(7.15 / 2.85) = 0.92 and ln(4.25 / 5.75) = −0.30, so P = 1 / (1 + e^−1.22) = **77 %**. The PIs are not subtracted directly: 7.15 − 4.25 = 2.90 has no meaning as a probability.

Littler against different opponents (model v2026-10-28):

| Opponent (PI rank) | Opponent's PI | Littler wins |
|---|---|---|
| #2 Luke Humphries | 6.36 | 59 % |
| #3 Gerwyn Price | 5.88 | 64 % |
| #10 Nathan Aspinall | 5.23 | 70 % |
| *average top-32 player* | *5.00* | *71.5 %* |
| #16 Chris Dobey | 4.78 | 73 % |
| #32 Cameron Menzies | 4.25 | 77 % |
| #64 Ritchie Edhouse | 3.23 | 84 % |
| #100 Adam Sevada | 2.49 | 88 % |

Two players with the same PI have a 50 % chance against each other, whatever their PI is.

**3. "Typical match" means first to 6 legs (best of 11 legs).** This is the standard format of the Players Championship and European Tour, and the format of 76 % of the matches between tracked players since 2021, which is the data the model learned from (see [What the model learned from](#what-the-model-learned-from)):

| Format | Share of matches |
|---|---|
| **First to 6 legs (best of 11)** | **76 %** |
| First to 4–5 legs (best of 7–9) | 14 % |
| First to 7–11 legs (best of 13–21), e.g. Grand Slam, Masters, European Championship knockouts | 7 % |
| Sets (World Championship, World Grand Prix) | 2 % |
| Other short formats (first to 2–3 legs) | 1 % |

So PI 7.15 means: Littler wins 71.5 % of best-of-11-legs matches against the average top-32 player. In longer formats luck evens out more and the favourite's chance rises. Littler vs Menzies at the World Championship (first to 3 sets in round 1, up to first to 7 sets in the final, each set first to 3 legs) would be above 77 %. Shorter formats work the other way. The tournament simulations convert every probability to the format of the round (see [DESIGN.md](DESIGN.md#tournament-overview)).

**4. The probabilities are calibrated.** Each match gets its own probability, from about 50 % for close match-ups to about 90 % for heavy favourites. On the 2026 test data (never used for fitting), matches were sorted by predicted probability into 10 groups. In each group the favourites won about as often as predicted. For example, in the group where the model predicted 77.9 % on average, the favourites won 79.2 %. So a probability of X % can be read literally. See [Validation](#validation-test-period-2026-never-used-for-fitting-or-selection).

---

The index is built in three transparent steps:

1. **Select predictors**: keep only the statistics that predict match results, tested on data the model has not seen.
2. **Weight them**: the weights are the coefficients of a logistic regression, not hand-picked numbers.
3. **Convert to the 0–10 scale**: compare each player with the average top-32 player.

Every number in this document is recomputed on each refresh and stored in Databricks (tables listed at the end). The app's *Methodology* page reads those tables, so it always shows the current model.

---

## What the model learned from

**Sources.** Until 28 Oct 2026: Darts Orakel's free match data (exact points and darts, plus first-9, checkout and 180s). Orakel blocked our client on 30 Oct 2026, so new results come from **Mastercaller** (3-dart averages, stats by iDarts). Mastercaller has no dart counts, so darts are estimated as `legs × 1503 / average` (sets × 4 legs). Checked on Orakel data, where the exact numbers are known: the 3-Dart Average (L30) moves by −0.06 points on average, 95 % within ±0.24, which is negligible next to a spread of ~4.5 points between players. Matches present in both sources come from Orakel. The selected predictors need only results and averages, so the model keeps learning from new matches. First-9, checkout and 180s can only be tested as candidates on data until 28 Oct 2026. The Order of Merit (tracked players, key test) comes from the official PDC ranking on Wikipedia.

**Orakel data, the basis of the current model.** Darts Orakel's free match data: every match since **1 January 2021** of the **150 players** in the current 2-year prize-money ranking (the PDC Order of Merit equivalent). Each player's match row has points and darts thrown, first-9 points and darts, checkouts hit and attempted, and 180s. Orakel covers every event these players play, so besides the PDC Pro Tour and the majors the data also has qualifiers, Q-School, the Challenge and Development Tours, the Women's Series and other tours (Asian Tour, MODUS, Nordic & Baltic, …).

**Which matches become observations.** A match is used only if:
- **both** players are among the 150 tracked players (both need predictors), and
- both have enough history: at least 10 earlier matches with stats (for the 3-dart average) and 30 earlier matches (for the Elo, see below).

Matches from early 2021 serve only as history, so the first usable match is from 27 February 2021.

**Majors** are the 10 televised PDC events in [config/majors.yml](../config/majors.yml): World Championship, Masters, UK Open, Premier League, World Matchplay, World Series Finals, World Grand Prix, European Championship, Grand Slam and Players Championship Finals.

**The data, split by time** (model v2026-10-28, `darts_gold.pi_training_data`):

| | Training | Validation | Test |
|---|---|---|---|
| Period | 27 Feb 2021 – 31 Mar 2025 | 1 Apr 2025 – 30 Dec 2025 | 1 Jan 2026 – 24 Oct 2026 |
| Used for | Elo tuning, fitting, significance tests, bootstrap | out-of-sample check during selection | final evaluation only |
| Matches | 13,330 | 4,171 | 4,955 |
| Players | 141 | 143 | 144 |
| Players Championship | 49 % | 53 % | 54 % |
| Majors | 14 % | 10 % | 9 % |
| Qualifiers & Q-School | 12 % | 13 % | 16 % |
| European Tour | 10 % | 12 % | 12 % |
| Challenge / Development Tour, Women's Series | 8 % | 5 % | 4 % |
| Other tours (Asian Tour, MODUS, Nordic & Baltic, …) | 6 % | 7 % | 3 % |
| Other PDC TV events (World Series, World Cup, …) | 2 % | 1 % | 2 % |

In total **22,456 matches**. The final weights are refitted on all three parts together, after the evaluation.

### No look-ahead

Every predictor describes a player **before** the match, computed only from earlier matches. Same-day matches count only if they come earlier in Orakel's match order. The time-window predictor (Big-Stage Delta) ignores the whole match day. So the model never sees the result it is trying to predict.

---

## Candidate predictors

"L30" means the player's last 30 matches before the one being predicted. Averages are pooled, as **total points ÷ total darts × 3**, rather than averaged match by match, so a long match counts more than a short one.

| Predictor | Name in the app | Definition |
|---|---|---|
| `avg_l30` | **3-Dart Average (L30)** | Points ÷ darts × 3 over the last 30 matches (at least 10 needed) |
| `first9_l30` | First-9 Average (L30) | Same, using only the first 9 darts of each leg |
| `form` | **Form (L10 vs L30)** | 3-dart average of the last 10 matches − 3-dart average of the last 30 |
| `big_stage_delta` | **Big-Stage Delta (majors only)** | 3-dart average on majors − overall 3-dart average, last 24 months, shrunk toward 0 for small samples (below) |
| `elo` | **Opponent-Weighted Elo** | Rating from results only: beating a strong player earns many points, beating a weak one few (below) |
| `checkout_l30` | Checkout % (L30) | Checkouts hit ÷ checkout attempts, last 30 matches |
| `t180_per100` | 180s per 100 Darts (L30) | Number of 180s per 100 darts thrown, last 30 matches |
| `winrate_l30` | Win Rate (L30) | Share of the last 30 matches won |
| `experience` | Experience (log matches) | log(1 + matches played so far) |

### Big-Stage Delta in detail

Does the player raise (or lose) their level on the big stage? The raw delta is the player's 3-dart average **on majors** minus their 3-dart average **in all matches**, both over the last 24 months. A player with only a handful of major matches would get an extreme value by chance, so the delta is shrunk toward 0:

```
Big-Stage Delta = raw delta × n / (n + 10)        n = major matches in the last 24 months
```

With 10 major matches only half of the raw delta counts. With 90 matches, 90 % counts. With no major matches the delta is 0 (no evidence either way).

The delta is a **majors-only** predictor. It enters the model only for matches played on a major, because the hypothesis is "some players perform better on the big stage", not "these players win more everywhere". In a first test it was clearly related to results on majors (p = 0.004) and not at all to results elsewhere (p = 0.95).

### Opponent-Weighted Elo in detail

A classic Elo rating, replayed over every match since 2021 in date order. Everyone starts at 1500.

```
expected win chance of A = 1 / (1 + 10^((Elo_B − Elo_A) / 400))
new Elo_A = Elo_A + K × m × (result − expected)        result = 1 for a win, 0 for a loss
```

- A win over a much stronger player (expected ≈ 0.2) earns 0.8 × K points. A win over a much weaker player (expected ≈ 0.9) earns only 0.1 × K. That is why it is called *opponent-weighted*.
- `m` = 1.5 on majors if that improves predictions, otherwise 1. Current model: **K = 16, m = 1.5**.
- **K and m are tuned**: the pipeline tries K ∈ {16, 24, 32, 40, 48} × m ∈ {1, 1.5} and keeps the pair whose own predictions have the lowest log loss in the training period.
- **Burn-in:** a player's Elo is only used after 30 matches, because early ratings are still mostly the starting value.
- Limitation: opponents outside the tracked 150 are rated only from their matches against tracked players.

---

## The model behind every step

Each match becomes one row: **y = 1 if player A won**, and each predictor is the **difference A − B**. Players are assigned to A and B at random. A **logistic regression without an intercept** is fitted:

```
P(A beats B) = 1 / (1 + e^−(S_A − S_B))        S = β₁·x₁/sd₁ + β₂·x₂/sd₂ + …
```

`S` is the player's **strength**. Swapping A and B flips the prediction exactly, which is why no intercept is used. Predictors are divided by their standard deviation (`sd`, measured on the training data), so each β answers the question *"how much does a one-standard-deviation advantage in this predictor change the log-odds of winning?"* and the βs are comparable.

The data is split by time, never at random:

| Part | Period | Used for |
|---|---|---|
| Training | until 31 Mar 2025 | Elo tuning, fitting, significance tests, bootstrap |
| Validation | Apr – Dec 2025 | Out-of-sample check during selection |
| Test | from 1 Jan 2026 | Final, untouched evaluation only |

---

## Step 1: Selecting predictors

A candidate must pass **all three** filters.

**1a. Correlation filter.** Two predictors that measure almost the same thing (|r| > 0.8 between their differences) make regression weights unstable: the model can't tell which one deserves the credit, and one of them can even get a wrong sign. From each such pair we keep the one that predicts better **on its own**, measured as the log loss of a one-predictor model over 5 consecutive time blocks of the training data.

**1b. Significance and out-of-sample check.**
- *Backward elimination on training data:* fit the model with all remaining predictors, then remove the predictor with a negative coefficient (a better value must never lower the win chance) or with the highest p-value if it is ≥ 0.05. Repeat until every predictor is positive and significant.
- *Out-of-sample check:* for each remaining predictor, refit without it and compare log loss on the **validation** period. If the model is just as good or better without it, it goes.

**1c. Bootstrap stability.** Refit the model on 500 bootstrap samples of the training data (rows drawn with replacement). A predictor stays only if it is significant (p < 0.05) and positive in **at least 80 %** of them. This guards against predictors that look significant by luck of one particular sample.

Every decision and its reason is stored in `darts_gold.pi_selection_log`.

### Result: all tested predictors (model v2026-10-28)

**In the index (4):**

| Predictor | Why it is in |
|---|---|
| **3-Dart Average (L30)** | The strongest single predictor of who wins. Significant in 100 % of bootstrap samples. |
| **Opponent-Weighted Elo** | Adds what the average doesn't know: how strong the beaten opponents were. 100 % of samples. |
| **Form (L10 vs L30)** | A player on an upswing wins more than their L30 average suggests. 100 % of samples. |
| **Experience (log matches)** | Small extra edge for experienced players. Borderline: exactly 80 % of samples, weight only 3 %. |

**Tested and left out (5):**

| Predictor | Out at | Why it is not in |
|---|---|---|
| First-9 Average (L30) | 1a | Measures almost the same as the 3-dart average (r = 0.94), and the 3-dart average predicts slightly better on its own. |
| Win Rate (L30) | 1b | Once average and Elo are in the model it adds nothing and its coefficient turns negative. Elo already captures results, and better. |
| Checkout % (L30) | 1b | Coefficient turns negative once the average is in. Finishing is already part of the 3-dart average (fewer darts per leg). |
| 180s per 100 Darts (L30) | 1b | Not significant (p = 0.69). Heavy scoring is already part of the 3-dart average. |
| Big-Stage Delta (majors only) | 1c | Significant in a single fit, but **not stable**: significant in only 61 % of bootstrap samples (threshold 80 %). See below. |

**Big-Stage Delta, tested on majors only.** The hypothesis is that some players raise their level on the big stage, so the delta only enters matches played on a major. On the 2,680 matches between tracked players on majors (2021–2026):

| Test | Result |
|---|---|
| Single regression (average, form, Elo, delta) on all majors | p = 0.028, significant at 5 % |
| Bootstrap, 500 resamples of the majors | significant in only 62 % |
| Full 3-step selection on majors only | out at step 1b (p = 0.23) |
| With data since 2023 instead of 2021 | 73 % of bootstrap samples, so the longer history made it weaker |

The effect may exist, but it is small, close to the 5 % threshold (with 9 candidates tested, one borderline result can be luck) and it depends on which matches happen to be in the sample. Putting it into the PI would make PI Major move with noise. It is therefore **shown as an information-only indicator** in player profiles and on major match cards ("plays +1.2 above his average on majors"), with no effect on the PI. It is re-tested automatically on every refit and enters PI Major on its own once it passes the stability rule.

---

## Step 2: Weights

The final weights are the coefficients of the logistic regression with the selected predictors, refitted on **all** matches. Current model:

| Predictor | β (per 1 sd) | p-value | Share of the index | In 3-dart-average points |
|---|---|---|---|---|
| 3-Dart Average (L30) | 0.506 | < 0.001 | 58 % | 1 point = 1 point |
| Opponent-Weighted Elo | 0.186 | < 0.001 | 21 % | 100 Elo points = 1.44 average points |
| Form (L10 vs L30) | 0.157 | < 0.001 | 18 % | 1 point of form = 0.53 average points |
| Experience (log matches) | 0.024 | 0.09 | 3 % | doubling the number of matches played = 0.33 average points |

- **Share of the index** = |β| ÷ sum of all |β|.
- **In 3-dart-average points** converts each predictor into the unit everyone in darts understands. Example: a player whose last 10 matches are 2 points above their L30 average gets the same boost as +1.06 points of 3-dart average.
- Experience has a p-value of 0.09 in the final fit on all data. It passed selection on the training data (exactly 80 % of bootstrap samples), so the rule keeps it. Its effect on any PI is small: a few hundredths in log-odds.

Weights, standard errors, 95 % confidence intervals and bootstrap shares are stored in `darts_gold.pi_coefficients`.

---

## Step 3: The 0–10 scale

1. Compute every player's strength `S` with the current weights.
2. The **reference player** is the *average profile* of the 32 strongest players at that date (mean of each predictor). Because the model is linear, the reference strength is simply the mean strength of those 32 players.
3. Convert:

```
PI = 10 × 1 / (1 + e^−(S − S_ref))
```

`S − S_ref` splits exactly into one **contribution** per predictor, `β × (x − x_ref) / sd`. So every PI can be explained, e.g. Littler's "PI 7.15 = 3-dart average +0.35, Elo +0.44, form +0.10, experience +0.02 (log-odds)".

**Head to head.** For two players A and B: `P(A beats B) = 1 / (1 + e^−(S_A − S_B))`. The same formula drives the tournament simulations.

**Effective Average.** The whole strength expressed in 3-dart-average points:

```
Effective Average = 3-dart average of the reference player + (S − S_ref) ÷ β_avg-per-point
                  = the player's own 3-dart average (L30) + form and Elo converted into average points
```

Example: Luke Littler, 3-Dart Average (L30) 98.0, Effective Average 103.1. His Elo, form and experience are worth about 5 extra average points against a typical top-32 field.

**PI Major.** If a majors-only predictor is selected (today none: Big-Stage Delta fails the stability rule, see Step 1), each player also gets a *PI Major*: the same calculation including that predictor, used for matches on majors and in all major tournament predictions. While no majors-only predictor is selected, PI Major equals PI.

**"Typical match"** means the mix of formats in the data, which is mostly Players Championship and European Tour matches (first to 6 legs). Tournament simulations translate match probabilities into the specific format of each round.

---

## Validation (test period 2026, never used for fitting or selection)

| Model | Matches | AUC | Log loss | Brier |
|---|---|---|---|---|
| **PI model** (3-dart average, Elo, form, experience) | 4,955 | **0.684** | **0.638** | **0.224** |
| 3-dart average only | 4,955 | 0.679 | 0.641 | 0.225 |
| Elo only | 4,955 | 0.661 | 0.652 | 0.230 |
| PI model, majors only | 424 | 0.707 | 0.626 | 0.219 |

- **AUC** (0.5 = coin flip, 1 = perfect): darts has a lot of randomness, so ~0.69 is a strong result for pre-match information alone.
- **Calibration:** when the model says 78 %, the favourite wins 79 % of the time. Every decile matches within a few percentage points (`darts_gold.pi_calibration`).

---

## Key test: does the PI beat the official PDC ranking?

If the model didn't predict winners better than the PDC Order of Merit, it would add nothing. So it is tested against it on every refit:

- **Baseline:** `P(A beats B) = 1 / (1 + e^−(b · (ln rank_B − ln rank_A)))`, with each player's Order of Merit rank **as of the match date** (the latest official snapshot before it, from the Wikipedia data module `Module:DartsRankings/data/PDC Rankings`). `b` is fitted on the same training matches as the PI model. Unranked players count as rank 500.
- **Test:** the untouched 2026 matches, plus majors only. A **paired bootstrap** (1,000 resamples of the same matches for both models) gives a 95 % interval for the log-loss gain. The model counts as better only if the whole interval is above zero.

**Result** (data until 28 Oct 2026, run 2026-10-30; stored per model version in `darts_gold.pi_benchmark`):

| Test matches | Model | Favourite won | Log loss | Brier | AUC |
|---|---|---|---|---|---|
| **All 2026 (4,986)** | **PI model** | **63.1 %** | **0.639** | **0.224** | **0.683** |
| | PDC Order of Merit | 57.9 % | 0.671 | 0.239 | 0.615 |
| **Majors 2026 (431)** | PI model | 65.2 % | 0.629 | 0.219 | 0.702 |
| | PDC Order of Merit | 67.1 % | 0.636 | 0.223 | 0.711 |

- **All matches:** log-loss gain +0.032, 95 % interval [+0.025, +0.038], p < 0.001. **The PI predicts winners significantly better than the official ranking.**
- **Majors only:** gain +0.008, interval [−0.014, +0.028], p = 0.25, so **no significant difference**. On majors, the field is mostly established top-32 players whose 2-year prize money already describes their strength well. The model's edge comes from the rest of the field: players in new form, newcomers, and players whose ranking lags behind their level.
- Idea for the next refit: add the Order of Merit rank itself as a candidate predictor. It goes through the same selection rules.

## Model versions (promotion policy)

Every refresh refits the model, but a new fit is only a **candidate**. It replaces the active model only if ([src/analytics/registry.py](../src/analytics/registry.py)):

1. the selected predictors are the same (a change in what the index is made of is a methodology change and needs a human decision),
2. its test log loss is not worse than the active model's by more than 0.005,
3. no predictor's share of the index moved by more than 15 percentage points.

Otherwise the active model stays, the health report shows why, and the PI does not jump because of noise. The decisions are stored in `darts_gold.pi_model_registry`. The PI, the tournament predictions and the app always use the **active** version.

---

## Limitations

- **Coverage:** only the current top 150 of the prize-money ranking are tracked. Everyone else, including players who were strong in 2021–2022 but have since dropped out, appears only as an opponent of a tracked player: their Elo comes from those matches alone, and matches between two untracked players are not in the data.
- **All events count** in the averages: Pro Tour, European Tour, majors, and also lower-level events some players play (Challenge Tour, World Series exhibitions). The Elo partly corrects for opponent strength.
- **Big-Stage Delta** is related to results on majors in a single fit (p = 0.004 in the first test), but it is not stable: significant in 73 % of bootstrap samples with data since 2023 and in only 61 % with data since 2021. A longer history made the evidence weaker, not stronger. It stays a candidate and is re-tested on every refit, and it can still be shown in player profiles as a descriptive number.
- **Linear model:** effects add up. Interactions (e.g. form mattering more for young players) are not modelled.

---

## Reproducibility

| What | Where |
|---|---|
| Predictor definitions | [src/analytics/features.py](../src/analytics/features.py) |
| Opponent-Weighted Elo | [src/analytics/elo.py](../src/analytics/elo.py) |
| Selection, weights, scale | [src/analytics/model.py](../src/analytics/model.py), [src/analytics/pipeline.py](../src/analytics/pipeline.py) |
| Databricks notebooks | [04_pi_model.py](../src/notebooks/04_pi_model.py), [05_performance_index.py](../src/notebooks/05_performance_index.py) |
| Majors list | [config/majors.yml](../config/majors.yml) |

| Gold table | Contents |
|---|---|
| `darts_gold.pi_coefficients` | weights, standard errors, p-values, CIs, bootstrap shares, conversion to average points (per model version) |
| `darts_gold.pi_selection_log` | every keep/drop decision with its reason |
| `darts_gold.pi_metrics` | AUC, log loss, Brier on the test period, PI model vs. baselines |
| `darts_gold.pi_calibration` | predicted vs. observed win rate by decile |
| `darts_gold.pi_elo_tuning` | log loss of each Elo parameter pair |
| `darts_gold.pi_correlations` | correlation matrix of the candidate predictors |
| `darts_gold.elo_history` | every player's Elo before and after each match |
| `darts_gold.performance_index` | PI, PI Major, Effective Average, contributions, monthly history |

The model is refitted on every full refresh and stored under a new version (`v<date>`). Earlier versions remain queryable.
