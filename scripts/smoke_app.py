"""Smoke test of every app page, every tournament and a few players, without a browser.

    python scripts/smoke_app.py local        # data/app_snapshot
    DATABRICKS_CONFIG_PROFILE=darts DATABRICKS_WAREHOUSE_ID=<id> python scripts/smoke_app.py databricks

Run the databricks mode before deploying the app: the warehouse returns other types than the snapshot.
Exits non-zero on any exception or table read error.
"""
import sys

from streamlit.testing.v1 import AppTest

MODE = sys.argv[1] if len(sys.argv) > 1 else "local"
failures = 0
SRC = """
import sys, os
sys.path.insert(0, os.path.abspath('app'))
os.environ['DARTS_DATA'] = '{mode}'
import data
data.MODE = '{mode}'
from views import {name}
{name}.render()
"""
def check(at, label):
    global failures
    errs = [e.value[:400] for e in at.exception]
    data_errs = at.session_state["data_errors"] if "data_errors" in at.session_state else {}
    failures += len(errs) + len(data_errs)
    print(f"{label:55s} exceptions={len(errs)} data_errors={list(data_errs)}")
    for e in errs: print("    ", e)
    for k, v in data_errs.items(): print("    ", k, v[:200])
for name in ["tournaments", "player", "leaderboard", "methodology", "admin", "ask"]:
    at = AppTest.from_string(SRC.format(name=name, mode=MODE), default_timeout=300); at.run()
    check(at, name)
    if name == "tournaments" and not at.exception:
        box = at.selectbox(key="event")
        for i in range(len(box.options)):
            at.selectbox(key="event").set_value(i).run(); check(at, "  " + box.format_func(i)[:50])
    if name == "player" and not at.exception:
        opts = at.selectbox(key="player").options
        for n in [opts[0], opts[len(opts) // 2], opts[-1]]:
            at.selectbox(key="player").set_value(n).run(); check(at, "  " + n)
    if name == "leaderboard" and not at.exception:
        at.button_group(key="lb_order").set_value("Performance Index").run(); check(at, "  rank by PI")
        at.selectbox(key="lb_find").set_value(at.selectbox(key="lb_find").options[5]).run(); check(at, "  search")

sys.exit(1 if failures else 0)
