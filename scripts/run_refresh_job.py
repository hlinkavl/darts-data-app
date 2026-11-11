"""Start the darts_refresh job in Databricks and wait for it; exit 1 if it doesn't succeed (CI e-mails on failure).
With --start-app (scheduled runs, i.e. during a major) it also starts the Databricks App, even when the job failed:
a failed run never overwrites the last good gold tables, so the app still shows correct (if older) data."""

import sys
from datetime import timedelta

from databricks.sdk import WorkspaceClient

from start_app import start_app

JOB_SUFFIX = "darts_refresh"
WAIT_MINUTES = 45  # a run takes ~6 min (~25 min with a monthly refit); measured 2026-11-09


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
    if "--start-app" in sys.argv:
        start_app(w)
    if state != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
