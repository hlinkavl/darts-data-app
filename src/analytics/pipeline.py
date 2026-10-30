"""End-to-end Performance Index pipeline, shared by the Databricks notebooks and local tests."""

from dataclasses import dataclass
from itertools import product

import pandas as pd

from . import benchmark, elo, features, model

VALIDATION_FROM = "2025-04-01"
TEST_FROM = "2026-01-01"
ELO_GRID = [elo.EloParams(k, m) for k, m in product([16, 24, 32, 40, 48], [1.0, 1.5])]


@dataclass
class ModelRun:
    version: str
    elo_params: elo.EloParams
    elo_tuning: pd.DataFrame
    elo_history: pd.DataFrame
    major_elo_history: pd.DataFrame
    selection_log: pd.DataFrame
    correlations: pd.DataFrame
    coefficients: pd.DataFrame
    metrics: pd.DataFrame
    calibration: pd.DataFrame
    data_summary: pd.DataFrame
    n_pairs: int
    benchmark: pd.DataFrame | None = None


def fit(player_matches: pd.DataFrame, matches: pd.DataFrame, version: str,
        rankings: pd.DataFrame | None = None) -> ModelRun:
    """Steps 1 and 2 of the methodology: tune Elo, select predictors, fit weights, evaluate. With `rankings`
    (Order of Merit snapshots: snapshot_date, player_key, rank) also the key test against the PDC ranking."""
    matches = matches.assign(match_date=pd.to_datetime(matches["match_date"]))
    elo_params, elo_tuning = elo.tune(matches, ELO_GRID, model.ELO_BURN_IN, pd.Timestamp(VALIDATION_FROM))
    elo_history = elo.run_elo(matches, elo_params)
    major_elo_history = elo.run_elo(matches[matches["is_major"].astype(bool)], elo_params)

    candidates = [c for c in features.CANDIDATES if rankings is not None or c != "oom_rank"]
    feats = features.point_in_time_features(player_matches, elo_history, rankings, major_elo_history)
    pairs = model.build_pairs(feats, candidates)
    split = model.time_split(pairs, VALIDATION_FROM, TEST_FROM)
    scale = split.train[candidates].std()

    log = model.SelectionLog()
    kept, corr = model.step1a_correlation(split, candidates, scale, log)
    kept = model.step1b_significance(split, kept, scale, log)
    selected, share = model.step1c_bootstrap(split, kept, scale, log)

    # From here on only the selected predictors are needed. Matches from sources without detailed stats
    # (Mastercaller: no first-9, checkout, 180s) lack some candidates but have every selected predictor,
    # so weights and evaluation use all matches that have the selected predictors.
    baselines = sorted(set(selected) | {"avg_l30", "elo"})
    pairs = model.build_pairs(feats, baselines)
    split = model.time_split(pairs, VALIDATION_FROM, TEST_FROM)
    scale = split.train[baselines].std()

    # Honest evaluation: fit on train + validation, score the untouched test period (2026).
    fit_data = pd.concat([split.train, split.validation])
    rows, calib, bench = [], None, []
    for name, cols in [("selected", selected), ("avg_l30 only", ["avg_l30"]), ("elo only", ["elo"])]:
        r = model.fit_logit(fit_data, cols, scale)
        for subset, df in [("test", split.test), ("test majors", split.test[split.test["is_major"]])]:
            p = model.predict(r, df, cols, scale)
            rows.append({"model": name, "predictors": ", ".join(cols), "dataset": subset, **model.metrics(df["y"].to_numpy(), p)})
            if name == "selected" and subset == "test":
                calib = model.calibration(df["y"].to_numpy(), p)
            if name == "selected" and rankings is not None:
                bench.append(benchmark.compare(fit_data, df, p, rankings, label=subset))

    # Walk-forward test against the PDC Order of Merit: quarterly refits, every predicted match out of sample.
    # Many more major matches than the 2026 test period alone, so the comparison on majors has real power.
    if rankings is not None:
        for label, majors_only in (("walk-forward majors", True), ("walk-forward all", False)):
            preds = benchmark.walk_forward(pairs, {"PI model": selected}, rankings, majors_only=majors_only)
            summary = benchmark.summarize(preds, ["PI model"]).rename(columns={"gain_vs_ranking": "log_loss_gain"})
            summary["dataset"] = label
            summary["model_significantly_better"] = bool(summary.loc[summary.model == "PI model", "gain_ci_low"].iloc[0] > 0)
            bench.append(summary)

    # Production weights: same predictors, refit on all matches.
    final = model.fit_logit(pairs, selected, scale)
    coefficients = model.coefficient_table(final, selected, scale, share)
    coefficients.insert(1, "display_name", coefficients["predictor"].map(features.CANDIDATES))

    tuning = elo_tuning.assign(selected=lambda t: (t.k == elo_params.k) & (t.major_multiplier == elo_params.major_multiplier))
    return ModelRun(
        version=version, elo_params=elo_params, elo_tuning=tuning, elo_history=elo_history,
        major_elo_history=major_elo_history,
        selection_log=pd.DataFrame(log.entries), correlations=corr, coefficients=coefficients,
        metrics=pd.DataFrame(rows), calibration=calib, data_summary=model.data_summary(split),
        n_pairs=len(pairs), benchmark=pd.concat(bench, ignore_index=True) if bench else None,
    )


def score(player_matches: pd.DataFrame, elo_history: pd.DataFrame, coefficients: pd.DataFrame,
          player_keys: list[int], as_of_dates: list[pd.Timestamp], rankings: pd.DataFrame | None = None,
          major_elo_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Step 3: PI, contributions and Effective Average for each player at each as-of date."""
    snapshots = []
    for as_of in as_of_dates:
        snap = features.features_as_of(player_matches, elo_history, as_of, player_keys, rankings, major_elo_history)
        snapshots.append(model.score_players(snap, coefficients))
    return pd.concat(snapshots, ignore_index=True)



class StrengthHistory:
    """Strengths at any past date with weights refitted only on matches before that date (no look-ahead).
    Elo and predictors are computed once; each date then costs one regression and one feature snapshot.
    Strength includes majors-only terms, because it is used for majors."""

    def __init__(self, player_matches: pd.DataFrame, matches: pd.DataFrame, predictors: list[str],
                 elo_params: elo.EloParams, rankings: pd.DataFrame | None = None):
        self.player_matches = player_matches
        self.predictors = predictors
        self.rankings = rankings
        matches = matches.assign(match_date=pd.to_datetime(matches["match_date"]))
        self.history = elo.run_elo(matches, elo_params)
        self.major_history = elo.run_elo(matches[matches["is_major"].astype(bool)], elo_params)
        feats = features.point_in_time_features(player_matches, self.history, rankings, self.major_history)
        self.pairs = model.build_pairs(feats, predictors)
        self.tracked = sorted(player_matches["player_key"].unique())

    def at(self, as_of) -> tuple[pd.DataFrame, pd.DataFrame]:
        as_of = pd.Timestamp(as_of)
        train = self.pairs[pd.to_datetime(self.pairs["match_date"]) < as_of]
        scale = train[self.predictors].std()
        per_unit = model.fit_logit(train, self.predictors, scale).params[self.predictors] / scale[self.predictors]
        snap = features.features_as_of(self.player_matches, self.history, as_of, self.tracked, self.rankings,
                                       self.major_history).dropna(subset=self.predictors)
        player_preds = [c for c in self.predictors if c not in features.PAIR_ONLY]
        strengths = pd.DataFrame({"player_key": snap["player_key"],
                                  "strength": (snap[player_preds] * per_unit[player_preds]).sum(axis=1)})
        before = self.history[pd.to_datetime(self.history["match_date"]) < as_of].sort_values(["match_date", "match_key"])
        elo_now = before.groupby("player_key")["elo_post"].last().rename("elo").reset_index()
        return strengths, elo_now
