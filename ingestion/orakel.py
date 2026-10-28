"""Darts Orakel (dartsorakel.com) scraper. Free, public endpoints only; nothing behind the subscription paywall.

Data: Darts Orakel. Used for a non-commercial project with rate limiting and caching.
"""

import html

from .http import PoliteClient

BASE = "https://dartsorakel.com/api"

# Orakel "rankKey" values for per-match stats. Each match row carries stat1/stat2 (numerator/denominator)
# so we can aggregate correctly, e.g. average = 3 * sum(points) / sum(darts).
MATCH_STATS = {
    "average": 25,
    "first9_average": 1029,
    "checkout_pct": 1053,
    "180s": 26,
}

PAGE_SIZE = 1000


def _datatable(client: PoliteClient, url: str, params: dict) -> list[dict]:
    """Fetch every page of a DataTables-style endpoint."""
    rows, start = [], 0
    while True:
        page = client.get_json(url, {**params, "draw": 1, "start": start, "length": PAGE_SIZE})
        rows.extend(_unescape(r) for r in page["data"])
        start += PAGE_SIZE
        if start >= page.get("recordsFiltered", 0) or not page["data"]:
            return rows


def _unescape(row: dict) -> dict:
    """Orakel returns names HTML-escaped (e.g. O&#039;Connor)."""
    return {k: html.unescape(v) if isinstance(v, str) else v for k, v in row.items()}


def fetch_rankings(client: PoliteClient, top_n: int) -> list[dict]:
    """Current prize-money ranking (equivalent of the 2-year PDC Order of Merit) with DOB and country."""
    page = client.get_json(
        f"{BASE}/rankings",
        {"rankKey": 0, "isCurrent": 1, "isWomanOnly": 0, "draw": 1, "start": 0, "length": top_n},
    )
    return [_unescape(r) for r in page["data"]]


def fetch_events(client: PoliteClient, year: int) -> list[dict]:
    """All events of a year with category, prize fund, winner and event average."""
    return _datatable(client, f"{BASE}/events", {"year": year, "organCal": "All"})


def fetch_upcoming(client: PoliteClient) -> list[dict]:
    """Scheduled matches Orakel already knows (draw / order of play published): players, round, start time."""
    return _datatable(client, f"{BASE}/match/upcoming-matches-datatable", {})


def fetch_player_matches(client: PoliteClient, player_key: int, stat: str, date_from: str, date_to: str) -> list[dict]:
    """Every match of a player in a date range, with one stat (see MATCH_STATS) per row."""
    rows = _datatable(
        client,
        f"{BASE}/player/matches/{player_key}",
        {"dateFrom": date_from, "dateTo": date_to, "rankKey": MATCH_STATS[stat], "organStat": "All"},
    )
    for row in rows:
        row["stat_name"] = stat
        row["player_key"] = player_key
        row.pop("opponent", None)  # rendered HTML link, redundant with winner/loser fields
    return rows
