"""Start the darts_refresh job in Databricks and wait for it; exit 1 if it doesn't succeed (CI e-mails on failure).
With --start-app (scheduled runs, i.e. during a major) it also starts the Databricks App."""

import sys
from datetime import timedelta

from databricks.sdk import WorkspaceClient

JOB_SUFFIX = "darts_refresh"
APP_NAME = "darts-performance-analyzer"
WAIT_MINUTES = 80  # a full run takes ~50 min on serverless (2026-11-01); speeding it up is planned


def main() -> None:
    w = WorkspaceClient()
    job = next((j for j in w.jobs.list() if j.settings.name.endswith(JOB_SUFFIX)), None)
    if job is None:
        sys.exit(f"no job named *{JOB_SUFFIX} found: deploy the bundle first")
    print(f"starting {job.settings.name} ({job.job_id})")
    run = w.jobs.run_now(job.job_id).result(timeout=timedelta(minutes=WAIT_MINUTES))
    for task in sorted(run.tasks, key=lambda t: t.start_time or 0):
        print(f"  {task.task_key}: {task.state.result_state.value if task.state.result_state else task.state.life_cycle_state.value}")
    state = run.state.result_state.value if run.state.result_state else "UNKNOWN"
    print("result:", state, run.run_page_url)
    if state != "SUCCESS":
        sys.exit(1)
    if "--start-app" in sys.argv:
        start_app(w)


def start_app(w: WorkspaceClient) -> None:
    """During a major the app should be up: start it (Free Edition stops apps after 24 h, so the daily refresh
    keeps it running for the whole event). Outside majors it stays stopped to save compute."""
    app = w.apps.get(APP_NAME)
    if app.compute_status and app.compute_status.state and app.compute_status.state.value in ("ACTIVE", "STARTING"):
        print(f"app {APP_NAME} already running: {app.url}")
        return
    w.apps.start(APP_NAME).result(timeout=timedelta(minutes=20))
    print(f"app {APP_NAME} started: {app.url}")


if __name__ == "__main__":
    main()
