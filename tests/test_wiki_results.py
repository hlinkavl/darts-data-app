import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analytics import wiki_results  # noqa: E402

MAJORS = {29: {"name": "World Matchplay", "wiki": "{year} World Matchplay"}}


def _page(scores_first_round: bool = True) -> str:
    """A 16-player knockout like the Matchplay page: round headers with formats and dates, averages in the cells."""
    heads = ["First round (best of 19 legs)<br>18–20 July", "Second round (best of 21 legs)<br>21–22 July",
             "Quarter-finals (best of 31 legs)<br>23–24 July", "Semi-finals (best of 33 legs)<br>25 July",
             "Final (best of 35 legs)<br>26 July"]
    lines = ["{{Infobox individual darts tournament", "| dates = 18–26 July 2026", "}}", "==Draw==",
             "{{#invoke:Bracket|16TeamBracket"]
    lines += [f"| RD{r + 1}='''{h}'''" for r, h in enumerate(heads)]
    for i in range(1, 17):
        lines.append(f"| RD1-team{i:02d} = {{{{PDCFlag|Player {i}|avg={90 + i}.50}}}}")
        if scores_first_round:
            lines.append(f"| RD1-score{i:02d} = {10 if i % 2 else 4}")
    for i in range(1, 9):  # second round drawn, nothing played yet
        lines.append(f"| RD2-team{i:02d} = {{{{PDCFlag|Player {2 * i - 1}|avg=}}}}")
    return "\n".join(lines + ["}}"])


def test_results_dates_and_open_matches():
    pages = pd.DataFrame([{"title": "2026 World Matchplay", "wikitext": _page()}])
    wk = wiki_results.draw_results(pages, MAJORS)
    first = wk[wk["round_order"] == 1]
    assert len(first) == 8 and first["played"].all()
    assert (first["match_date"] == date(2026, 7, 20)).all()          # the round's last day
    m = first.iloc[0]
    assert (m.player_a, m.player_b, m.score_a, m.score_b, m.avg_a) == ("Player 1", "Player 2", 10, 4, 91.5)
    open_ = wk[~wk["played"]]
    assert len(open_) == 4 and set(open_["round"]) == {"Second round"}  # both players known, no score yet
    assert (open_["match_date"] == date(2026, 7, 22)).all()


def test_events_covered_by_the_history_are_skipped():
    pages = pd.DataFrame([{"title": "2026 World Matchplay", "wikitext": _page()}])
    assert wiki_results.draw_results(pages, MAJORS, after=date(2026, 7, 31)).empty
    assert len(wiki_results.draw_results(pages, MAJORS, after=date(2026, 7, 1))) == 12
