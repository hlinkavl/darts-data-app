"""Decide whether the scheduled refresh should run today: only while a major is running or starts tomorrow.
Prints run=true|false to $GITHUB_OUTPUT (or stdout). Manual runs (workflow_dispatch) skip this check.

The dates come straight from the majors' Wikipedia pages (infobox), the same source as gold.majors_calendar,
so the daily check costs no Databricks compute (querying the calendar table started the SQL warehouse).
If no page can be read, it says true, to be safe.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from analytics import calendar  # noqa: E402
from ingestion import wikipedia  # noqa: E402
from ingestion.http import PoliteClient  # noqa: E402
from ingestion.run import major_pages  # noqa: E402


def refresh_today(today: date, date_ranges: list[tuple[date | None, date | None]]) -> bool:
    """True if a major runs today or starts tomorrow."""
    return any(start and end and start <= today + timedelta(days=1) and end >= today for start, end in date_ranges)


def main() -> None:
    today = date.today()
    client = PoliteClient(min_interval=1.0, cache_ttl=0)
    ranges, read = [], 0
    for title in major_pages(today):
        page = wikipedia.fetch_page_wikitext(client, title)
        if page.get("wikitext"):
            read += 1
            ranges.append(calendar.infobox_dates(page["wikitext"]))
    run = refresh_today(today, ranges) if read else True
    line = f"run={'true' if run else 'false'}"
    print(f"{read} major pages read; {line}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
