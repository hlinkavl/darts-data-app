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
    checks = health.draws(cal, TODAY) + [health.freshness(date(2026, 11, 15))]
    df = health.report(checks)
    assert df.iloc[0]["status"] == health.YELLOW and health.overall(df) == health.YELLOW


def test_name_matching():
    assert health.player_matching(["A", "B"])[0].status == health.GREEN
    assert health.player_matching([str(i) for i in range(8)])[0].status == health.YELLOW
    known_gap = health.player_matching([], [str(i) for i in range(15)])
    assert [c.status for c in known_gap] == [health.GREEN, health.GREEN]


def test_open_draw_matches_overdue_are_red():
    open_matches = pd.DataFrame({"event_title": ["2026 Grand Slam"] * 2, "round_name": ["Second round", "Quarter-finals"],
                                 "start_time": pd.to_datetime(["2026-11-13", "2026-11-15"])})
    red = health.overdue_matches(open_matches, TODAY)  # TODAY = 16 Nov: the 13 Nov match is 3 days overdue
    assert red.status == health.RED and red.value == "1 matches"
    assert health.overdue_matches(open_matches.iloc[1:], TODAY).status == health.GREEN
    assert health.overdue_matches(pd.DataFrame(), TODAY).status == health.GREEN
    assert health.freshness(date(2026, 10, 1)).status == health.GREEN  # weeks without results are normal now


def test_teapot_418_counts_as_blocked():
    manifest = pd.DataFrame([{"source": "mastercaller", "dataset": None, "rows": 0, "status": "error",
                              "error": "HTTP 418: 418 Client Error:  for url: https://mastercaller.com/pdc-tournaments"}])
    red = [c for c in health.ingestion(manifest, pd.Timestamp("2026-11-16"), TODAY, True) if c.status == health.RED]
    assert len(red) == 1 and "Don't work around it" in red[0].action
