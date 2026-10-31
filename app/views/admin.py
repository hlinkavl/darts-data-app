"""Data & Health: refresh button, last refresh, health report with recommended actions, model versions."""

import pandas as pd
import streamlit as st

import data
import refresh
import ui


def render() -> None:
    st.title("⚙️ Data & Health")
    status = data.data_status()
    c = st.columns(3)
    c[0].metric("Health", ui.status_label(status["status"]))
    c[1].metric("Data until", f"{pd.Timestamp(status['data_until']):%d %b %Y}" if status["data_until"] is not None else "–")
    c[2].metric("Model", status["model_version"] or "–")

    st.subheader("Refresh")
    if data.MODE == "local":
        st.caption("Local mode (snapshot). Refresh with `make ingest` and `python scripts/build_local_snapshot.py`.")
    elif refresh.can_trigger():
        if st.button("🔄 Refresh data now", type="primary"):
            ok, msg = refresh.trigger()
            (st.success if ok else st.error)(msg)
    else:
        st.caption(f"Automatic refresh runs daily during majors. To refresh now, start the "
                   f"[refresh workflow on GitHub]({refresh.ACTIONS_URL}) (\"Run workflow\").")
    runs = refresh.recent_runs()
    if runs:
        df = pd.DataFrame(runs)
        df["started"] = pd.to_datetime(df["started"]).dt.strftime("%d %b %Y %H:%M")
        df["result"] = df["result"].map({"success": "✅ success", "failure": "❌ failure", "skipped": "skipped"}).fillna(df["status"])
        st.dataframe(df[["started", "trigger", "result", "url"]], hide_index=True, width="stretch",
                     column_config={"url": st.column_config.LinkColumn("Run", display_text="open")})

    st.subheader("Health report")
    report = data.table("health_report")
    if report.empty:
        st.info("No health report yet.")
    else:
        report = report.assign(status=report["status"].map(ui.status_label))
        st.dataframe(report[["status", "area", "check", "value", "message", "action"]], hide_index=True,
                     width="stretch", column_config={"message": st.column_config.TextColumn(width="large"),
                                                              "action": st.column_config.TextColumn("What to do", width="large")})

    st.subheader("Model versions")
    reg = data.table("pi_model_registry")
    if len(reg):
        st.dataframe(reg.sort_values("decided_at", ascending=False)[["version", "status", "predictors", "test_log_loss", "reason"]],
                     hide_index=True, width="stretch")
    st.caption(ui.CREDITS)
