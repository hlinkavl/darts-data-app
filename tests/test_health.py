import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from analytics import health  # noqa: E402

TODAY = date(2026, 11, 16)


def test_blocked_source_is_red_with_dont_circumvent_action():
    manifest = pd.DataFrame([
        {"source": "mastercaller", "dataset": None, "rows": 0, "status": "error", "error": "HTTP 403: Forbidden"},
        {"source": "wikipedia", "dataset": "rankings", "rows": 448, "status": "ok", "error": None},
    ])
    checks = health.ingestion(manifest, pd.Timestamp("2026-11-16"), TODAY, major_running=True)
    red = [c for c in checks if c.status == health.RED]
    assert len(red) == 1 and "Don't work around it" in red[0].action


def test_stale_ingestion_during_major_is_yellow():
    manifest = pd.DataFrame([{"source": "wikipedia", "dataset": "rankings", "rows": 448, "status": "ok", "error": None}])
    checks = health.ingestion(manifest, pd.Timestamp("2026-11-12"), TODAY, major_running=True)
    assert checks[0].status == health.YELLOW


def test_missing_draw_for_running_major_and_overall_status():
    cal = pd.DataFrame([{"tournament_name": "Grand Slam", "wiki_title": "2026 Grand Slam of Darts",
                         "start_date": pd.Timestamp("2026-11-14"), "end_date": pd.Timestamp("2026-11-22"),
                         "status": "in progress", "has_draw": False}])
    checks = health.draws(cal, TODAY) + [health.freshness(date(2026, 11, 15), TODAY, True)]
    df = health.report(checks)
    assert df.iloc[0]["status"] == health.YELLOW and health.overall(df) == health.YELLOW


def test_new_series_and_name_matching():
    assert health.new_series({"players-championships", "budapest-darts-masters"}, {"players-championships"})[0].status == health.YELLOW
    assert health.player_matching(["A", "B"]).status == health.GREEN
    assert health.player_matching([str(i) for i in range(8)]).status == health.YELLOW
