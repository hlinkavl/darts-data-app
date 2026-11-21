import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analytics import bracket, formats, tournament  # noqa: E402

WIKITEXT = """
==Draw==
{{#invoke:bracket|4TeamBracket
| RD1='''Semi-finals''' ''(best of 11 legs)''
| RD2='''Final''' ''(best of 3 sets)''
| RD1-seed1 = 1
| RD1-team1 = {{PDCFlag|Player A|avg=101.20}}
| RD1-score1 = 6
| RD1-seed2 = &nbsp;
| RD1-team2 = {{PDCFlag|Player B|avg=95.00}}
| RD1-score2 = 2
| RD1-team3 = {{#invoke:DartsRankings|PDCFlag|Player C|avg=|b=1}}
| RD1-score3 = {{nowrap|'''[[Walkover|w/o]]'''}}
| RD1-team4 = {{PDCFlag|Player D|avg=}}
| RD1-score4 =
| RD2-team1 = {{PDCFlag|Player A|avg=}}
| RD2-team2 = {{PDCFlag|Player C|avg=}}
}}
"""


def _draw():
    blocks = bracket.parse_blocks(WIKITEXT)
    return bracket.Draw("test", blocks[0]["rounds"])


def test_parse_formats_scores_and_walkover():
    draw = _draw()
    sf, final = draw.rounds
    assert (sf.first_to, sf.unit, final.first_to, final.unit) == (6, "legs", 2, "sets")
    assert sf.matches[0].winner == "Player A" and sf.matches[0].avg_a == 101.2
    assert sf.matches[0].seed_a == "1" and sf.matches[0].seed_b is None  # &nbsp; is an empty seed
    assert sf.matches[1].walkover and sf.matches[1].winner == "Player C"
    assert final.matches[0].winner is None


def test_team_cell_named_parameters_are_never_the_name():
    assert bracket.parse_team("{{PDCFlag|flag=NED}}") == (None, None)
    assert bracket.parse_team("{{PDCFlag|flag=ENG|avg=}}") == (None, None)
    assert bracket.parse_team("{{PDCFlag||avg=}}") == (None, None)
    assert bracket.parse_team("{{PDCFlag|Gerwyn Price|txt=(4)|avg=101.5}}") == ("Gerwyn Price", 101.5)
    assert bracket.parse_team("{{#invoke:DartsRankings|PDCFlag|Player C|avg=|b=1}}") == ("Player C", None)


def _section(n: int) -> str:
    """An 8-player section whose last round (the semi-final) repeats the first round of the finals."""
    lines = [f"===Section {n}===", "{{8TeamBracket", "| RD1='''First round''' ''(best of 11 legs)''<br>27 November",
             "| RD2='''Second round''' ''(best of 11 legs)''<br>28 November",
             "| RD3='''Semi-finals''' ''(best of 21 legs)''<br>29 November"]
    players = [f"S{n}P{i}" for i in range(1, 9)]
    for i, p in enumerate(players, 1):
        lines += [f"| RD1-team{i} = {{{{PDCFlag|{p}|avg=90.00}}}}", f"| RD1-score{i} = {6 if i % 2 else 2}"]
    for i, p in enumerate(players[::2], 1):
        lines += [f"| RD2-team{i} = {{{{PDCFlag|{p}|avg=}}}}"]
    lines += [f"| RD3-team1 = {{{{PDCFlag|{players[0]}|avg=}}}}"]
    return "\n".join(lines + ["}}"])


def test_sections_repeating_the_finals_first_round_are_merged():
    finals = "\n".join(["===Finals===", "{{4TeamBracket", "| RD1='''Semi-finals''' ''(best of 21 legs)''<br>29 November",
                        "| RD2='''Final''' ''(best of 21 legs)''<br>29 November"] + [
        f"| RD1-team{i} = {{{{PDCFlag|{p}|avg=}}}}" for i, p in enumerate(["S1P1", "S1P5", "S2P1", "S2P5"], 1)] + [
        "| RD2-team1 = {{PDCFlag||avg=}}", "| RD2-team2 = {{PDCFlag||avg=}}", "}}"])  # unplayed, as on the pages
    draw = bracket.build_draw("Players Championship Finals", "\n".join(["==Draw==", finals, _section(1), _section(2)]))
    assert [r.name for r in draw.rounds] == ["First round", "Second round", "Semi-finals", "Final"]
    assert [len(r.matches) for r in draw.rounds] == [8, 4, 2, 1]
    assert len(draw.players) == 16 and draw.rounds[2].matches[1].player_a == "S2P1"


def test_format_conversion_keeps_typical_and_rewards_favourite_in_longer_matches():
    assert np.isclose(formats.match_probability(0.7, formats.TYPICAL_FIRST_TO), 0.7, atol=1e-6)
    assert formats.match_probability(0.7, 3) < 0.7 < formats.match_probability(0.7, 10)
    assert np.isclose(formats.match_probability(0.5, 7, "sets"), 0.5)


def test_live_simulation_respects_played_matches():
    draw = _draw()
    slots = pd.DataFrame({"slot": range(4), "player_name": draw.players, "strength": [0.0, 3.0, 0.0, 0.0]})
    sim = tournament.simulate(draw, slots, fix_played=True, n_sims=2000)
    final = sim[sim.round_name == "Final"].set_index("player_name")["p_reach"]
    # B is much stronger but lost the played semi-final; C advanced on a walkover.
    assert final["Player A"] == 1.0 and final["Player B"] == 0.0 and final["Player C"] == 1.0
    pre = tournament.simulate(draw, slots, fix_played=False, n_sims=2000)
    assert pre[pre.round_name == "Final"].set_index("player_name")["p_reach"]["Player B"] > 0.9


def test_backtests_of_the_same_model_are_reused():
    """A finished major is simulated once per model version; later refreshes reuse it."""
    from datetime import date

    from analytics import overview

    text = WIKITEXT.replace("| RD2-team1 = {{PDCFlag|Player A|avg=}}", "| RD2-team1 = {{PDCFlag|Player A|avg=}}\n| RD2-score1 = 2") \
                   .replace("| RD2-team2 = {{PDCFlag|Player C|avg=}}", "| RD2-team2 = {{PDCFlag|Player C|avg=}}\n| RD2-score2 = 0")
    draw = bracket.Draw("test", bracket.parse_blocks(text)[0]["rounds"])
    assert draw.rounds[-1].matches[0].winner == "Player A"
    cal = pd.DataFrame([{"has_draw": True, "wiki_title": "Test", "tournament_key": 1, "tournament_name": "Test",
                         "edition": 2026, "start_date": pd.Timestamp("2026-01-01")}])
    players = pd.DataFrame({"player_key": [1, 2, 3, 4], "player_name": ["Player A", "Player B", "Player C", "Player D"]})
    strengths = pd.DataFrame({"player_key": [1, 2, 3, 4], "strength": [0.5, 0.2, 0.0, -0.3]})
    elo_now = pd.DataFrame({"player_key": [1, 2, 3, 4], "elo": [1600, 1550, 1500, 1450]})

    class History:
        def at(self, _):
            return strengths, elo_now

    first = overview.draw_outputs(cal, {"Test": draw}, players, strengths, elo_now, History, date(2026, 11, 1))

    def must_not_run():
        raise AssertionError("a reused backtest must not rebuild the strength history")

    again = overview.draw_outputs(cal, {"Test": draw}, players, strengths, elo_now, must_not_run, date(2026, 11, 2),
                                  previous=first)
    for table in overview.BACKTEST_TABLES:
        pd.testing.assert_frame_equal(first[table].reset_index(drop=True), again[table].reset_index(drop=True))


def test_snapshot_types_match_the_warehouse():
    from datetime import date
    from decimal import Decimal

    from analytics import snapshot
    raw = pd.DataFrame({"at": pd.to_datetime(["2026-11-20 10:00"]).tz_localize("Europe/Prague"),
                        "pi": [Decimal("7.25")], "day": [date(2026, 11, 20)], "name": ["Littler"]})
    raw.attrs["metrics"] = object()  # Spark Connect's plan metrics: not JSON serialisable
    df = snapshot.normalize(raw)
    assert not df.attrs
    assert str(df["at"].dtype).startswith("datetime64[") and df["at"].iloc[0].hour == 9
    assert df["pi"].dtype == float and str(df["day"].dtype).startswith("datetime64") and df["name"].iloc[0] == "Littler"
