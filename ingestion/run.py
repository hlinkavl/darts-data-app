"""Fetch the sources and upload the output to the Unity Catalog Volume.

    python -m ingestion.run --upload

Sources, official APIs only (since 14 Nov 2026):
- Wikipedia (MediaWiki API): the official PDC Order of Merit (current snapshot every run, monthly history once),
  the pages of the majors (calendar, draws, and the results with 3-dart averages of every major match) and the
  background (incl. a free photo) of tracked and drawn players.
- PDC news RSS: the latest official articles (kept forever in bronze, input for AI summaries).

Historical sources, fetched once and kept in the Volume as training data: Darts Orakel (2021 - 28 Oct 2026, it
blocked our client on 30 Oct 2026) and Mastercaller (Oct - 9 Nov 2026, it started refusing GitHub-hosted runners
on 11 Nov 2026). Neither is fetched any more; see docs/MAINTENANCE.md, Decisions and limits.

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

from . import pdc_news, wikipedia
from .http import PoliteClient

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
VOLUME_ROOT = "/Volumes/{catalog}/darts_bronze/raw"
MAJORS_CONFIG = Path(__file__).resolve().parent.parent / "config" / "majors.yml"

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

def run_wikipedia(w, catalog: str, today: date, run_id: str) -> list[Path]:
    client = PoliteClient(min_interval=1.0, cache_ttl=7 * 24 * 3600)
    current = wikipedia.fetch_rankings_at(PoliteClient(min_interval=1.0, cache_ttl=0), today.isoformat())
    paths = [write_jsonl("wikipedia", "rankings", current, run_id)]

    history_files = _files(w, catalog, "wikipedia", "rankings_history")
    last = _read_jsonl(w, history_files[-1]) if history_files else []
    stale = not last or last[0].get("parser", 1) < wikipedia.RANKINGS_PARSER
    if stale:  # once, or again after a parser fix
        months, d = [], RANKINGS_HISTORY_FROM
        while d <= today:
            months.append(d)
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        history = [row for m in months for row in wikipedia.fetch_rankings_at(client, m.isoformat())]
        paths.append(write_jsonl("wikipedia", "rankings_history", history, run_id))

    fresh = PoliteClient(min_interval=1.0, cache_ttl=0)  # draws and results change during an event
    pages = [wikipedia.fetch_page_wikitext(fresh, title) for title in major_pages(today)]
    paths.append(write_jsonl("wikipedia", "tournament_pages", pages, run_id))

    previous = [r for f in _files(w, catalog, "wikipedia", "player_background") for r in _read_jsonl(w, f)]
    background = fetch_backgrounds(client, background_names(current, pages), previous, today)
    paths.append(write_jsonl("wikipedia", "player_background", background, run_id))
    return paths


def background_names(current: list[dict], pages: list[dict]) -> list[str]:
    """Tracked players (top of the Order of Merit) plus everyone in the majors' draws, e.g. World Championship
    qualifiers, so the draw shows their photos too."""
    names = [r["player_name"] for r in current if r["rank"] <= TRACKED_PLAYERS]
    drawn = set().union(*(wikipedia.draw_players(p.get("wikitext")) for p in pages)) if pages else set()
    return names + sorted(drawn - set(names))


def fetch_backgrounds(client: PoliteClient, names: list[str], previous: list[dict], today: date) -> list[dict]:
    latest = {r.get("name"): r for r in previous}  # files are read oldest first, so the last record wins
    out = []
    for name in names:
        if not wikipedia.needs_background(latest.get(name), today):
            continue
        try:
            out.append(wikipedia.fetch_player_background(client, name))
        except Exception as exc:  # one missing background must not stop the refresh; retried next run
            log.warning("no background for %s: %s", name, exc)
    log.info("wikipedia: background for %s of %s players", len(out), len(names))
    return out


def upload(w, paths: list[Path], catalog: str) -> None:
    root = VOLUME_ROOT.format(catalog=catalog)
    for path in paths:
        target = f"{root}/{path.relative_to(RAW_DIR).as_posix()}"
        with path.open("rb") as f:
            w.files.upload(target, f, overwrite=True)
        log.info("uploaded %s", target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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

    # Each source runs on its own: one failing (e.g. blocked with 403) must not stop the others. The manifest
    # records what every source returned; the health report reads it.
    paths, manifest = [], []
    for source, step in (("wikipedia", lambda: run_wikipedia(w, args.catalog, today, run_id)),
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
