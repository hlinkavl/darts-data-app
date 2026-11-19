"""Start the Databricks App (it runs for 24 h on Free Edition, then stops by itself).

Used by the "start-app" GitHub workflow (the scheduled refresh does not start the app since 19 Nov 2026: it cost
more quota than the refresh). Credentials: DATABRICKS_HOST / DATABRICKS_TOKEN (CI) or a CLI profile
(DATABRICKS_CONFIG_PROFILE).
"""

from datetime import timedelta

from databricks.sdk import WorkspaceClient

APP_NAME = "darts-performance-analyzer"


def start_app(w: WorkspaceClient) -> None:
    app = w.apps.get(APP_NAME)
    if app.compute_status and app.compute_status.state and app.compute_status.state.value in ("ACTIVE", "STARTING"):
        print(f"app {APP_NAME} already running: {app.url}")
        return
    w.apps.start(APP_NAME).result(timeout=timedelta(minutes=20))
    print(f"app {APP_NAME} started for 24 h: {app.url}")


if __name__ == "__main__":
    start_app(WorkspaceClient())
