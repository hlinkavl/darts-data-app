"""Data & Health: data status, refresh button and recent refreshes, health report, model versions."""

from html import escape

import pandas as pd
import streamlit as st

import data
import refresh
import ui

HEADLINE = {"green": ("All checks passed", "#2a3a2a", "#8fd18f"), "yellow": ("Needs attention", "#3d3420", "#f2c46b"),
            "red": ("Problem", "#4a2323", "#ff8a8a")}
ORDER = {"red": 0, "yellow": 1, "green": 2}


def _when(ts, fmt: str = "%d %b %Y") -> str:
    return f"{pd.Timestamp(ts):{fmt}}" if ts is not None and pd.notna(ts) else "–"


def _summary(status: dict, report: pd.DataFrame) -> None:
    """One card: overall health as a pill, then the facts that tell whether the data is fresh."""
    label, bg, fg = HEADLINE.get(status["status"], HEADLINE["green"])
    ok = int((report["status"] == "green").sum()) if len(report) else 0
    facts = [("Results until", _when(status["data_until"])),
             ("Last refresh", _when(status["checked_at"], "%d %b %Y %H:%M") + (" UTC" if status["checked_at"] is not None else "")),
             ("Checks passed", f"{ok} of {len(report)}" if len(report) else "–"),
             ("Active model", status["model_version"] or "–")]
    cells = "".join(f"<div><div style='color:{ui.TEXT_2};font-size:0.78em'>{k}</div>"
                    f"<div style='color:{ui.TEXT};font-weight:600;margin-top:2px'>{escape(v)}</div></div>" for k, v in facts)
    st.markdown(
        f"<div style='border:1px solid {ui.GRID};border-radius:12px;padding:16px 20px;margin:6px 0 18px'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap'>"
        f"<div style='font-size:1.2em;font-weight:700;color:{ui.TEXT}'>Data status</div>"
        f"<span style='background:{bg};color:{fg};border-radius:999px;padding:3px 12px;font-size:0.82em;"
        f"font-weight:600'>{label}</span></div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px 28px;"
        f"border-top:1px solid {ui.GRID};margin-top:14px;padding-top:12px'>{cells}</div></div>",
        unsafe_allow_html=True)


def _issue_card(r) -> str:
    icon, _, color = ui.STATUS.get(r.status, ui.STATUS["yellow"])
    action = (f"<div style='color:{ui.TEXT};font-size:0.88em;margin-top:6px'><b>What to do:</b> {escape(str(r.action))}</div>"
              if isinstance(r.action, str) and r.action else "")
    return (f"<div style='border:1px solid {ui.GRID};border-left:4px solid {color};border-radius:10px;"
            f"padding:10px 14px;margin:8px 0'>"
            f"<div style='color:{ui.TEXT};font-weight:600'>{icon} {escape(str(r.check)[:1].upper() + str(r.check)[1:])} "
            f"<span style='color:{ui.TEXT_2};font-weight:400;font-size:0.85em'>· {escape(str(r.area))} · {escape(str(r.value))}</span></div>"
            f"<div style='color:{ui.TEXT_2};font-size:0.88em;margin-top:4px'>{escape(str(r.message))}</div>{action}</div>")


def _health(report: pd.DataFrame) -> None:
    st.subheader("Health report")
    if report.empty:
        st.info("No health report yet.")
        return
    report = report.assign(_o=report["status"].map(ORDER)).sort_values(["_o", "area", "check"])
    issues = report[report["status"] != "green"]
    if len(issues):
        st.markdown("".join(_issue_card(r) for r in issues.itertuples()), unsafe_allow_html=True)
    else:
        st.success("Every check passed.")
    with st.expander(f"All {len(report)} checks"):
        for area, rows in report.groupby("area", sort=True):
            st.markdown(f"**{area.capitalize()}**")
            st.markdown("\n".join(f"- {ui.STATUS.get(r.status, ('⚪',))[0]} {r.check}: {r.value}" for r in rows.itertuples()))


def _refreshes() -> None:
    st.subheader("Refresh")
    if data.MODE == "local":
        st.caption("Local mode (snapshot). Refresh with `make ingest` and `python scripts/build_local_snapshot.py`.")
    elif refresh.can_trigger():
        if st.button("🔄 Refresh data now", type="primary"):
            ok, msg = refresh.trigger()
            (st.success if ok else st.error)(msg)
        st.caption("Runs automatically every day during majors.")
    else:
        st.caption(f"Automatic refresh runs daily during majors. To refresh now, start the "
                   f"[refresh workflow on GitHub]({refresh.ACTIONS_URL}) (\"Run workflow\").")
    runs = refresh.recent_runs()
    if runs:
        with st.expander("Recent refreshes"):
            df = pd.DataFrame(runs)
            df["started"] = pd.to_datetime(df["started"]).dt.strftime("%d %b %Y %H:%M")
            df["result"] = df["result"].map({"success": "✅ success", "failure": "❌ failure", "skipped": "skipped"}).fillna(df["status"])
            df["trigger"] = df["trigger"].map({"schedule": "daily check", "workflow_dispatch": "by hand"}).fillna(df["trigger"])
            st.dataframe(df[["started", "trigger", "result", "url"]], hide_index=True, width="stretch",
                         column_config={"url": st.column_config.LinkColumn("Run", display_text="open")})
            st.caption("A daily check outside a major ends in seconds without refreshing.")


def render() -> None:
    st.title("⚙️ Data & Health")
    report = data.table("health_report")
    _summary(data.data_status(), report)
    _refreshes()
    _health(report)

    st.subheader("Model versions")
    reg = data.table("pi_model_registry")
    if len(reg):
        st.dataframe(reg.sort_values("decided_at", ascending=False)[["version", "status", "predictors", "test_log_loss", "reason"]],
                     hide_index=True, width="stretch",
                     column_config={"test_log_loss": st.column_config.NumberColumn("Test log loss", format="%.4f")})
    st.caption(ui.CREDITS)
