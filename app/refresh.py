"""Refresh from the app: start the GitHub Actions workflow (ingestion runs outside Databricks), show recent runs.

Starting a run needs GITHUB_TOKEN (fine-grained token, Actions: read and write on this repository), provided
to the Databricks App through a secret resource. Reading runs needs no token (public repository).
"""

import os

import requests

REPO = os.getenv("GITHUB_REPO", "hlinkavl/darts-data-app")
WORKFLOW = "refresh.yml"
API = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}"
ACTIONS_URL = f"https://github.com/{REPO}/actions/workflows/{WORKFLOW}"


def can_trigger() -> bool:
    return bool(os.getenv("GITHUB_TOKEN"))


def trigger() -> tuple[bool, str]:
    resp = requests.post(f"{API}/dispatches", json={"ref": "main"}, timeout=15,
                         headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                  "Accept": "application/vnd.github+json"})
    if resp.status_code == 204:
        return True, "Refresh started. New data usually arrives in 10–30 minutes."
    return False, f"GitHub refused the request ({resp.status_code}): {resp.text[:200]}"


def recent_runs(n: int = 5) -> list[dict]:
    try:
        resp = requests.get(f"{API}/runs", params={"per_page": n}, timeout=10,
                            headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
    except requests.RequestException:
        return []
    return [{"started": r["created_at"], "status": r["status"], "result": r["conclusion"], "trigger": r["event"],
             "url": r["html_url"]} for r in resp.json().get("workflow_runs", [])]
