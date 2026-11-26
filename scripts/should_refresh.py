"""Decide whether the scheduled refresh should run today: while a major is running, the day before it starts and
the day after it ends (the refresh runs at night, so the last day's results, the final included, arrive then).
It also catches up: if the Databricks job has not succeeded since a major's last day (the workspace was asleep,
see workspace.py), it runs even after that window. Two and three days before a major it asks for a wake check, so a
sleeping workspace is reported while there is time to sign in.
Prints run=true|false and wake_check=true|false to $GITHUB_OUTPUT (or stdout). Manual runs (workflow_dispatch) skip
this check.

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


CATCH_UP_DAYS = 30  # a major whose end was missed is caught up within this many days


def refresh_today(today: date, date_ranges: list[tuple[date | None, date | None]],
                  last_success: date | None = None) -> bool:
    """True if a major runs today, starts tomorrow or ended yesterday, or if it ended earlier but no job run has
    succeeded since its last day (its final results are still missing)."""
    for start, end in date_ranges:
        if not (start and end):
            continue
        if start <= today + timedelta(days=1) and end + timedelta(days=1) >= today:
            return True
        if last_success and last_success <= end < today - timedelta(days=1) and today - end <= timedelta(days=CATCH_UP_DAYS):
            return True
    return False


def wake_check_today(today: date, date_ranges: list[tuple[date | None, date | None]]) -> bool:
    """True two or three days before a major starts."""
    return any(start and timedelta(days=2) <= start - today <= timedelta(days=3) for start, _ in date_ranges)


def last_success() -> date | None:
    """The newest successful job run; None (no catch-up) if Databricks can't be asked."""
    if not (os.environ.get("DATABRICKS_HOST") and os.environ.get("DATABRICKS_TOKEN")):
        return None
    try:
        from databricks.sdk import WorkspaceClient
        import workspace
        return workspace.last_success(WorkspaceClient())
    except Exception as exc:
        print("could not read the last job run:", str(exc).splitlines()[0][:200])
        return None


def main() -> None:
    today = date.today()
    client = PoliteClient(min_interval=1.0, cache_ttl=0)
    ranges, read = [], 0
    for title in major_pages(today):
        page = wikipedia.fetch_page_wikitext(client, title)
        if page.get("wikitext"):
            read += 1
            ranges.append(calendar.infobox_dates(page["wikitext"]))
    success = last_success()
    run = refresh_today(today, ranges, success) if read else True
    wake = not run and wake_check_today(today, ranges)
    lines = [f"run={'true' if run else 'false'}", f"wake_check={'true' if wake else 'false'}"]
    print(f"{read} major pages read; last successful job run {success}; {'; '.join(lines)}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
