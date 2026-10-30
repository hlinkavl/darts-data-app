# Performance Index (PI): Methodology

The Performance Index rates every tracked PDC player on a **0–10 scale**:

> **PI = 10 × the probability that the player beats an average top-32 player in a typical match.**

A PI of 7.0 means a 70 % chance against a typical top-32 opponent. A PI of 5.0 means the player *is* a typical top-32 player. A PI of 2.0 means a 20 % chance. Because the scale is a probability, any two PIs can be turned into a head-to-head prediction.

**Does it work?** The PI predicts match winners significantly better than the official PDC Order of Merit, both over all matches and **on majors** (1,825 major matches predicted ahead of time, log loss 0.628 vs 0.652, p < 0.001). See [Key test](#key-test-does-the-pi-beat-the-official-pdc-ranking).

All numbers in this document are from model run *2026-10-31* (data until 28 Oct 2026). They are recomputed on every refresh and stored in Databricks (tables at the end); the app's *Methodology* page reads those tables.

---

## How to read the PI

**1. The PI is measured against one benchmark: the average top-32 player.** The benchmark is the average profile of the 32 strongest players, roughly the level of the 14th-best player. Luke Littler's PI of 7.35 means he beats *that* player in 73.5 % of typical matches. It does **not** mean he beats every top-32 player 73.5 % of the time.

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

In longer formats luck evens out more and the favourite's chance rises; in shorter ones it falls. The tournament simulations convert every probability to the format of the round ([TOURNAMENT_PREDICTIONS.md](TOURNAMENT_PREDICTIONS.md)).

**4. The probabilities are calibrated.** Each match gets its own probability, from about 50 % for close match-ups to about 90 % for heavy favourites. On the 2026 test data (never used for fitting), matches sorted into 10 groups by predicted probability are won about as often as predicted. For example, in the group where the model predicted 77.4 %, the favourites won 77.6 %. So a probability of X % can be read literally.

---

## The three steps

1. **Select predictors**: keep only the statistics that predict match results, tested on data the model has not seen.
2. **Weight them**: the weights are the coefficients of a logistic regression, not hand-picked numbers.
3. **Convert to the 0–10 scale**: compare each player with the average top-32 player.

---

## What the model learned from

**Sources.**
- **Until 28 Oct 2026: Darts Orakel** (exact points and darts, plus first-9, checkout and 180s). Orakel blocked our client on 30 Oct 2026.
- **From then on: Mastercaller** (3-dart averages, stats by iDarts). Mastercaller has no dart counts, so darts are estimated as `legs × 1503 / average` (sets × 4 legs). Checked on Orakel data, where the exact numbers are known: the 3-Dart Average (L30) moves by −0.06 points on average, 95 % within ±0.24, which is negligible next to a spread of ~4.5 points between players. Matches present in both sources come from Orakel.
- **The official PDC Order of Merit** (tracked players, the Order of Merit predictor and the key test) comes from the Wikipedia data module `Module:DartsRankings/data/PDC Rankings`, current and as of any past date.

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

### No look-ahead

Every predictor describes a player **before** the match, computed only from earlier matches. Within a day, matches are ordered **by round** (Last 128 before Last 64 … before the final), not by match id. Time-window predictors ignore the whole match day. So the model never sees the result it is trying to predict, and a test (`tests/test_analytics.py`) guards the ordering.

> **Correction, 31 Oct 2026.** Earlier versions ordered same-day matches by Darts Orakel's match id. Orakel numbers single-day Players Championship events *backwards* (the final has the lowest id), so a first-round match could "see" the same player's later rounds that day, which only exist if he won. This mainly inflated *Experience*, which no longer passes selection, and slightly affected Elo and the L30 averages. All numbers in this document were recomputed after the fix.

---

## Candidate predictors

"L30" means the player's last 30 matches before the one being predicted. Averages are pooled, as **total points ÷ total darts × 3**, so a long match counts more than a short one. Every candidate is defined so that **higher is better**. The last seven were added on 31 Oct 2026, aimed at majors, and fixed before testing.

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

### Opponent-Weighted Elo in detail

A classic Elo rating, replayed over every match since 2021 in chronological order. Everyone starts at 1500.

```
expected win chance of A = 1 / (1 + 10^((Elo_B − Elo_A) / 400))
new Elo_A = Elo_A + K × m × (result − expected)        result = 1 for a win, 0 for a loss
```

- A win over a much stronger player (expected ≈ 0.2) earns 0.8 × K points; a win over a much weaker one (expected ≈ 0.9) only 0.1 × K. That is why it is called *opponent-weighted*.
- **K and m are tuned** on the training period (K ∈ {16, 24, 32, 40, 48}, m = 1 or 1.5 on majors, lowest log loss wins). Current model: **K = 16, m = 1.5**.
- **Burn-in:** a player's Elo is only used after 30 matches.
- Limitation: opponents outside the tracked players are rated only from their matches against tracked players.

### Big-Stage Delta in detail

Does a player raise (or lose) their level on the big stage? The raw delta is the player's 3-dart average **on majors** minus their 3-dart average **in all matches**, both over the last 24 months, shrunk toward 0 for small samples: `raw delta × n / (n + 10)`, n = major matches in the last 24 months. It is a **majors-only** predictor: it enters the model only for matches on a major.

---

## The model behind every step

Each match becomes one row: **y = 1 if player A won**, and each predictor is the **difference A − B**. Players are assigned to A and B at random. A **logistic regression without an intercept** is fitted:

```
P(A beats B) = 1 / (1 + e^−(S_A − S_B))        S = β₁·x₁/sd₁ + β₂·x₂/sd₂ + …
```

`S` is the player's **strength**. Swapping A and B flips the prediction exactly, which is why there is no intercept. Predictors are divided by their standard deviation (`sd`, from the training data), so each β answers *"how much does a one-standard-deviation advantage change the log-odds of winning?"* and the βs are comparable.

---

## Step 1: Selecting predictors

A candidate must pass **all three** filters.

**1a. Correlation filter.** Two predictors that measure almost the same thing (|r| > 0.8) make the weights unstable. From each such pair we keep the one that predicts better **on its own** (log loss of a one-predictor model over 5 consecutive time blocks of the training data).

**1b. Significance and out-of-sample check.** Backward elimination on training data: remove a predictor with a negative coefficient (a better value must never lower the win chance) or with p ≥ 0.05, one at a time. Then each remaining predictor must improve log loss on the **validation** period; if the model is just as good without it, it goes.

**1c. Bootstrap stability.** Refit on 500 bootstrap samples of the training data. A predictor stays only if it is significant (p < 0.05) and positive in **at least 80 %** of them.

Every decision and its reason is stored in `darts_gold.pi_selection_log`.

### Result: all 16 tested predictors

**In the index (4):**

| Predictor | Why it is in |
|---|---|
| **3-Dart Average (L30)** | The strongest single predictor of who wins. Significant in 100 % of bootstrap samples. |
| **Opponent-Weighted Elo** | Adds what the average doesn't know: how strong the beaten opponents were. 100 % of samples. |
| **Form (L10 vs L30)** | A player on an upswing wins more than their L30 average suggests. 100 % of samples. |
| **PDC Order of Merit (log rank)** | Adds the long-term record on the stages with the most prize money (majors), which recent averages and Elo don't fully capture. 100 % of samples. |

**Tested and left out (12):**

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
| Big-Stage Delta (majors only) | 1c | Significant in single fits, but not stable: significant in only 71 % of bootstrap samples (threshold 80 %). |

**Big-Stage Delta**, the hypothesis that some players raise their level on the big stage, has been tested several ways. It is significant in some single fits (p = 0.004 on majors in the first test, p = 0.03 in a majors-only model), but never stable: 73 % of bootstrap samples with data since 2023, 61–71 % with data since 2021. The effect may exist, but it is small and depends on which matches happen to be in the sample. It is therefore **shown as an information-only indicator** in player profiles and on major match cards, with no effect on the PI, and re-tested on every refit.

---

## Step 2: Weights

The final weights are the coefficients of the logistic regression with the selected predictors, refitted on **all** matches:

| Predictor | β (per 1 sd) | Share of the index | In 3-dart-average points |
|---|---|---|---|
| 3-Dart Average (L30) | 0.458 | 53 % | 1 point = 1 point |
| Opponent-Weighted Elo | 0.181 | 21 % | 100 Elo points = 1.5 average points |
| Form (L10 vs L30) | 0.128 | 15 % | 1 point of form = 0.48 average points |
| PDC Order of Merit (log rank) | 0.100 | 12 % | halving your rank number (e.g. #20 → #10) = 0.47 average points |

All four have p < 0.001. **Share of the index** = |β| ÷ sum of all |β|. **In 3-dart-average points** converts each predictor into the unit everyone in darts understands. Weights, standard errors, 95 % confidence intervals and bootstrap shares are in `darts_gold.pi_coefficients`.

---

## Step 3: The 0–10 scale

1. Compute every player's strength `S` with the current weights.
2. The **reference player** is the *average profile* of the 32 strongest players at that date (mean of each predictor). Because the model is linear, the reference strength is the mean strength of those 32 players.
3. Convert: `PI = 10 × 1 / (1 + e^−(S − S_ref))`.

`S − S_ref` splits exactly into one **contribution** per predictor, `β × (x − x_ref) / sd`. So every PI can be explained. For example, Littler's PI 7.35 = Elo +0.39, 3-dart average +0.35, Order of Merit +0.19, form +0.09 (log-odds).

**Effective Average** expresses the whole strength in 3-dart-average points: the player's own 3-dart average (L30) plus Elo, form and Order of Merit converted into average points. Example: Littler, 3-Dart Average (L30) 98.2, **Effective Average 104.7**. His Elo, ranking and form are worth about 6.5 extra average points against a typical top-32 field.

**PI Major.** If a majors-only predictor is selected (today none), each player also gets a *PI Major* including it, used for matches on majors. While none is selected, PI Major equals PI.

**Pair-specific predictors** (Head-to-Head) never enter a player's PI. If one is ever selected, it adjusts the probability of the specific match only.

---

## Validation (test period 2026, never used for fitting or selection)

| Model | Matches | AUC | Log loss | Brier |
|---|---|---|---|---|
| **PI model** (average, form, Elo, Order of Merit) | 4,987 | **0.681** | **0.639** | **0.225** |
| 3-dart average only | 4,987 | 0.677 | 0.642 | 0.226 |
| Elo only | 4,987 | 0.661 | 0.652 | 0.230 |
| PI model, majors only | 431 | 0.708 | 0.622 | 0.217 |

- **AUC** (0.5 = coin flip, 1 = perfect): darts has a lot of randomness, so ~0.68 is a strong result for pre-match information alone.
- **Calibration:** in every decile the favourites win about as often as predicted (`darts_gold.pi_calibration`).

---

## Key test: does the PI beat the official PDC ranking?

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

## Model versions (promotion policy)

Every refresh refits the model, but a new fit is only a **candidate**. It replaces the active model only if ([src/analytics/registry.py](../src/analytics/registry.py)):

1. the selected predictors are the same (a change in what the index is made of needs a human decision),
2. its test log loss is not worse than the active model's by more than 0.005,
3. no predictor's share of the index moved by more than 15 percentage points.

Otherwise the active model stays and the health report shows why, so the PI does not jump because of noise. Decisions are stored in `darts_gold.pi_model_registry`; the PI, the tournament predictions and the app always use the **active** version.

---

## Limitations

- **Coverage:** only the 150 best players in the Order of Merit are tracked. Everyone else appears only as an opponent of a tracked player: their Elo comes from those matches alone, and matches between two untracked players are not in the data.
- **All events count** in the averages, including lower-level events some players play. The Elo and the Order of Merit partly correct for the level of opposition.
- **Mastercaller data** (from 30 Oct 2026) has estimated dart counts (see above) and no first-9, checkout or 180s.
- **Linear model:** effects add up; interactions are not modelled.

---

## Reproducibility

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
