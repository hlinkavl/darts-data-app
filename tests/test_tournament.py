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
    assert sf.matches[1].walkover and sf.matches[1].winner == "Player C"
    assert final.matches[0].winner is None


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
