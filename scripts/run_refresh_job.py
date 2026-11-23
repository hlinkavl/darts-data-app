"""Start the darts_refresh job in Databricks and wait for it; exit 1 if it doesn't succeed (CI e-mails on failure).
With --start-app it also starts the Databricks App, even when the job failed or could not start: a failed run never
overwrites the last good gold tables, so the app still shows correct (if older) data. The scheduled refresh does not
pass it (a running app costs more quota than the job); the app is started with the start-app workflow."""

import sys
from datetime import timedelta

from databricks.sdk import WorkspaceClient

from start_app import start_app

JOB_SUFFIX = "darts_refresh"
WAIT_MINUTES = 100  # usually ~6 min; after a major ~45 min (new top 150 rescores the PI history + backtest), ~70 with a refit too (measured 2026-11-23)


def main() -> None:
    w = WorkspaceClient()
    job = next((j for j in w.jobs.list() if j.settings.name.endswith(JOB_SUFFIX)), None)
    if job is None:
        sys.exit(f"no job named *{JOB_SUFFIX} found: deploy the bundle first")
    print(f"starting {job.settings.name} ({job.job_id})")
    state = "NOT STARTED"
    try:
        waiter = w.jobs.run_now(job.job_id)
        try:
            waiter.result(timeout=timedelta(minutes=WAIT_MINUTES))
        except Exception as exc:  # a failed run raises here; report it, but still start the app below
            print("job did not succeed:", str(exc).splitlines()[0][:300])
        run = w.jobs.get_run(waiter.run_id)
        for task in sorted(run.tasks or [], key=lambda t: t.start_time or 0):
            print(f"  {task.task_key}: {task.state.result_state.value if task.state.result_state else task.state.life_cycle_state.value}")
        state = run.state.result_state.value if run.state and run.state.result_state else "UNKNOWN"
        print("result:", state, run.run_page_url)
    except Exception as exc:  # e.g. the Free Edition quota: "Triggering new runs ... is currently disabled temporarily"
        print("could not run the job:", str(exc).splitlines()[0][:300])
    if "--start-app" in sys.argv:
        # Also after a failure: the gold tables keep the last good data.
        try:
            start_app(w)
        except Exception as exc:
            print("could not start the app:", str(exc).splitlines()[0][:300])
    if state != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
