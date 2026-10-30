import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analytics import elo, features, model  # noqa: E402


def _matches(rows):
    return pd.DataFrame(rows, columns=["match_key", "match_date", "winner_key", "loser_key", "is_major"]).assign(
        match_date=lambda d: pd.to_datetime(d["match_date"]))


def test_elo_rewards_wins_over_stronger_opponents():
    # Player 1 becomes strong by beating 9 twice; then 2 beats strong 1 and 3 beats weak 9.
    history = elo.run_elo(_matches([
        (1, "2025-01-01", 1, 9, False), (2, "2025-01-02", 1, 9, False),
        (3, "2025-01-03", 2, 1, False), (4, "2025-01-03", 3, 9, False),
    ]), elo.EloParams(k=32))
    gain = (history["elo_post"] - history["elo_pre"]).groupby([history["match_key"], history["player_key"]]).first()
    assert gain[(3, 2)] > gain[(4, 3)] > 0


def test_elo_major_multiplier():
    params = elo.EloParams(k=20, major_multiplier=1.5)
    floor = elo.run_elo(_matches([(1, "2025-01-01", 1, 2, False)]), params)
    major = elo.run_elo(_matches([(1, "2025-01-01", 1, 2, True)]), params)
    assert np.isclose((major.elo_post - major.elo_pre).iloc[0], 1.5 * (floor.elo_post - floor.elo_pre).iloc[0])


def _player_matches(n=40, player=1, start="2025-01-01"):
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({
        "match_key": np.arange(n) + 1000 * player, "player_key": player, "opponent_key": 99, "match_date": dates,
        "tournament_key": 0, "is_major": False, "won": True,
        "points": 300.0, "darts": 9.0, "first9_points": 300.0, "first9_darts": 9.0,  # 100 average every match
        "checkouts_hit": 1.0, "checkout_attempts": 2.0, "one_eighties": 1.0,
    })


def test_features_use_only_earlier_matches():
    pm = _player_matches()
    pm.loc[pm.index[-1], "points"] = 3000.0  # absurd last match must not leak into its own features
    hist = pd.DataFrame({"match_key": pm.match_key, "player_key": 1, "elo_pre": 1500.0, "elo_n": range(len(pm))})
    f = features.point_in_time_features(pm, hist).sort_values("match_date")
    assert np.isclose(f["avg_l30"].iloc[-1], 100.0)
    assert np.isnan(f["avg_l30"].iloc[5])  # fewer than 10 earlier matches
    assert np.isclose(f["form"].iloc[-1], 0.0)


def test_reference_top32_player_scores_pi_5():
    snap = pd.DataFrame({"player_key": range(32), "avg_l30": np.full(32, 95.0), "form": 0.0, "elo": 1600.0})
    coefs = pd.DataFrame({"predictor": ["avg_l30", "form", "elo"], "beta_per_unit": [0.12, 0.06, 0.0015]})
    scored = model.score_players(snap, coefs)
    assert np.allclose(scored["pi"], 5.0)
    assert np.allclose(scored["effective_average"], 95.0)


def test_win_probability_is_symmetric():
    assert np.isclose(model.win_probability(1.2, 0.4) + model.win_probability(0.4, 1.2), 1.0)


def test_no_leak_from_later_rounds_on_the_same_day():
    # One-day event numbered backwards like Orakel's Players Championships: the final has the lowest id.
    day = pd.Timestamp("2025-08-25")
    rounds = [("Last 128", 300), ("Last 64", 200), ("Final", 100)]
    pm = pd.DataFrame({
        "match_key": [k for _, k in rounds], "player_key": 1, "opponent_key": [7, 8, 9], "match_date": day,
        "round": [r for r, _ in rounds], "tournament_key": 0, "is_major": False, "won": True,
        "points": 300.0, "darts": 9.0, "first9_points": 300.0, "first9_darts": 9.0,
        "checkouts_hit": 1.0, "checkout_attempts": 2.0, "one_eighties": 1.0,
    })
    matches = pd.DataFrame({"match_key": [k for _, k in rounds], "match_date": day, "round": [r for r, _ in rounds],
                            "winner_key": 1, "loser_key": [7, 8, 9], "is_major": False})
    hist = elo.run_elo(matches, elo.EloParams(k=32))
    f = features.point_in_time_features(pm, hist).set_index("match_key")
    assert f.loc[300, "experience"] == 0.0          # first round: no earlier match that day
    assert f.loc[100, "experience"] > f.loc[200, "experience"] > 0
    assert f.loc[300, "elo"] == elo.INITIAL_RATING  # Elo before the first round is untouched by later rounds
