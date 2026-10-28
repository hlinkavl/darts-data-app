"""Create or update the saved SQL queries in Databricks from sql/queries/*.sql (idempotent, matched by name).

    python scripts/sync_queries.py [--profile darts] [--warehouse-id ID]

The first comment line of each file becomes the query description. Queries live in the workspace folder
/Users/<you>/darts-data-app/queries, named "darts: <file name>".
"""

import argparse
import os
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import CreateQueryRequestQuery, UpdateQueryRequestQuery

QUERY_DIR = Path(__file__).resolve().parent.parent / "sql" / "queries"
PREFIX = "darts: "


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE", "darts"))
    parser.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID"))
    args = parser.parse_args()

    w = WorkspaceClient(profile=args.profile)
    warehouse_id = args.warehouse_id or next(iter(w.warehouses.list())).id
    folder = f"/Users/{w.current_user.me().user_name}/darts-data-app/queries"
    w.workspace.mkdirs(folder)
    existing = {q.display_name: q.id for q in w.queries.list() if q.display_name and q.display_name.startswith(PREFIX)}

    for path in sorted(QUERY_DIR.glob("*.sql")):
        text = path.read_text()
        first = text.splitlines()[0]
        description = first.removeprefix("--").strip() if first.startswith("--") else ""
        name = PREFIX + path.stem
        if name in existing:
            w.queries.update(existing[name], update_mask="query_text,description,warehouse_id",
                             query=UpdateQueryRequestQuery(query_text=text, description=description,
                                                           warehouse_id=warehouse_id))
            print(f"updated  {name}")
        else:
            w.queries.create(query=CreateQueryRequestQuery(display_name=name, query_text=text, description=description,
                                                           warehouse_id=warehouse_id, parent_path=folder))
            print(f"created  {name}")


if __name__ == "__main__":
    main()
