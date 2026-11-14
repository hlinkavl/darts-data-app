"""Results of the majors from Wikipedia draws (since 14 Nov 2026 the only source of new results).

Every knockout match in a parsed draw becomes one row: players, score, 3-dart averages (Wikipedia shows them in the
bracket) and the round's date from the round header. Matches without a result yet are kept as well: with both
players known they are the upcoming matches. Group stages and leagues have no bracket and are not covered.
"""

from datetime import date, timedelta

import pandas as pd

from . import bracket, calendar

COLUMNS = ["wiki_title", "tournament_key", "tournament_name", "edition", "event_start", "event_end", "round",
           "round_order", "first_to", "unit", "match_date", "player_a", "player_b", "score_a", "score_b", "avg_a",
           "avg_b", "played", "is_final"]


def draw_results(pages: pd.DataFrame, majors: dict, after: date | None = None) -> pd.DataFrame:
    """pages: title, wikitext. Only events that start after `after` (earlier ones come from the historical
    sources). A round without a date in its header gets the event's start date plus its round number, capped at
    the end date."""
    rows = []
    for page in pages.itertuples():
        found = calendar.match_major(page.title, majors)
        if not found or not isinstance(page.wikitext, str):
            continue
        key, edition = found
        start, end = calendar.infobox_dates(page.wikitext)
        if not start or (after and start <= after):
            continue
        draw = bracket.build_draw(page.title, page.wikitext)
        if not draw:
            continue
        for r, rnd in enumerate(draw.rounds):
            day = rnd.date_in(start, end) or min(start + timedelta(days=r), end or start + timedelta(days=r))
            for m in rnd.matches:
                if not m.player_a or not m.player_b:
                    continue
                played = (m.score_a is not None and m.score_b is not None and m.score_a != m.score_b
                          and not m.walkover)
                rows.append({"wiki_title": page.title, "tournament_key": key, "tournament_name": majors[key]["name"],
                             "edition": edition, "event_start": start, "event_end": end, "round": rnd.name,
                             "round_order": r + 1, "first_to": rnd.first_to, "unit": rnd.unit or "legs",
                             "match_date": day, "player_a": m.player_a, "player_b": m.player_b,
                             "score_a": m.score_a, "score_b": m.score_b, "avg_a": m.avg_a, "avg_b": m.avg_b,
                             "played": played, "is_final": r == len(draw.rounds) - 1})
    return pd.DataFrame(rows, columns=COLUMNS)
