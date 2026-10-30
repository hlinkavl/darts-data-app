"""Run all scrapers and upload the output to the Unity Catalog Volume.

    python -m ingestion.run --upload            # incremental (default)

Sources (since 30 Oct 2026, when Darts Orakel blocked our client; its earlier data stays in the Volume):
- Mastercaller: results of every PDC tournament played since the last run (minus LOOKBACK_DAYS, to pick up
  multi-day events), and the scheduled matches of the next UPCOMING_DAYS days.
- PDC news RSS: the latest official articles (kept forever in bronze, input for AI summaries).
- Wikipedia: the official PDC Order of Merit (current snapshot every run, monthly history once), the pages of
  the majors (calendar, draws) and the background of tracked players not seen before.

Every run writes its own folder, so a run never overwrites an earlier one:
raw/<source>/<run_id>/<dataset>.jsonl, run_id = YYYY-MM-DDTHHMMSS (sortable).
"""

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from . import mastercaller, pdc_news, wikipedia
from .http import PoliteClient

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
VOLUME_ROOT = "/Volumes/{catalog}/darts_bronze/raw"
MAJORS_CONFIG = Path(__file__).resolve().parent.parent / "config" / "majors.yml"
SERIES_CONFIG = Path(__file__).resolve().parent.parent / "config" / "mastercaller_series.yml"

FIRST_SINCE = date(2026, 10, 1)       # first Mastercaller run overlaps Orakel's last month (validation)
LOOKBACK_DAYS = 3                      # re-read recent days: multi-day events, late corrections
UPCOMING_DAYS = 7                      # scheduled matches shown as "upcoming"
RANKINGS_HISTORY_FROM = date(2021, 1, 1)
TRACKED_PLAYERS = 150                  # top N of the PDC Order of Merit

log = logging.getLogger("ingestion")


def major_pages(today: date) -> list[str]:
    """Wikipedia pages of every major from last year to next year (calendar, draws, backtests), plus the
    World Championships since 2024. Pages that don't exist yet are stored with an error and retried next run."""
    majors = yaml.safe_load(MAJORS_CONFIG.read_text())["majors"]
    titles = [m["wiki"].format(year=y) for y in range(today.year - 1, today.year + 2) for m in majors.values()]
    titles += [majors[1]["wiki"].format(year=y) for y in range(2024, today.year - 1)]
    return sorted(set(titles))


def configured_series() -> set[str]:
    """Series we always treat as PDC (the pdc-tournaments page does not link every series, e.g. Players
    Championships): majors plus the groups in config/mastercaller_series.yml."""
    majors = yaml.safe_load(MAJORS_CONFIG.read_text())["majors"]
    groups = yaml.safe_load(SERIES_CONFIG.read_text())
    return {m["mastercaller"] for m in majors.values() if m.get("mastercaller")} | {s for g in groups.values() for s in g}


def write_jsonl(source: str, dataset: str, rows: list[dict], run_id: str) -> Path:
    path = RAW_DIR / source / run_id / f"{dataset}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    log.info("wrote %s rows to %s", len(rows), path.relative_to(RAW_DIR.parent))
    return path


# ------------------------------------------------------------------------------------- state in the Volume

def _runs(w, catalog: str, source: str) -> list[str]:
    root = f"{VOLUME_ROOT.format(catalog=catalog)}/{source}"
    try:
        return sorted(e.name for e in w.files.list_directory_contents(root) if e.is_directory)
    except Exception:  # directory missing on a fresh workspace
        return []


def _files(w, catalog: str, source: str, dataset: str) -> list[str]:
    root = f"{VOLUME_ROOT.format(catalog=catalog)}/{source}"
    out = []
    for run in _runs(w, catalog, source):
        names = {e.name for e in w.files.list_directory_contents(f"{root}/{run}")}
        if f"{dataset}.jsonl" in names:
            out.append(f"{root}/{run}/{dataset}.jsonl")
    return out


def _read_jsonl(w, path: str) -> list[dict]:
    return [json.loads(l) for l in w.files.download(path).contents.read().decode().splitlines() if l]


# ---------------------------------------------------------------------------------------------- sources

def run_mastercaller(since: date, today: date, run_id: str) -> list[Path]:
    client = PoliteClient(min_interval=3.0, cache_ttl=3600)
    pdc_series = mastercaller.fetch_pdc_series(client) | configured_series()
    tournaments = set()
    day = since
    while day <= today:
        links, _ = mastercaller.fetch_day(client, day)
        tournaments |= {(s, e) for s, e in links if s in pdc_series}
        day += timedelta(days=1)
    log.info("mastercaller: %s PDC tournaments played %s .. %s", len(tournaments), since, today)

    results = []
    for series, edition in sorted(tournaments):
        results.extend(mastercaller.fetch_results(client, series, edition))

    upcoming = []
    for offset in range(UPCOMING_DAYS + 1):
        _, matches = mastercaller.fetch_day(client, today + timedelta(days=offset))
        upcoming.extend(m for m in matches if "score_a" not in m)
    return [write_jsonl("mastercaller", "results", results, run_id),
            write_jsonl("mastercaller", "upcoming_matches", upcoming, run_id)]


def run_wikipedia(w, catalog: str, today: date, run_id: str) -> list[Path]:
    client = PoliteClient(min_interval=1.0, cache_ttl=7 * 24 * 3600)
    current = wikipedia.fetch_rankings_at(PoliteClient(min_interval=1.0, cache_ttl=0), today.isoformat())
    paths = [write_jsonl("wikipedia", "rankings", current, run_id)]

    if not _files(w, catalog, "wikipedia", "rankings_history"):
        months, d = [], RANKINGS_HISTORY_FROM
        while d <= today:
            months.append(d)
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        history = [row for m in months for row in wikipedia.fetch_rankings_at(client, m.isoformat())]
        paths.append(write_jsonl("wikipedia", "rankings_history", history, run_id))

    pages = [wikipedia.fetch_page_wikitext(client, title) for title in major_pages(today)]
    paths.append(write_jsonl("wikipedia", "tournament_pages", pages, run_id))

    known = {r.get("name") for f in _files(w, catalog, "wikipedia", "player_background") for r in _read_jsonl(w, f)}
    tracked = [r["player_name"] for r in current if r["rank"] <= TRACKED_PLAYERS]
    background = []
    for name in tracked:
        if name in known:
            continue
        try:
            background.append(wikipedia.fetch_player_background(client, name))
        except Exception as exc:  # one missing background must not stop the refresh; retried next run
            log.warning("no background for %s: %s", name, exc)
    paths.append(write_jsonl("wikipedia", "player_background", background, run_id))
    return paths


def upload(w, paths: list[Path], catalog: str) -> None:
    root = VOLUME_ROOT.format(catalog=catalog)
    for path in paths:
        target = f"{root}/{path.relative_to(RAW_DIR).as_posix()}"
        with path.open("rb") as f:
            w.files.upload(target, f, overwrite=True)
        log.info("uploaded %s", target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", help="override the first day of results to fetch (YYYY-MM-DD)")
    parser.add_argument("--upload", action="store_true", help="upload output to the UC Volume")
    parser.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "darts"))
    parser.add_argument("--catalog", default=os.environ.get("DARTS_CATALOG", "workspace"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_id = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    today = date.today()

    from databricks.sdk import WorkspaceClient

    # Profile locally; in CI the SDK reads DATABRICKS_HOST / DATABRICKS_TOKEN from the environment.
    w = WorkspaceClient() if os.environ.get("DATABRICKS_HOST") else WorkspaceClient(profile=args.profile)

    previous = _runs(w, args.catalog, "mastercaller")
    if args.since:
        since = date.fromisoformat(args.since)
    elif previous:
        since = date.fromisoformat(previous[-1][:10]) - timedelta(days=LOOKBACK_DAYS)
    else:
        since = FIRST_SINCE
    log.info("results since %s (previous mastercaller run: %s)", since, previous[-1] if previous else None)

    # Each source runs on its own: one failing (e.g. blocked with 403) must not stop the others. The manifest
    # records what every source returned; the health report reads it.
    paths, manifest = [], []
    for source, step in (("mastercaller", lambda: run_mastercaller(since, today, run_id)),
                         ("wikipedia", lambda: run_wikipedia(w, args.catalog, today, run_id)),
                         ("pdc_news", lambda: [write_jsonl("pdc_news", "articles", pdc_news.fetch(PoliteClient()), run_id)])):
        try:
            produced = step()
            paths += produced
            for path in produced:
                rows = sum(1 for _ in path.open())
                manifest.append({"run_id": run_id, "source": source, "dataset": path.stem, "rows": rows,
                                 "status": "ok", "error": None})
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            log.error("%s failed: %s", source, exc)
            manifest.append({"run_id": run_id, "source": source, "dataset": None, "rows": 0, "status": "error",
                             "error": f"HTTP {status}: {exc}" if status else str(exc)[:500]})
    paths.append(write_jsonl("ingestion", "manifest", manifest, run_id))
    if args.upload:
        upload(w, paths, args.catalog)
    if any(m["status"] == "error" for m in manifest):
        raise SystemExit("ingestion finished with errors, see the manifest")  # non-zero exit: CI sends an e-mail


if __name__ == "__main__":
    main()
