"""Season calendar of the majors: match Wikipedia pages to majors and read the event dates from the infobox."""

import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}


def _clean(text: str) -> str:
    text = re.sub(r"<ref[^>]*/>|<ref.*?</ref>|<[^>]+>", " ", text, flags=re.S)
    text = re.sub(r"\{\{\s*nowrap\s*\|\s*(?:1=)?", "", text).replace("}}", "")
    return re.sub(r"\s+", " ", text.replace("&ndash;", "–").replace("&nbsp;", " ")).strip()


def parse_date_range(text: str) -> tuple[date | None, date | None]:
    """'11 December 2026 – 3 January 2027', '14–22 November 2026', '5 February – 28 May 2026', '25 October 2026'."""
    t = _clean(text)
    parts = [p.strip() for p in re.split(r"\s*[–—-]\s*", t) if p.strip()]
    found = [re.match(r"(\d{1,2})?\s*([A-Za-z]+)?\s*(\d{4})?$", p) for p in parts[:2]]
    if not found or not all(found):
        return None, None
    end_day, end_month, end_year = found[-1].groups()
    start_day, start_month, start_year = found[0].groups()
    end_month = end_month or start_month
    start_month = start_month or end_month
    start_year = start_year or end_year
    try:
        end = date(int(end_year), MONTHS[end_month.lower()], int(end_day))
        start = date(int(start_year), MONTHS[start_month.lower()], int(start_day))
    except (TypeError, KeyError, ValueError):
        return None, None
    if start > end:  # e.g. "11 December – 3 January 2027" without the first year
        start = start.replace(year=start.year - 1)
    return start, end


def infobox_dates(wikitext: str) -> tuple[date | None, date | None]:
    m = re.search(r"\|\s*dates\s*=\s*([^\n]+)", wikitext)
    return parse_date_range(m.group(1)) if m else (None, None)


def match_major(title: str, majors: dict, years=range(2020, 2031)) -> tuple[int, int] | None:
    """(tournament_key, edition year) for a Wikipedia title, using the `wiki` patterns in config/majors.yml."""
    for key, m in majors.items():
        for year in years:
            if m["wiki"].format(year=year) == title:
                return int(key), year
    return None
