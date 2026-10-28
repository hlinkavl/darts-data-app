"""Run all scrapers and upload the output to the Unity Catalog Volume.

    python -m ingestion.run --upload            # incremental (default)
    python -m ingestion.run --full --upload     # full backfill since --since

Incremental: players tracked in the previous run get matches from (previous run - LOOKBACK_DAYS);
players new to the top N get their full history since --since. Wikipedia background is fetched
for new players only. Every run writes its own folder, so a run never overwrites an earlier one:
raw/<source>/<run_id>/<dataset>.jsonl, run_id = YYYY-MM-DDTHHMMSS (sortable).
"""

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from . import orakel, wikipedia
from .http import PoliteClient

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
VOLUME_ROOT = "/Volumes/{catalog}/darts_bronze/raw"
FULL_SINCE = "2023-01-01"
# Re-fetch recent matches so late stat corrections and multi-day events are picked up.
LOOKBACK_DAYS = 14

MAJORS_CONFIG = Path(__file__).resolve().parent.parent / "config" / "majors.yml"


def major_pages(today: date) -> list[str]:
    """Wikipedia pages of every major from last year to next year (calendar, draws, backtests), plus the
    World Championships since 2024. Pages that don't exist yet are stored with an error and retried next run."""
    majors = yaml.safe_load(MAJORS_CONFIG.read_text())["majors"]
    titles = [m["wiki"].format(year=y) for y in range(today.year - 1, today.year + 2) for m in majors.values()]
    titles += [majors[1]["wiki"].format(year=y) for y in range(2024, today.year - 1)]
    return sorted(set(titles))

log = logging.getLogger("ingestion")


def write_jsonl(source: str, dataset: str, rows: list[dict], run_id: str) -> Path:
    path = RAW_DIR / source / run_id / f"{dataset}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("wrote %s rows to %s", len(rows), path.relative_to(RAW_DIR.parent))
    return path


def previous_run(w, catalog: str) -> tuple[str, set[int]] | None:
    """Latest Orakel run in the Volume and the player keys it tracked, or None if there is none."""
    root = f"{VOLUME_ROOT.format(catalog=catalog)}/orakel"
    try:
        runs = sorted(e.name for e in w.files.list_directory_contents(root) if e.is_directory)
    except Exception:  # directory missing on a fresh workspace
        return None
    if not runs:
        return None
    rankings = w.files.download(f"{root}/{runs[-1]}/rankings.jsonl").contents.read().decode()
    return runs[-1], {json.loads(line)["player_key"] for line in rankings.splitlines() if line}


def run_orakel(client: PoliteClient, rankings: list[dict], since_known: str, full_since: str, until: str,
               known: set[int], run_id: str) -> list[Path]:
    paths = [write_jsonl("orakel", "rankings", rankings, run_id),
             write_jsonl("orakel", "upcoming_matches", orakel.fetch_upcoming(client), run_id)]

    events = []
    for year in range(int(since_known[:4]), int(until[:4]) + 1):
        events.extend(orakel.fetch_events(client, year))
    paths.append(write_jsonl("orakel", "events", events, run_id))

    for stat in orakel.MATCH_STATS:
        rows = []
        for i, player in enumerate(rankings, 1):
            since = since_known if player["player_key"] in known else full_since
            rows.extend(orakel.fetch_player_matches(client, player["player_key"], stat, since, until))
            if i % 25 == 0:
                log.info("%s: %s/%s players", stat, i, len(rankings))
        paths.append(write_jsonl("orakel", f"matches_{stat}", rows, run_id))
    return paths


def run_wikipedia(players: list[dict], run_id: str) -> list[Path]:
    client = PoliteClient(min_interval=1.0, cache_ttl=7 * 24 * 3600)
    pages = [wikipedia.fetch_page_wikitext(client, title) for title in major_pages(date.today())]
    background = [wikipedia.fetch_player_background(client, p["player_name"]) | {"player_key": p["player_key"]}
                  for p in players]
    return [
        write_jsonl("wikipedia", "tournament_pages", pages, run_id),
        write_jsonl("wikipedia", "player_background", background, run_id),
    ]


def upload(w, paths: list[Path], catalog: str) -> None:
    root = VOLUME_ROOT.format(catalog=catalog)
    for path in paths:
        target = f"{root}/{path.relative_to(RAW_DIR).as_posix()}"
        with path.open("rb") as f:
            w.files.upload(target, f, overwrite=True)
        log.info("uploaded %s", target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="ignore previous runs and fetch everything since --since")
    parser.add_argument("--since", default=FULL_SINCE, help="first match date for --full (YYYY-MM-DD)")
    parser.add_argument("--until", default=date.today().isoformat(), help="last match date (YYYY-MM-DD)")
    parser.add_argument("--top", type=int, default=150, help="number of players from the prize-money ranking")
    parser.add_argument("--skip-wiki", action="store_true")
    parser.add_argument("--upload", action="store_true", help="upload output to the UC Volume")
    parser.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "darts"))
    parser.add_argument("--catalog", default=os.environ.get("DARTS_CATALOG", "workspace"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_id = datetime.now().strftime("%Y-%m-%dT%H%M%S")

    w = None
    if args.upload or not args.full:
        from databricks.sdk import WorkspaceClient

        # Profile locally; in CI the SDK reads DATABRICKS_HOST / DATABRICKS_TOKEN from the environment.
        w = WorkspaceClient() if os.environ.get("DATABRICKS_HOST") else WorkspaceClient(profile=args.profile)

    prev = None if args.full else previous_run(w, args.catalog)
    if prev:
        prev_run, known = prev
        since_known = (date.fromisoformat(prev_run[:10]) - timedelta(days=LOOKBACK_DAYS)).isoformat()
        log.info("incremental run: previous %s, %s known players, re-fetching since %s", prev_run, len(known), since_known)
    else:
        known, since_known = set(), args.since
        log.info("full run since %s", since_known)

    client = PoliteClient(min_interval=2.0)
    rankings = orakel.fetch_rankings(client, args.top)
    paths = run_orakel(client, rankings, since_known, args.since, args.until, known, run_id)
    if not args.skip_wiki:
        paths += run_wikipedia([p for p in rankings if p["player_key"] not in known], run_id)
    if args.upload:
        upload(w, paths, args.catalog)


if __name__ == "__main__":
    main()
