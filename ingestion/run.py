"""Run all scrapers and (optionally) upload the output to the Unity Catalog Volume.

    python -m ingestion.run --since 2023-01-01 --top 150 --upload

Output layout (local and in the Volume): raw/<source>/<run_date>/<dataset>.jsonl
"""

import argparse
import json
import logging
import os
from datetime import date
from pathlib import Path

from . import orakel, wikipedia
from .http import PoliteClient

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
VOLUME_ROOT = "/Volumes/{catalog}/darts_bronze/raw"

# Tournament pages used for draws and backtests. The 2027 draw appears on Wikipedia in late November.
WC_PAGES = [f"{year} PDC World Darts Championship" for year in (2024, 2025, 2026, 2027)]

log = logging.getLogger("ingestion")


def write_jsonl(source: str, dataset: str, rows: list[dict], run_date: str) -> Path:
    path = RAW_DIR / source / run_date / f"{dataset}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("wrote %s rows to %s", len(rows), path.relative_to(RAW_DIR.parent))
    return path


def run_orakel(since: str, until: str, top_n: int, run_date: str) -> tuple[list[Path], list[dict]]:
    client = PoliteClient(min_interval=2.0)
    rankings = orakel.fetch_rankings(client, top_n)
    paths = [write_jsonl("orakel", "rankings", rankings, run_date)]

    events = []
    for year in range(int(since[:4]), int(until[:4]) + 1):
        events.extend(orakel.fetch_events(client, year))
    paths.append(write_jsonl("orakel", "events", events, run_date))

    for stat in orakel.MATCH_STATS:
        rows = []
        for i, player in enumerate(rankings, 1):
            rows.extend(orakel.fetch_player_matches(client, player["player_key"], stat, since, until))
            if i % 25 == 0:
                log.info("%s: %s/%s players", stat, i, len(rankings))
        paths.append(write_jsonl("orakel", f"matches_{stat}", rows, run_date))
    return paths, rankings


def run_wikipedia(players: list[dict], run_date: str) -> list[Path]:
    client = PoliteClient(min_interval=1.0, cache_ttl=7 * 24 * 3600)
    pages = [wikipedia.fetch_page_wikitext(client, title) for title in WC_PAGES]
    background = [wikipedia.fetch_player_background(client, p["player_name"]) | {"player_key": p["player_key"]}
                  for p in players]
    return [
        write_jsonl("wikipedia", "tournament_pages", pages, run_date),
        write_jsonl("wikipedia", "player_background", background, run_date),
    ]


def upload(paths: list[Path], profile: str, catalog: str) -> None:
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient(profile=profile)
    root = VOLUME_ROOT.format(catalog=catalog)
    for path in paths:
        target = f"{root}/{path.relative_to(RAW_DIR).as_posix()}"
        with path.open("rb") as f:
            w.files.upload(target, f, overwrite=True)
        log.info("uploaded %s", target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default="2023-01-01", help="first match date (YYYY-MM-DD)")
    parser.add_argument("--until", default=date.today().isoformat(), help="last match date (YYYY-MM-DD)")
    parser.add_argument("--top", type=int, default=150, help="number of players from the prize-money ranking")
    parser.add_argument("--skip-wiki", action="store_true")
    parser.add_argument("--upload", action="store_true", help="upload output to the UC Volume")
    parser.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "darts"))
    parser.add_argument("--catalog", default=os.environ.get("DARTS_CATALOG", "workspace"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_date = date.today().isoformat()

    paths, players = run_orakel(args.since, args.until, args.top, run_date)
    if not args.skip_wiki:
        paths += run_wikipedia(players, run_date)
    if args.upload:
        upload(paths, args.profile, args.catalog)


if __name__ == "__main__":
    main()
