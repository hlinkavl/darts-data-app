"""Darts Performance Analyzer: Streamlit app (Databricks App; public copy on Streamlit Community Cloud; local snapshot
for development)."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Darts Performance Analyzer", page_icon="🎯", layout="wide")

import data  # noqa: E402
import ui  # noqa: E402
from views import admin, ask, leaderboard, methodology, player, tournaments  # noqa: E402

PAGES = {
    "tournaments": st.Page(tournaments.render, title="Tournament Overview", icon="🏆", url_path="tournaments", default=True),
    "player": st.Page(player.render, title="Player Profile", icon="👤", url_path="player"),
    "leaderboard": st.Page(leaderboard.render, title="PI Leaderboard", icon="📊", url_path="leaderboard"),
    "ask": st.Page(ask.render, title="Ask the data", icon="🔎", url_path="ask"),
    "methodology": st.Page(methodology.render, title="Methodology", icon="📖", url_path="methodology"),
    "health": st.Page(admin.render, title="Data & Health", icon="⚙️", url_path="health"),
}
if data.MODE == "public":  # Genie needs the Databricks workspace
    PAGES.pop("ask")
st.session_state["pages"] = PAGES  # lets a page switch to another one (st.switch_page)
pages = st.navigation(list(PAGES.values()))

with st.sidebar:
    st.markdown("### 🎯 Darts Performance Analyzer")
    s = data.data_status()
    st.markdown(f"**Health:** {ui.status_label(s['status'])}")
    if s["data_until"] is not None:
        st.caption(f"Results until {pd.Timestamp(s['data_until']):%d %b %Y}")
    if s["checked_at"] is not None:
        st.caption(f"Last refresh {pd.Timestamp(s['checked_at']):%d %b %Y %H:%M} UTC")
    if s["mode"] == "local":
        st.caption("🧪 Local snapshot")
    elif s["mode"] == "public":
        st.caption("Public copy, updated after every refresh (daily during majors).")
    st.caption(ui.CREDITS)

pages.run()
