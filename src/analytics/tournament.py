"""Tournament predictions: Monte Carlo simulation of a knockout draw and a match-level backtest.

Strength S comes from the PI model (log-odds scale). For a match in round r:
    P(A beats B) = format_r( 1 / (1 + e^-(S_A - S_B)) )
where format_r converts the typical-match probability to the round's format (analytics.formats).
"""

import numpy as np
import pandas as pd

from .bracket import Draw, normalize_name
from .formats import TYPICAL_FIRST_TO, match_probability

N_SIMS = 10_000
SEED = 42
FALLBACK_QUANTILE = 0.05  # strength for players with no data at all: 5th percentile of tracked players
EMPTY_SLOT = -50.0        # a bye: the opponent always goes through

_GRID = np.linspace(0.0005, 0.9995, 1999)


def _format_table(first_to: int | None, unit: str | None) -> np.ndarray:
    """P(win) in the round's format on a grid of typical-match probabilities, for fast interpolation."""
    if not first_to or not unit:
        return _GRID.copy()
    return np.array([match_probability(p, first_to, unit) for p in _GRID])


def _round_probability(table: np.ndarray, strength_diff: np.ndarray) -> np.ndarray:
    return np.interp(1.0 / (1.0 + np.exp(-strength_diff)), _GRID, table)


# ------------------------------------------------------------------------------------------ strengths

def draw_strengths(draw: Draw, players: pd.DataFrame, strengths: pd.DataFrame, elo_now: pd.DataFrame) -> pd.DataFrame:
    """Strength for every first-round slot.

    players: player_key, player_name (all known players). strengths: player_key, strength (PI model, tracked
    players). elo_now: player_key, elo (latest Elo, any player who met a tracked player).
    Untracked players get a strength predicted from their Elo (linear fit on tracked players); players with
    no Elo get the 5th percentile of tracked strength.
    """
    by_name = {normalize_name(n): k for k, n in zip(players["player_key"], players["player_name"])}
    tracked = strengths.merge(elo_now, on="player_key", how="left").dropna()
    slope, intercept = np.polyfit(tracked["elo"], tracked["strength"], 1)
    fallback = strengths["strength"].quantile(FALLBACK_QUANTILE)
    s_map = dict(zip(strengths["player_key"], strengths["strength"]))
    e_map = dict(zip(elo_now["player_key"], elo_now["elo"]))

    rows = []
    for slot, name in enumerate(draw.players):
        key = by_name.get(normalize_name(name)) if name else None
        if name is None:
            strength, source = EMPTY_SLOT, "bye"
        elif key in s_map:
            strength, source = s_map[key], "pi_model"
        elif key in e_map:
            strength, source = intercept + slope * e_map[key], "elo_estimate"
        else:
            strength, source = fallback, "fallback"
        rows.append({"slot": slot, "player_name": name, "player_key": key, "strength": strength, "source": source})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------- simulation

def simulate(draw: Draw, slot_strengths: pd.DataFrame, fix_played: bool, n_sims: int = N_SIMS,
             seed: int = SEED) -> pd.DataFrame:
    """Monte Carlo of the whole draw. With fix_played, matches that already have a winner are not simulated
    (live bracket). Returns per player the probability to reach each round and to win the event."""
    rng = np.random.default_rng(seed)
    names = list(draw.players)
    strength = slot_strengths.sort_values("slot")["strength"].to_numpy()
    n = len(names)
    current = np.tile(np.arange(n), (n_sims, 1))
    reach = {0: np.ones(n)}
    index = {name: i for i, name in enumerate(names) if name}

    for r, rnd in enumerate(draw.rounds):
        table = _format_table(rnd.first_to, rnd.unit)
        a, b = current[:, 0::2], current[:, 1::2]
        p_a = _round_probability(table, strength[a] - strength[b])
        a_wins = rng.random(p_a.shape) < p_a
        if fix_played:
            for m in rnd.matches:
                if m.winner in index:
                    a_wins[:, m.slot] = (a[:, m.slot] == index[m.winner])
        current = np.where(a_wins, a, b)
        reach[r + 1] = np.bincount(current.ravel(), minlength=n) / n_sims

    rows = []
    for i, name in enumerate(names):
        if name is None:
            continue
        for r, rnd in enumerate(draw.rounds):
            rows.append({"slot": i, "player_name": name, "round_order": r + 1, "round_name": rnd.name,
                         "p_reach": reach[r][i]})
        rows.append({"slot": i, "player_name": name, "round_order": len(draw.rounds) + 1, "round_name": "Winner",
                     "p_reach": reach[len(draw.rounds)][i]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------- backtest

def backtest_matches(draw: Draw, slot_strengths: pd.DataFrame) -> pd.DataFrame:
    """Pre-tournament probability for every match that was actually played (walkovers excluded),
    in the round's format and, for comparison, as a typical match."""
    s = dict(zip(slot_strengths["player_name"], slot_strengths["strength"]))
    rows = []
    for rnd in draw.rounds:
        for m in rnd.matches:
            if m.winner is None or m.walkover or m.player_a not in s or m.player_b not in s:
                continue
            p_typical = 1.0 / (1.0 + np.exp(-(s[m.player_a] - s[m.player_b])))
            p_format = match_probability(p_typical, rnd.first_to or TYPICAL_FIRST_TO, rnd.unit or "legs")
            rows.append({"round_name": rnd.name, "player_a": m.player_a, "player_b": m.player_b,
                         "score": f"{m.score_a}-{m.score_b}", "winner": m.winner,
                         "a_won": int(m.winner == m.player_a), "p_a_typical": p_typical, "p_a": p_format})
    return pd.DataFrame(rows)


def backtest_summary(matches: pd.DataFrame, simulation: pd.DataFrame, draw: Draw) -> pd.DataFrame:
    """Match-level accuracy, log loss and Brier (format vs. typical), and how the champion was rated."""
    y = matches["a_won"].to_numpy()
    out = []
    for label, col in [("model, round format", "p_a"), ("model, typical match", "p_a_typical")]:
        p = np.clip(matches[col].to_numpy(), 1e-6, 1 - 1e-6)
        out.append({"metric_set": label, "matches": len(y),
                    "favourite_won_pct": 100 * np.mean((p > 0.5) == (y == 1)),
                    "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
                    "brier": float(np.mean((p - y) ** 2))})
    summary = pd.DataFrame(out)

    champion = draw.rounds[-1].matches[0].winner
    winners = simulation[simulation["round_name"] == "Winner"].sort_values("p_reach", ascending=False).reset_index(drop=True)
    row = winners[winners["player_name"] == champion]
    summary["champion"] = champion
    summary["champion_p_title"] = float(row["p_reach"].iloc[0]) if len(row) else np.nan
    summary["champion_rank_by_p_title"] = int(row.index[0]) + 1 if len(row) else None
    summary["favourite"] = winners["player_name"].iloc[0]
    summary["favourite_p_title"] = float(winners["p_reach"].iloc[0])
    return summary
