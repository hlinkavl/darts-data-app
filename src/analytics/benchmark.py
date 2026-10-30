"""Key test: does the PI model predict match winners better than the official PDC Order of Merit?

Baseline: P(A beats B) = 1 / (1 + e^-(b * (ln rank_B - ln rank_A))), with each player's Order of Merit rank as of
the match date (latest snapshot before it) and b fitted on the same training matches as the PI model.
Comparison on the untouched test period: accuracy, log loss, Brier, and a paired bootstrap of the log-loss
difference (same matches resampled for both models), which tells whether the model is *significantly* better.
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .model import metrics

UNRANKED = 500          # players outside the Order of Merit (rank cut-off is ~450)
BOOTSTRAP = 1000
SEED = 42


def ranks_as_of(pairs: pd.DataFrame, rankings: pd.DataFrame) -> pd.DataFrame:
    """Add rank_a / rank_b: each player's Order of Merit rank in the latest snapshot before the match date."""
    r = rankings[["snapshot_date", "player_key", "rank"]].dropna().assign(
        snapshot_date=lambda d: pd.to_datetime(d["snapshot_date"]).astype("datetime64[ns]"),
        player_key=lambda d: d["player_key"].astype("int64"))
    r = r.sort_values("snapshot_date")
    out = pairs.assign(match_date=pd.to_datetime(pairs["match_date"]).astype("datetime64[ns]"), _row=np.arange(len(pairs)),
                       player_a=pairs["player_a"].astype("int64"), player_b=pairs["player_b"].astype("int64"))
    out = out.sort_values("match_date")
    for side in ("a", "b"):
        out = pd.merge_asof(out, r.rename(columns={"player_key": f"player_{side}", "rank": f"rank_{side}"}),
                            left_on="match_date", right_on="snapshot_date", by=f"player_{side}",
                            allow_exact_matches=False).drop(columns="snapshot_date")
    out[["rank_a", "rank_b"]] = out[["rank_a", "rank_b"]].fillna(UNRANKED)
    return out.sort_values("_row").drop(columns="_row").reset_index(drop=True)


def _rank_feature(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"log_rank_gap": np.log(df["rank_b"].to_numpy()) - np.log(df["rank_a"].to_numpy())})


def compare(fit_pairs: pd.DataFrame, test_pairs: pd.DataFrame, p_model: np.ndarray, rankings: pd.DataFrame,
            label: str = "test") -> pd.DataFrame:
    """Model vs Order of Merit on test_pairs. p_model = the PI model's P(A wins) for test_pairs (honest
    predictions: model fitted on fit_pairs only)."""
    fit_r, test_r = ranks_as_of(fit_pairs, rankings), ranks_as_of(test_pairs, rankings)
    ranking_model = sm.Logit(fit_r["y"].to_numpy(), _rank_feature(fit_r)).fit(disp=0)
    p_rank = np.asarray(ranking_model.predict(_rank_feature(test_r)))
    y = test_r["y"].to_numpy()
    p_model = np.clip(np.asarray(p_model), 1e-6, 1 - 1e-6)
    p_rank = np.clip(p_rank, 1e-6, 1 - 1e-6)

    def ll(p):
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))

    diff = ll(p_rank) - ll(p_model)              # > 0: the model is better on that match
    rng = np.random.default_rng(SEED)
    boots = np.array([diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(BOOTSTRAP)])
    rows = []
    for name, p in (("PI model", p_model), ("PDC Order of Merit", p_rank)):
        m = metrics(y, p)
        rows.append({"dataset": label, "model": name, **m,
                     "favourite_won_pct": 100 * np.mean((p > 0.5) == (y == 1)),
                     "ranked_share_pct": 100 * np.mean((test_r["rank_a"] < UNRANKED) & (test_r["rank_b"] < UNRANKED))})
    out = pd.DataFrame(rows)
    out["log_loss_gain"] = float(diff.mean())                    # ranking log loss minus model log loss
    out["gain_ci_low"], out["gain_ci_high"] = np.quantile(boots, [0.025, 0.975])
    out["p_value"] = float(np.mean(boots <= 0))                  # one-sided: share of resamples with no gain
    out["model_significantly_better"] = bool(out["gain_ci_low"].iloc[0] > 0)
    out["ranking_coefficient"] = float(ranking_model.params.iloc[0])
    return out


def walk_forward(pairs: pd.DataFrame, predictor_sets: dict[str, list[str]], rankings: pd.DataFrame,
                 start: str = "2023-07-01", freq: str = "QS", majors_only: bool = True) -> pd.DataFrame:
    """Out-of-sample predictions with quarterly refits: for each quarter, every predictor set and the ranking
    baseline are fitted on matches before the quarter and predict the quarter's (major) matches.
    Returns one row per predicted match with one probability column per model."""
    from .model import fit_logit, predict

    ranked = ranks_as_of(pairs, rankings)
    ranked["log_rank_gap"] = _rank_feature(ranked)["log_rank_gap"].to_numpy()
    dates = pd.to_datetime(ranked["match_date"])
    edges = list(pd.date_range(start, dates.max() + pd.Timedelta(days=1), freq=freq)) + [dates.max() + pd.Timedelta(days=1)]
    out = []
    for q0, q1 in zip(edges[:-1], edges[1:]):
        train = ranked[dates < q0]
        test = ranked[(dates >= q0) & (dates < q1)]
        if majors_only:
            test = test[test["is_major"]]
        if test.empty or len(train) < 1000:
            continue
        rows = test[["match_key", "match_date", "is_major", "y"]].copy()
        for name, cols in predictor_sets.items():
            scale = train[cols].std()
            rows[name] = predict(fit_logit(train, cols, scale), test, cols, scale)
        rank_model = sm.Logit(train["y"].to_numpy(), train[["log_rank_gap"]]).fit(disp=0)
        rows["PDC Order of Merit"] = np.asarray(rank_model.predict(test[["log_rank_gap"]]))
        out.append(rows.assign(quarter=q0.date()))
    return pd.concat(out, ignore_index=True)


def summarize(preds: pd.DataFrame, models: list[str], baseline: str = "PDC Order of Merit") -> pd.DataFrame:
    """Metrics per model and the paired-bootstrap log-loss gain of each model over the baseline."""
    y = preds["y"].to_numpy()
    rng = np.random.default_rng(SEED)
    idx = [rng.integers(0, len(y), len(y)) for _ in range(BOOTSTRAP)]

    def ll(p):
        p = np.clip(p, 1e-6, 1 - 1e-6)
        return -(y * np.log(p) + (1 - y) * np.log(1 - p))

    base = ll(preds[baseline].to_numpy())
    rows = []
    for name in models + [baseline]:
        p = preds[name].to_numpy()
        diff = base - ll(p)
        boots = np.array([diff[i].mean() for i in idx])
        rows.append({"model": name, **metrics(y, p), "favourite_won_pct": 100 * np.mean((p > 0.5) == (y == 1)),
                     "gain_vs_ranking": diff.mean(), "gain_ci_low": np.quantile(boots, 0.025),
                     "gain_ci_high": np.quantile(boots, 0.975), "p_value": float(np.mean(boots <= 0))})
    return pd.DataFrame(rows)
