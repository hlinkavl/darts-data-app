"""Point-in-time predictors for the Performance Index.

Every value describes a player *before* a given match, computed only from earlier matches, so the model
never sees the outcome it predicts. The same function produces "as of date X" values for the index itself
by scoring a virtual match on that date (see features_as_of).
"""

import numpy as np
import pandas as pd

# Candidate predictors (step 1 of the methodology). Higher is better for all of them.
# Big-Stage Delta only enters matches played on a major (see analytics.model.MAJOR_ONLY).
CANDIDATES = {
    "avg_l30": "3-Dart Average (L30)",
    "first9_l30": "First-9 Average (L30)",
    "form": "Form (L10 vs L30)",
    "big_stage_delta": "Big-Stage Delta (majors only)",
    "elo": "Opponent-Weighted Elo",
    "checkout_l30": "Checkout % (L30)",
    "t180_per100": "180s per 100 Darts (L30)",
    "winrate_l30": "Win Rate (L30)",
    "experience": "Experience (log matches)",
}

LONG_WINDOW, SHORT_WINDOW = 30, 10
MIN_LONG, MIN_SHORT = 10, 5
BIG_STAGE_WINDOW = "730D"
# Big-Stage Delta is shrunk toward 0 by n / (n + BIG_STAGE_SHRINK): with 10 major matches only half counts.
BIG_STAGE_SHRINK = 10.0

STAT_COLUMNS = ["points", "darts", "first9_points", "first9_darts", "checkouts_hit", "checkout_attempts", "one_eighties"]


def _player_features(g: pd.DataFrame) -> pd.DataFrame:
    """Features for one player's matches (sorted chronologically), each from strictly earlier matches."""
    prev = g[STAT_COLUMNS + ["won"]].astype(float).shift(1)

    def window_sum(col: str, n: int, min_periods: int) -> pd.Series:
        return prev[col].rolling(n, min_periods=min_periods).sum()

    darts_l30 = window_sum("darts", LONG_WINDOW, MIN_LONG)
    out = pd.DataFrame(index=g.index)
    out["avg_l30"] = 3 * window_sum("points", LONG_WINDOW, MIN_LONG) / darts_l30
    avg_l10 = 3 * window_sum("points", SHORT_WINDOW, MIN_SHORT) / window_sum("darts", SHORT_WINDOW, MIN_SHORT)
    out["form"] = avg_l10 - out["avg_l30"]
    out["first9_l30"] = 3 * window_sum("first9_points", LONG_WINDOW, MIN_LONG) / window_sum("first9_darts", LONG_WINDOW, MIN_LONG)
    out["checkout_l30"] = 100 * window_sum("checkouts_hit", LONG_WINDOW, MIN_LONG) / window_sum("checkout_attempts", LONG_WINDOW, MIN_LONG)
    out["t180_per100"] = 100 * window_sum("one_eighties", LONG_WINDOW, MIN_LONG) / darts_l30
    out["winrate_l30"] = prev["won"].rolling(LONG_WINDOW, min_periods=MIN_LONG).mean()
    out["experience"] = np.log1p(np.arange(len(g)))

    # Big-Stage Delta: average on majors minus overall average, last 24 months (strictly before the match date).
    t = g[["match_date", "points", "darts"]].astype({"points": float, "darts": float}).copy()
    has_stats = t["darts"].notna()
    t["maj_points"] = t["points"].where(g["is_major"].astype(bool), 0.0)
    t["maj_darts"] = t["darts"].where(g["is_major"].astype(bool), 0.0)
    t["maj_n"] = (g["is_major"].astype(bool) & has_stats).astype(float)
    t = t.fillna(0.0).set_index("match_date")
    rolled = t.rolling(BIG_STAGE_WINDOW, closed="left").sum()
    overall = 3 * rolled["points"] / rolled["darts"].replace(0, np.nan)
    major = 3 * rolled["maj_points"] / rolled["maj_darts"].replace(0, np.nan)
    n_major = rolled["maj_n"].to_numpy()
    delta = ((major - overall).to_numpy() * n_major / (n_major + BIG_STAGE_SHRINK))
    out["big_stage_delta"] = np.where(n_major > 0, delta, 0.0)
    out["n_major_24m"] = n_major
    return out


def point_in_time_features(player_matches: pd.DataFrame, elo_history: pd.DataFrame) -> pd.DataFrame:
    """One row per (match_key, player_key) with all candidate predictors as of just before the match.

    player_matches: silver.player_matches (tracked players' perspective).
    elo_history: output of analytics.elo.run_elo.
    """
    pm = player_matches.assign(match_date=pd.to_datetime(player_matches["match_date"]))
    pm = pm.sort_values(["player_key", "match_date", "match_key"]).reset_index(drop=True)
    feats = pd.concat([_player_features(g) for _, g in pm.groupby("player_key", sort=False)])
    out = pm[["match_key", "player_key", "opponent_key", "match_date", "tournament_key", "is_major", "won"]].join(feats)
    elo = elo_history[["match_key", "player_key", "elo_pre", "elo_n"]].rename(columns={"elo_pre": "elo"})
    return out.merge(elo, on=["match_key", "player_key"], how="left")


def features_as_of(player_matches: pd.DataFrame, elo_history: pd.DataFrame, as_of: pd.Timestamp,
                   player_keys: list[int]) -> pd.DataFrame:
    """Predictors for each player as if they played a (virtual) match on `as_of`, using matches before it."""
    as_of = pd.Timestamp(as_of)
    pm = player_matches[pd.to_datetime(player_matches["match_date"]) < as_of]
    virtual = pd.DataFrame({
        "match_key": -1, "player_key": player_keys, "opponent_key": -1, "match_date": as_of,
        "tournament_key": -1, "is_major": False, "won": np.nan,
    })
    for col in STAT_COLUMNS:
        virtual[col] = np.nan

    hist = elo_history[pd.to_datetime(elo_history["match_date"]) < as_of].sort_values(["match_date", "match_key"])
    last = hist.groupby("player_key").agg(elo_pre=("elo_post", "last"), elo_n=("elo_post", "size")).reset_index()
    virtual_elo = virtual[["match_key", "player_key"]].merge(last, on="player_key", how="left")

    feats = point_in_time_features(pd.concat([pm, virtual], ignore_index=True), virtual_elo)
    out = feats[feats["match_key"] == -1].drop(columns=["match_key", "opponent_key", "tournament_key", "is_major", "won"])
    return out.assign(as_of_date=as_of.normalize()).reset_index(drop=True)
