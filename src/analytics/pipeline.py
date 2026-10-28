"""End-to-end Performance Index pipeline, shared by the Databricks notebooks and local tests."""

from dataclasses import dataclass
from itertools import product

import pandas as pd

from . import elo, features, model

VALIDATION_FROM = "2025-04-01"
TEST_FROM = "2026-01-01"
ELO_GRID = [elo.EloParams(k, m) for k, m in product([16, 24, 32, 40, 48], [1.0, 1.5])]


@dataclass
class ModelRun:
    version: str
    elo_params: elo.EloParams
    elo_tuning: pd.DataFrame
    elo_history: pd.DataFrame
    selection_log: pd.DataFrame
    correlations: pd.DataFrame
    coefficients: pd.DataFrame
    metrics: pd.DataFrame
    calibration: pd.DataFrame
    data_summary: pd.DataFrame
    n_pairs: int


def fit(player_matches: pd.DataFrame, matches: pd.DataFrame, version: str) -> ModelRun:
    """Steps 1 and 2 of the methodology: tune Elo, select predictors, fit weights, evaluate."""
    matches = matches.assign(match_date=pd.to_datetime(matches["match_date"]))
    elo_params, elo_tuning = elo.tune(matches, ELO_GRID, model.ELO_BURN_IN, pd.Timestamp(VALIDATION_FROM))
    elo_history = elo.run_elo(matches, elo_params)

    candidates = list(features.CANDIDATES)
    feats = features.point_in_time_features(player_matches, elo_history)
    pairs = model.build_pairs(feats, candidates)
    split = model.time_split(pairs, VALIDATION_FROM, TEST_FROM)
    scale = split.train[candidates].std()

    log = model.SelectionLog()
    kept, corr = model.step1a_correlation(split, candidates, scale, log)
    kept = model.step1b_significance(split, kept, scale, log)
    selected, share = model.step1c_bootstrap(split, kept, scale, log)

    # Honest evaluation: fit on train + validation, score the untouched test period (2026).
    fit_data = pd.concat([split.train, split.validation])
    rows, calib = [], None
    for name, cols in [("selected", selected), ("avg_l30 only", ["avg_l30"]), ("elo only", ["elo"])]:
        r = model.fit_logit(fit_data, cols, scale)
        for subset, df in [("test", split.test), ("test majors", split.test[split.test["is_major"]])]:
            p = model.predict(r, df, cols, scale)
            rows.append({"model": name, "predictors": ", ".join(cols), "dataset": subset, **model.metrics(df["y"].to_numpy(), p)})
            if name == "selected" and subset == "test":
                calib = model.calibration(df["y"].to_numpy(), p)

    # Production weights: same predictors, refit on all matches.
    final = model.fit_logit(pairs, selected, scale)
    coefficients = model.coefficient_table(final, selected, scale, share)
    coefficients.insert(1, "display_name", coefficients["predictor"].map(features.CANDIDATES))

    tuning = elo_tuning.assign(selected=lambda t: (t.k == elo_params.k) & (t.major_multiplier == elo_params.major_multiplier))
    return ModelRun(
        version=version, elo_params=elo_params, elo_tuning=tuning, elo_history=elo_history,
        selection_log=pd.DataFrame(log.entries), correlations=corr, coefficients=coefficients,
        metrics=pd.DataFrame(rows), calibration=calib, data_summary=model.data_summary(split),
        n_pairs=len(pairs),
    )


def score(player_matches: pd.DataFrame, elo_history: pd.DataFrame, coefficients: pd.DataFrame,
          player_keys: list[int], as_of_dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Step 3: PI, contributions and Effective Average for each player at each as-of date."""
    snapshots = []
    for as_of in as_of_dates:
        snap = features.features_as_of(player_matches, elo_history, as_of, player_keys)
        snapshots.append(model.score_players(snap, coefficients))
    return pd.concat(snapshots, ignore_index=True)
