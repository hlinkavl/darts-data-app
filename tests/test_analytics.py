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


def test_major_features_come_from_majors_only_and_never_see_the_same_day():
    pm = _player_matches(n=30)
    pm["is_major"] = pm.index % 3 == 0                                   # every third match is on a major
    pm.loc[~pm["is_major"], "points"] = 150.0                           # 50 average away from the majors
    pm.loc[pm.index[-1], ["points", "is_major"]] = [3000.0, True]       # absurd last major must not leak
    hist = elo.run_elo(pm.assign(winner_key=1, loser_key=99)[["match_key", "match_date", "winner_key", "loser_key", "is_major"]],
                       elo.EloParams())
    f = features.point_in_time_features(pm, hist).set_index("match_key")
    last = f.loc[pm["match_key"].iloc[-1]]
    assert np.isclose(last["avg_major"], 100.0)                         # majors only: 100, not the 50s
    assert np.isclose(last["form_major"], 0.0)
    assert np.isnan(f.loc[pm["match_key"].iloc[3], "avg_major"])        # fewer than 5 earlier major matches


def _major_rows(rows):
    """rows: (match_key, date, tournament_key, round, won) for player 1 against player 99."""
    return pd.DataFrame([{"match_key": k, "player_key": 1, "opponent_key": 99, "match_date": pd.Timestamp(d),
                          "tournament_key": t, "is_major": True, "won": w, "round": r, "points": 300.0, "darts": 9.0,
                          "first9_points": np.nan, "first9_darts": np.nan, "checkouts_hit": np.nan,
                          "checkout_attempts": np.nan, "one_eighties": np.nan} for k, d, t, r, w in rows])


def test_results_on_majors_count_deep_runs_in_the_window_and_skip_the_league():
    pm = _major_rows([
        (1, "2025-07-20", 29, "Quarter-finals", True), (2, "2025-07-21", 29, "Semi-finals", True),
        (3, "2025-07-22", 29, "Final", True),                                    # Matchplay 2025: title
        (4, "2025-10-01", 36, "Quarter-finals", False),                          # Grand Prix: out in the QF
        (5, "2025-11-01", 1070, "Final", True),                                  # Premier League night: ignored
        (6, "2025-11-20", 40, "Last 16", False),                                 # next event, before its own end
    ])
    hist = elo.run_elo(pm.assign(winner_key=1, loser_key=99)[["match_key", "match_date", "winner_key", "loser_key", "is_major"]],
                       elo.EloParams())
    f = features.point_in_time_features(pm, hist).set_index("match_key").loc[6]
    assert f["major_qf_12m"] == 2 and f["major_points_12m"] == 4 + 1 and f["major_titles_24m"] == 1


def test_time_in_top32_is_a_share_of_the_months_with_history():
    months = pd.date_range("2024-01-01", periods=24, freq="MS")
    rankings = pd.DataFrame({"snapshot_date": months, "player_key": 1, "rank": [10] * 12 + [40] * 12})
    rows = pd.DataFrame({"match_date": [pd.Timestamp("2026-01-15")], "player_key": [1]})
    q = features._ranking_quality(rows, rankings).iloc[0]
    assert np.isclose(q["top32_share_5y"], 0.5)                    # 12 of 24 months with history
    assert np.isclose(q["oom_best_3y"], -np.log(10))
    mid = features._ranking_quality(pd.DataFrame({"match_date": [pd.Timestamp("2025-07-15")], "player_key": [1]}), rankings)
    assert np.isclose(mid["oom_momentum"].iloc[0], -np.log(40) + np.log(10))  # #10 a year ago, #40 now
