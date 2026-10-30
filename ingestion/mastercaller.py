"""Mastercaller (mastercaller.com): PDC match results with 3-dart averages (stats by iDarts).

robots.txt allows all agents. We identify ourselves, wait 3 s between requests and fetch only what is new:
one match-center page per day since the last run, then the full results of the PDC tournaments played on
those days. Pages are large (0.3-1 MB), so a refresh stays at a few requests. The match center of future
days lists scheduled matches once a draw or order of play is out (our "upcoming matches").

Data: Mastercaller / iDarts.
"""

import html
import re
from datetime import date

from .http import PoliteClient

BASE = "https://mastercaller.com"
PLAYER_MARK = "@@PLAYER@@"
DAY_TIME = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{1,2}) (\w{3})(?: - (\d{2}:\d{2}))?$")
CLOCK = re.compile(r"^\d{2}:\d{2}$")
ROUND = re.compile(r"^(Last \d+|Round \d+|(First|Second|Third|Fourth) Round|Quarter-finals|Semi-finals|Final|"
                   r"Group [A-H]|Play-offs)$", re.I)
AVERAGE = re.compile(r"^\d{2,3}\.\d{2}$")
SCORE = re.compile(r"^\d{1,2}$")
RESULTS_LINK = re.compile(r'href="https://mastercaller\.com/tournaments/([a-z0-9-]+)/([a-z0-9-]+)/results"')
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# Series whose scores count sets, not legs.
SET_SERIES = {"pdc-world-championship", "world-grand-prix"}


def _tokens(page: str) -> list[str]:
    """Text tokens in document order. Player links become PLAYER_MARK + 'slug' + PLAYER_MARK + 'name'."""
    page = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "", page, flags=re.S)
    page = re.sub(
        r'<a[^>]+href="https://mastercaller\.com/players/([^"]+)"[^>]*>(.*?)</a>',
        lambda m: f"<i>{PLAYER_MARK}{m.group(1)}{PLAYER_MARK}{re.sub(r'<[^>]+>', ' ', m.group(2)).strip()}</i>",
        page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    return [t for t in (re.sub(r"\s+", " ", s).strip() for s in text.split("\n")) if t]


def _resolve_date(weekday: str, day: int, month: str, around_year: int) -> date | None:
    """Results pages print 'Wed 28 Oct' without a year; the weekday makes it unique among neighbouring years."""
    for year in (around_year, around_year - 1, around_year + 1):
        try:
            d = date(year, MONTHS[month], day)
        except (KeyError, ValueError):
            continue
        if WEEKDAYS[d.weekday()] == weekday:
            return d
    return None


def parse_matches(page: str, around_year: int, page_date: date | None = None) -> list[dict]:
    """Matches on a results page or a match-center page, in document order.

    A match is: [time] player A [avg A] score A score B player B [avg B]. Scheduled matches have no scores.
    On match-center pages (several tournaments per day) each match also gets the tournament it belongs to.
    """
    toks = _tokens(page)
    matches, current = [], None
    rnd = tournament = when = clock = None
    for i, tok in enumerate(toks):
        if tok == "See All Results" and i > 0:
            tournament = toks[i - 1]
        elif ROUND.match(tok):
            rnd = tok
        elif m := DAY_TIME.match(tok):
            when, clock = _resolve_date(m.group(1), int(m.group(2)), m.group(3), around_year), m.group(4)
        elif CLOCK.match(tok):
            clock = tok
        elif tok.startswith(PLAYER_MARK):
            _, slug, name = tok.split(PLAYER_MARK)
            if current is None or "player_b_slug" in current:
                current = {"tournament": tournament, "round": rnd,
                           "match_date": (when or page_date).isoformat() if (when or page_date) else None,
                           "start_time": clock, "player_a_slug": slug, "player_a_name": name}
                matches.append(current)
            else:
                current["player_b_slug"], current["player_b_name"] = slug, name
        elif current is not None and AVERAGE.match(tok):
            current.setdefault("avg_b" if "player_b_slug" in current else "avg_a", float(tok))
        elif current is not None and SCORE.match(tok) and "player_b_slug" not in current:
            current.setdefault("score_a" if "score_a" not in current else "score_b", int(tok))
    return [m for m in matches if "player_b_slug" in m]


def fetch_day(client: PoliteClient, day: date) -> tuple[list[tuple[str, str]], list[dict]]:
    """Match center of one day: (series, edition) of tournaments with results, and the matches listed."""
    page = client.get_text(f"{BASE}/matchcenter/{day:%Y/%m/%d}")
    return sorted(set(RESULTS_LINK.findall(page))), parse_matches(page, day.year, page_date=day)


def fetch_results(client: PoliteClient, series: str, edition: str) -> list[dict]:
    """All matches of one tournament edition, e.g. ('players-championships', '2026-pc-31-den-bosch')."""
    page = client.get_text(f"{BASE}/tournaments/{series}/{edition}/results")
    title = re.search(r"<title>Results of (.*?) - Mastercaller</title>", page)
    year = int(re.match(r"(\d{4})", edition).group(1)) if re.match(r"\d{4}", edition) else date.today().year
    rows = parse_matches(page, year)
    for r in rows:
        r.update({"series": series, "edition": edition, "tournament": html.unescape(title.group(1)) if title else edition,
                  "unit": "sets" if series in SET_SERIES else "legs"})
    return rows


def fetch_pdc_series(client: PoliteClient) -> set[str]:
    """Series listed under PDC tournaments (excludes WDF and other organisations)."""
    page = client.get_text(f"{BASE}/pdc-tournaments")
    return set(re.findall(r'href="https://mastercaller\.com/tournaments/([a-z0-9-]+)"', page))
