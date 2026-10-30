"""Point-in-time predictors for the Performance Index.

Every value describes a player *before* a given match, computed only from earlier matches, so the model
never sees the outcome it predicts. The same function produces "as of date X" values for the index itself
by scoring a virtual match on that date (see features_as_of).
"""

import numpy as np
import pandas as pd

from .rounds import order_key

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
    # Added 2026-10-31 (aimed at majors, decided before testing):
    "oom_rank": "PDC Order of Merit (log rank)",
    "major_elo": "Big-Stage Elo",
    "major_experience": "Big-Stage Experience (log matches)",
    "h2h": "Head-to-Head (shrunk)",
    "consistency": "Consistency (L30)",
    "activity": "Activity (matches in last 30 days)",
    "sharpness": "Match Sharpness (days since last match)",
    # Added 2026-10-31 (big-stage ability, majors only, decided before testing):
    "major_results_oe": "Big-Stage Results over Expectation (majors only)",
    "stage_delta": "Stage Delta (majors only)",
    "long_format_delta": "Long-Format Delta (majors only)",
}
# Pair-specific predictors: they describe a match-up, not a player, so they never enter a player's PI; they
# adjust the probability of that particular match (see analytics.model.PAIR_ONLY).
PAIR_ONLY = {"h2h"}

LONG_WINDOW, SHORT_WINDOW = 30, 10
MIN_LONG, MIN_SHORT = 10, 5
BIG_STAGE_WINDOW = "730D"
# Big-Stage Delta is shrunk toward 0 by n / (n + BIG_STAGE_SHRINK): with 10 major matches only half counts.
BIG_STAGE_SHRINK = 10.0
H2H_PRIOR = 2.0            # head-to-head share shrunk toward 50 %: (wins + 2) / (matches + 4)
UNRANKED = 500             # players outside the Order of Merit
# Stage events (played on a stage with a crowd) vs floor events, by event category.
STAGE_CATEGORIES = {"MJ", "WC", "WGP", "U", "ET", "WS", "WSD", "PCF"}
LONG_MATCH_LEGS = 15       # first to 8 legs or longer (sets count as 4 legs)

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

    # Consistency: minus the spread of match averages over the last 30 matches (higher = steadier).
    match_avg = 3 * prev["points"] / prev["darts"]
    out["consistency"] = -match_avg.rolling(LONG_WINDOW, min_periods=MIN_LONG).std()

    # Activity (matches in the 30 days before the match day) and sharpness (minus log days since the last match).
    dates = g["match_date"]
    ones = pd.Series(1.0, index=dates.to_numpy())
    out["activity"] = np.log1p(ones.rolling("30D", closed="left").sum().to_numpy())
    gap = (dates - dates.shift(1)).dt.days
    out["sharpness"] = -np.log1p(gap.to_numpy(dtype=float))

    # Head-to-head against this match's opponent, from earlier meetings only, shrunk toward 50 %.
    pair = g.groupby("opponent_key", sort=False)["won"]
    prior_wins = pair.transform(lambda s: s.astype(float).shift(1).fillna(0).cumsum())
    prior_n = pair.cumcount()
    out["h2h"] = (prior_wins + H2H_PRIOR) / (prior_n + 2 * H2H_PRIOR) - 0.5

    # Big-stage variants (24 months, strictly before the match date, shrunk by n / (n + 10)):
    def window_delta(mask: pd.Series, against: pd.Series | None = None) -> np.ndarray:
        """Average in matches where `mask` minus average where `against` (default: all matches)."""
        w = g[["match_date"]].copy()
        pts, drt = g["points"].astype(float).fillna(0.0), g["darts"].astype(float).fillna(0.0)
        base = against if against is not None else pd.Series(True, index=g.index)
        w["p1"], w["d1"] = pts.where(mask, 0.0), drt.where(mask, 0.0)
        w["p0"], w["d0"] = pts.where(base, 0.0), drt.where(base, 0.0)
        w["n"] = (mask & g["darts"].notna()).astype(float)
        r = w.set_index("match_date").rolling(BIG_STAGE_WINDOW, closed="left").sum()
        n = r["n"].to_numpy()
        d = (3 * r["p1"] / r["d1"].replace(0, np.nan) - 3 * r["p0"] / r["d0"].replace(0, np.nan)).to_numpy()
        return np.where(n > 0, np.nan_to_num(d) * n / (n + BIG_STAGE_SHRINK), 0.0)

    if "category" in g.columns:
        stage = g["category"].isin(STAGE_CATEGORIES)
        out["stage_delta"] = window_delta(stage, ~stage)
    else:
        out["stage_delta"] = np.nan
    if {"score_for", "score_against"} <= set(g.columns):
        legs = (g["score_for"] + g["score_against"]).astype(float) * np.where(g.get("unit", "legs") == "sets", 4, 1)
        out["long_format_delta"] = window_delta(legs >= LONG_MATCH_LEGS)
    else:
        out["long_format_delta"] = np.nan

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


def _as_of(rows: pd.DataFrame, history: pd.DataFrame, value: str, by: str = "player_key") -> pd.Series:
    """Latest `value` per player from `history` (player_key, date, value) strictly before each row's match_date."""
    left = rows[["match_date", by]].assign(_i=np.arange(len(rows)), match_date=lambda d: d["match_date"].astype("datetime64[ns]"),
                                           **{by: lambda d: d[by].astype("int64")}).sort_values("match_date")
    right = history.assign(date=lambda d: pd.to_datetime(d["date"]).astype("datetime64[ns]"),
                           **{by: lambda d: d[by].astype("int64")}).sort_values("date")
    merged = pd.merge_asof(left, right[["date", by, value]], left_on="match_date", right_on="date", by=by,
                           allow_exact_matches=False)
    return merged.sort_values("_i")[value].reset_index(drop=True)


def point_in_time_features(player_matches: pd.DataFrame, elo_history: pd.DataFrame,
                           rankings: pd.DataFrame | None = None, major_elo_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (match_key, player_key) with all candidate predictors as of just before the match.

    player_matches: silver.player_matches (tracked players' perspective).
    elo_history: output of analytics.elo.run_elo on all matches; major_elo_history: the same on majors only.
    rankings: Order of Merit snapshots (snapshot_date, player_key, rank).
    """
    pm = player_matches.assign(match_date=pd.to_datetime(player_matches["match_date"]))
    pm = pm.assign(_round_order=order_key(pm))
    pm = pm.sort_values(["player_key", "match_date", "_round_order", "match_key"]).reset_index(drop=True)
    feats = pd.concat([_player_features(g) for _, g in pm.groupby("player_key", sort=False)])
    keep = ["match_key", "player_key", "opponent_key", "match_date", "tournament_key", "is_major", "won"]
    keep += [c for c in ("category", "tournament_name") if c in pm.columns]  # descriptive, for the data summary
    out = pm[keep].join(feats)
    elo = elo_history[["match_key", "player_key", "elo_pre", "elo_n"]].rename(columns={"elo_pre": "elo"})
    out = out.merge(elo, on=["match_key", "player_key"], how="left")

    # Big-Stage Results over Expectation: on majors in the last 24 months, (wins - Elo-expected wins) / (n + 10).
    opp = elo_history[["match_key", "player_key", "elo_pre"]].rename(columns={"player_key": "opponent_key", "elo_pre": "opp_elo"})
    out = out.merge(opp, on=["match_key", "opponent_key"], how="left")
    expected = 1 / (1 + 10 ** ((out["opp_elo"] - out["elo"]) / 400))
    out["_res"] = np.where(out["is_major"].astype(bool), out["won"].astype(float) - expected, 0.0)
    out["_n"] = (out["is_major"].astype(bool) & expected.notna()).astype(float)
    out["_res"] = out["_res"].fillna(0.0)
    oe = []
    for _, g in out.sort_values(["player_key", "match_date"]).groupby("player_key", sort=False):
        r = g.set_index("match_date")[["_res", "_n"]].rolling(BIG_STAGE_WINDOW, closed="left").sum()
        oe.append(pd.Series((r["_res"] / (r["_n"] + BIG_STAGE_SHRINK)).to_numpy(), index=g.index))
    out["major_results_oe"] = pd.concat(oe).reindex(out.index).fillna(0.0) if oe else np.nan
    out = out.drop(columns=["_res", "_n", "opp_elo"])

    if rankings is not None and len(rankings):
        r = rankings.rename(columns={"snapshot_date": "date"})[["date", "player_key", "rank"]].dropna()
        out["oom_rank"] = -np.log(_as_of(out, r, "rank").fillna(UNRANKED).to_numpy())
    else:
        out["oom_rank"] = np.nan
    if major_elo_history is not None and len(major_elo_history):
        h = major_elo_history.assign(major_n=1).sort_values(["match_date", "match_key"])
        h["major_n"] = h.groupby("player_key").cumcount() + 1
        h = h.rename(columns={"match_date": "date", "elo_post": "major_elo"})
        out["major_elo"] = _as_of(out, h, "major_elo").fillna(elo_module_initial()).to_numpy()
        out["major_experience"] = np.log1p(_as_of(out, h, "major_n").fillna(0).to_numpy())
    else:
        out["major_elo"] = np.nan
        out["major_experience"] = np.nan
    return out


def elo_module_initial() -> float:
    from .elo import INITIAL_RATING
    return INITIAL_RATING


def features_as_of(player_matches: pd.DataFrame, elo_history: pd.DataFrame, as_of: pd.Timestamp,
                   player_keys: list[int], rankings: pd.DataFrame | None = None,
                   major_elo_history: pd.DataFrame | None = None) -> pd.DataFrame:
    """Predictors for each player as if they played a (virtual) match on `as_of`, using matches before it."""
    as_of = pd.Timestamp(as_of)
    player_keys = sorted(set(player_keys))  # one virtual match per player, or the windows shift
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

    feats = point_in_time_features(pd.concat([pm, virtual], ignore_index=True), virtual_elo, rankings, major_elo_history)
    out = feats[feats["match_key"] == -1].drop(columns=["match_key", "opponent_key", "tournament_key", "is_major", "won"])
    return out.assign(as_of_date=as_of.normalize()).reset_index(drop=True)
