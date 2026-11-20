"""Download the app snapshot (parquet files written by the job's health task) from the Volume.

    python scripts/download_snapshot.py app/snapshot

Uses the Files API, which needs no compute (no quota). Used by the publish-app workflow; exits 1 if the snapshot is
missing, so a broken export never replaces the published one.
"""

import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analytics.snapshot import APP_SNAPSHOT_DIR, APP_TABLES  # noqa: E402

CATALOG = "workspace"
REQUIRED = {"players", "performance_index", "health_report", "pi_model_registry"}  # the app is useless without them


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "app/snapshot")
    out.mkdir(parents=True, exist_ok=True)
    w = WorkspaceClient()
    source = APP_SNAPSHOT_DIR.format(catalog=CATALOG)
    names = [e.name for e in w.files.list_directory_contents(source) if e.name.endswith(".parquet")]
    found = {n.removesuffix(".parquet") for n in names}
    if REQUIRED - found:
        sys.exit(f"snapshot in {source} is missing: {', '.join(sorted(REQUIRED - found))}")
    if set(APP_TABLES) - found:
        print("not in the snapshot (the app shows those parts empty):", ", ".join(sorted(set(APP_TABLES) - found)))
    for name in names:
        (out / name).write_bytes(w.files.download(f"{source}/{name}").contents.read())
    print(f"downloaded {len(names)} files to {out}")


if __name__ == "__main__":
    main()
