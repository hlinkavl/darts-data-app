"""Wake check a few days before a major: is the Databricks workspace awake (workspace.py)? Asks the SQL warehouse to
start, which a sleeping workspace refuses, and stops it again right away if it was stopped (a few seconds of
compute). Exits 1 with a clear message if the workspace is asleep, so GitHub e-mails while there is time to sign in.
Any other problem only prints a warning: the refresh itself will report it."""

import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import BadRequest
from databricks.sdk.service.sql import State

from workspace import asleep_message, is_asleep


def main() -> None:
    w = WorkspaceClient()
    try:
        warehouse = next(iter(w.warehouses.list()))
        was_stopped = warehouse.state in (State.STOPPED, State.STOPPING)
        w.warehouses.start(warehouse.id)
    except Exception as exc:
        if is_asleep(str(exc)) or isinstance(exc, BadRequest):  # a start is refused with 400 only when asleep
            print("::error::" + asleep_message())
            sys.exit(1)
        print("::warning::wake check could not run:", str(exc).splitlines()[0][:300])
        return
    if was_stopped:
        try:
            w.warehouses.stop(warehouse.id)
        except Exception as exc:  # it stops by itself after 10 minutes anyway
            print("could not stop the warehouse again:", str(exc).splitlines()[0][:200])
    print("the Databricks workspace is awake")


if __name__ == "__main__":
    main()
