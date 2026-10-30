"""Opponent-Weighted Elo: a rating built from results only, where beating a strong opponent earns more points.

    expected_A = 1 / (1 + 10 ** ((R_B - R_A) / 400))
    R_A_new    = R_A + K * m * (result_A - expected_A)        m = major_multiplier on majors, else 1

A win over a much stronger player (expected_A close to 0) earns almost the full K; a win over a much weaker
player (expected_A close to 1) earns almost nothing. Losses work the same way in reverse.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .rounds import order_key

INITIAL_RATING = 1500.0


@dataclass(frozen=True)
class EloParams:
    k: float = 24.0
    major_multiplier: float = 1.0


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def run_elo(matches: pd.DataFrame, params: EloParams) -> pd.DataFrame:
    """Replay every match in chronological order.

    matches: one row per match with match_key, match_date, winner_key, loser_key, is_major (and round, used to
    order matches within a day; ids alone are not chronological).
    Returns one row per (match_key, player_key) with the rating *before* and *after* the match and the
    number of matches the player had played before it (elo_n, used for burn-in).
    """
    ordered = matches.assign(_round_order=order_key(matches)).sort_values(["match_date", "_round_order", "match_key"])
    ratings: dict[int, float] = {}
    played: dict[int, int] = {}
    rows = []
    for m in ordered.itertuples(index=False):
        w, l = m.winner_key, m.loser_key
        rw, rl = ratings.get(w, INITIAL_RATING), ratings.get(l, INITIAL_RATING)
        k = params.k * (params.major_multiplier if m.is_major else 1.0)
        delta = k * (1.0 - expected_score(rw, rl))
        rows.append((m.match_key, w, m.match_date, rw, rw + delta, played.get(w, 0)))
        rows.append((m.match_key, l, m.match_date, rl, rl - delta, played.get(l, 0)))
        ratings[w], ratings[l] = rw + delta, rl - delta
        played[w], played[l] = played.get(w, 0) + 1, played.get(l, 0) + 1
    return pd.DataFrame(rows, columns=["match_key", "player_key", "match_date", "elo_pre", "elo_post", "elo_n"])


def elo_log_loss(history: pd.DataFrame, matches: pd.DataFrame, min_matches: int, before: pd.Timestamp) -> float:
    """Log loss of Elo's own win expectation, for tuning K. Only matches before `before` where both players
    have at least `min_matches` prior matches (burn-in)."""
    pre = history.set_index(["match_key", "player_key"])[["elo_pre", "elo_n"]]
    m = matches[matches.match_date < before]
    w = pre.reindex(pd.MultiIndex.from_arrays([m.match_key, m.winner_key])).to_numpy()
    l = pre.reindex(pd.MultiIndex.from_arrays([m.match_key, m.loser_key])).to_numpy()
    ok = (w[:, 1] >= min_matches) & (l[:, 1] >= min_matches)
    p_winner = 1.0 / (1.0 + 10.0 ** ((l[ok, 0] - w[ok, 0]) / 400.0))
    return float(-np.mean(np.log(np.clip(p_winner, 1e-9, 1.0))))


def tune(matches: pd.DataFrame, grid: list[EloParams], min_matches: int, before: pd.Timestamp) -> tuple[EloParams, pd.DataFrame]:
    """Pick the parameters with the lowest log loss on the training period."""
    results = [(p, elo_log_loss(run_elo(matches, p), matches, min_matches, before)) for p in grid]
    table = pd.DataFrame([{"k": p.k, "major_multiplier": p.major_multiplier, "log_loss": ll} for p, ll in results])
    best = min(results, key=lambda r: r[1])[0]
    return best, table
