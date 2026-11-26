"""The Databricks Free Edition workspace goes to sleep after about 4-5 days without a sign-in in the browser: all
compute is refused (job runs: "Triggering new runs ... is currently disabled temporarily", warehouse start:
DENY_NEW_AND_EXISTING_RESOURCES / INACTIVE). API calls with the token do not count as activity and cannot wake it;
a browser sign-in does. Seen on 14 and 26 Nov 2026, both after a few quiet days between majors."""

import os
from datetime import date, datetime, timezone

from databricks.sdk import WorkspaceClient

JOB_SUFFIX = "darts_refresh"
# The SQL API answered "The request could not be processed by the warehouse." while asleep on 26 Nov 2026.
ASLEEP_MARKERS = ("disabled temporarily", "INACTIVE", "DENY_NEW_AND_EXISTING_RESOURCES", "could not be processed by the warehouse")


def is_asleep(error: str) -> bool:
    return any(m.lower() in error.lower() for m in ASLEEP_MARKERS)


def asleep_message() -> str:
    host = os.environ.get("DATABRICKS_HOST", "the Databricks workspace")
    return (f"The Databricks workspace is asleep (Free Edition pauses compute after ~4-5 days without a browser "
            f"sign-in) or over its daily quota. Sign in at {host}, then run the refresh again: Actions -> refresh -> "
            f"Run workflow. If it was the quota, it works again tomorrow.")


def refresh_job(w: WorkspaceClient):
    return next((j for j in w.jobs.list() if j.settings.name.endswith(JOB_SUFFIX)), None)


def last_success(w: WorkspaceClient) -> date | None:
    """Start date (UTC) of the newest successful darts_refresh run."""
    job = refresh_job(w)
    if job is None:
        return None
    for run in w.jobs.list_runs(job_id=job.job_id, completed_only=True):
        if run.state and run.state.result_state and run.state.result_state.value == "SUCCESS":
            return datetime.fromtimestamp(run.start_time / 1000, timezone.utc).date()
    return None
