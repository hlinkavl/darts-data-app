"""Decide whether the scheduled refresh should run today: only while a major is running or starts tomorrow.

Prints run=true|false to $GITHUB_OUTPUT (or stdout). Manual runs (workflow_dispatch) skip this check.
Reads gold.majors_calendar through the SQL warehouse; if the table doesn't exist yet, it says true.
"""

import os

from databricks.sdk import WorkspaceClient

CATALOG = os.environ.get("DARTS_CATALOG", "workspace")
QUERY = f"""
SELECT count(*) FROM {CATALOG}.darts_gold.majors_calendar
WHERE status = 'in progress'
   OR (start_date <= date_add(current_date(), 1) AND end_date >= current_date())
"""


def main() -> None:
    w = WorkspaceClient()
    warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID") or next(iter(w.warehouses.list())).id
    resp = w.statement_execution.execute_statement(statement=QUERY, warehouse_id=warehouse, wait_timeout="50s")
    if resp.status.state.value != "SUCCEEDED":
        print(f"calendar query {resp.status.state.value}: {resp.status.error}; refreshing to be safe")
        run = True
    else:
        run = int(resp.result.data_array[0][0]) > 0
    line = f"run={'true' if run else 'false'}"
    print(line)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
