# Performance Index (PI): Methodology

The Performance Index rates every tracked PDC player on a **0–10 scale**:

> **PI = 10 × the probability that the player beats an average top-32 player in a typical match.**

A PI of 7.0 means a 70 % chance against a typical top-32 opponent. A PI of 5.0 means the player *is* a typical top-32 player. A PI of 2.0 means a 20 % chance. Because the scale is a probability, any two PIs can be turned into a head-to-head prediction (see [Step 3](#step-3-the-0-10-scale)).

## How to read the PI

**1. The PI is measured against one benchmark: the average top-32 player.** The benchmark is the average profile of the 32 strongest players, roughly the level of the 14th-best player. Luke Littler's PI of 7.04 means he beats *that* player in 70 % of typical matches. It does **not** mean he beats every top-32 player 70 % of the time.

**2. Any specific match-up comes from the two PIs.** Each PI encodes a strength. The chance of A beating B depends on the difference between the two strengths:

```
strength from PI:   s = ln( PI / (10 − PI) )            (the log-odds of beating the benchmark)
P(A beats B)      = 1 / (1 + e^−(s_A − s_B))
```

Example, Littler (PI 7.04) vs Ryan Searle (PI 4.28): s = ln(7.04 / 2.96) = 0.87 and ln(4.28 / 5.72) = −0.29, so P = 1 / (1 + e^−1.16) = **76 %**. The PIs are not subtracted directly: 7.04 − 4.28 = 2.76 has no meaning as a probability.

Littler against different opponents (model v2026-10-28):

| Opponent (PI rank) | Opponent's PI | Littler wins |
|---|---|---|
| #2 Luke Humphries | 6.28 | 58 % |
| #3 Gerwyn Price | 5.83 | 63 % |
| #10 Luke Woodhouse | 5.24 | 68 % |
| *average top-32 player* | *5.00* | *70 %* |
| #16 Chris Dobey | 4.80 | 72 % |
| #32 Ryan Searle | 4.28 | 76 % |
| #64 Gabriel Clemens | 3.29 | 83 % |
| #100 Adam Sevada | 2.55 | 87 % |

Two players with the same PI have a 50 % chance against each other, whatever their PI is.

**3. "Typical match" means first to 6 legs (best of 11 legs).** This is the standard format of the Players Championship and European Tour, and the format of 77 % of the matches the model learned from (matches between two tracked players since 2023):

| Format | Share of matches |
|---|---|
| **First to 6 legs (best of 11)** | **77 %** |
| First to 4–5 legs (best of 7–9) | 13 % |
| First to 7–11 legs (best of 13–21), e.g. Grand Slam, Masters, European Championship knockouts | 6 % |
| Sets (World Championship, World Grand Prix) | 2 % |
| Other short formats (first to 2–3 legs) | 1 % |

So PI 7.04 means: Littler wins 70 % of best-of-11-legs matches against the average top-32 player. In longer formats luck evens out more and the favourite's chance rises. Littler vs Searle at the World Championship (first to 3 sets in round 1, up to first to 7 sets in the final, each set first to 3 legs) would be above 76 %. Shorter formats work the other way. The tournament simulations convert every probability to the format of the round (see [DESIGN.md](DESIGN.md#tournament-overview)).

**4. The probabilities are calibrated.** Each match gets its own probability, from about 50 % for close match-ups to about 90 % for heavy favourites. On the 2026 test data (never used for fitting), matches were sorted by predicted probability into 10 groups. In each group the favourites won about as often as predicted. For example, in the group where the model predicted 77.9 % on average, the favourites won 77.8 %. So a probability of X % can be read literally. See [Validation](#validation-test-period-2026-never-used-for-fitting-or-selection).

---

The index is built in three transparent steps:

1. **Select predictors**: keep only the statistics that predict match results, tested on data the model has not seen.
2. **Weight them**: the weights are the coefficients of a logistic regression, not hand-picked numbers.
3. **Convert to the 0–10 scale**: compare each player with the average top-32 player.

Every number in this document is recomputed on each refresh and stored in Databricks (tables listed at the end). The app's *Methodology* page reads those tables, so it always shows the current model.

---

## Data

- **Matches:** every match of the 150 players in the 2-year prize-money ranking (PDC Order of Merit equivalent) since 1 Jan 2023, from Darts Orakel. Each player's match row has points and darts thrown, first-9 points and darts, checkouts hit and attempted, and 180s.
- **Majors:** the 10 televised PDC events in [config/majors.yml](../config/majors.yml): World Championship, Masters, UK Open, Premier League, World Matchplay, World Series Finals, World Grand Prix, European Championship, Grand Slam and Players Championship Finals.
- **Observations for the model:** matches where **both** players are tracked and have enough history (at least 10 matches with stats and 30 matches for the Elo, see below). This is roughly 17,600 matches.

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

A classic Elo rating, replayed over every match since 2023 in date order. Everyone starts at 1500.

```
expected win chance of A = 1 / (1 + 10^((Elo_B − Elo_A) / 400))
new Elo_A = Elo_A + K × m × (result − expected)        result = 1 for a win, 0 for a loss
```

- A win over a much stronger player (expected ≈ 0.2) earns 0.8 × K points. A win over a much weaker player (expected ≈ 0.9) earns only 0.1 × K. That is why it is called *opponent-weighted*.
- `m` = 1.5 on majors if that improves predictions, otherwise 1.
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

### Result of the current model (v2026-10-28)

| Predictor | Decision | Reason |
|---|---|---|
| First-9 Average (L30) | ❌ 1a | r = 0.94 with 3-Dart Average, which predicts better alone |
| Win Rate (L30) | ❌ 1a | r = 0.81 with Opponent-Weighted Elo, which predicts better alone |
| Checkout % (L30) | ❌ 1b | negative coefficient once the average is in the model |
| 180s per 100 Darts (L30) | ❌ 1b | negative coefficient once the average is in the model |
| Experience | ❌ 1b | p = 0.36 |
| Big-Stage Delta (majors only) | ❌ 1c | significant in 1b, but only in 73 % of bootstrap samples (< 80 %) |
| **3-Dart Average (L30)** | ✅ | significant in 100 % of bootstrap samples |
| **Form (L10 vs L30)** | ✅ | significant in 100 % of bootstrap samples |
| **Opponent-Weighted Elo** | ✅ | significant in 99.8 % of bootstrap samples |

Checkout % and 180s are not useless. They are part of what the 3-dart average already measures, so they add nothing on top of it.

---

## Step 2: Weights

The final weights are the coefficients of the logistic regression with the selected predictors, refitted on **all** matches. Current model:

| Predictor | β (per 1 sd) | p-value | Share of the index | In 3-dart-average points |
|---|---|---|---|---|
| 3-Dart Average (L30) | 0.543 | < 0.001 | 63 % | 1 point = 1 point |
| Form (L10 vs L30) | 0.151 | < 0.001 | 18 % | 1 point of form = 0.48 average points |
| Opponent-Weighted Elo | 0.163 | < 0.001 | 19 % | 100 Elo points = 1.2 average points |

- **Share of the index** = |β| ÷ sum of all |β|.
- **In 3-dart-average points** converts each predictor into the unit everyone in darts understands. Example: a player whose last 10 matches are 2 points above their L30 average gets the same boost as +0.95 points of 3-dart average.

Weights, standard errors, 95 % confidence intervals and bootstrap shares are stored in `darts_gold.pi_coefficients`.

---

## Step 3: The 0–10 scale

1. Compute every player's strength `S` with the current weights.
2. The **reference player** is the *average profile* of the 32 strongest players at that date (mean of each predictor). Because the model is linear, the reference strength is simply the mean strength of those 32 players.
3. Convert:

```
PI = 10 × 1 / (1 + e^−(S − S_ref))
```

`S − S_ref` splits exactly into one **contribution** per predictor, `β × (x − x_ref) / sd`. So every PI can be explained, e.g. "PI 7.0 = 3-dart average +0.37, form +0.10, Elo +0.40 (log-odds)".

**Head to head.** For two players A and B: `P(A beats B) = 1 / (1 + e^−(S_A − S_B))`. The same formula drives the tournament simulations.

**Effective Average.** The whole strength expressed in 3-dart-average points:

```
Effective Average = 3-dart average of the reference player + (S − S_ref) ÷ β_avg-per-point
                  = the player's own 3-dart average (L30) + form and Elo converted into average points
```

Example: Luke Littler, 3-Dart Average (L30) 98.0, Effective Average 102.1. His form and Elo are worth about 4 extra average points against a typical top-32 field.

**PI Major.** If a majors-only predictor is selected (today: none, see Step 1), each player also gets a *PI Major*: the same calculation including that predictor, used for matches on majors and in all major tournament predictions. While no majors-only predictor is selected, PI Major equals PI.

**"Typical match"** means the mix of formats in the data, which is mostly Players Championship and European Tour matches (first to 6 legs). Tournament simulations translate match probabilities into the specific format of each round.

---

## Validation (test period 2026, never used for fitting or selection)

| Model | Matches | AUC | Log loss | Brier |
|---|---|---|---|---|
| **PI model** (3-dart average, form, Elo) | 4,942 | **0.686** | **0.637** | **0.223** |
| 3-dart average only | 4,942 | 0.679 | 0.641 | 0.225 |
| Elo only | 4,942 | 0.659 | 0.654 | 0.231 |
| PI model, majors only | 423 | 0.700 | 0.629 | 0.220 |

- **AUC** (0.5 = coin flip, 1 = perfect): darts has a lot of randomness, so ~0.69 is a strong result for pre-match information alone.
- **Calibration:** when the model says 78 %, the favourite wins 78 % of the time. Every decile matches within a few percentage points (`darts_gold.pi_calibration`).

---

## Limitations

- **Coverage:** only the top 150 of the prize-money ranking are tracked. Their opponents are rated from matches against tracked players only.
- **All events count** in the averages: Pro Tour, European Tour, majors, and also lower-level events some players play (Challenge Tour, World Series exhibitions). The Elo partly corrects for opponent strength.
- **Big-Stage Delta** has few observations per player (a top player plays roughly 30–60 major matches in 2 years). The current data is not enough for it to pass the stability rule. It is re-tested on every refit, and a longer history should give it a fairer test.
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
