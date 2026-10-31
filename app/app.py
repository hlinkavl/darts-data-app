"""Darts Performance Analyzer: Streamlit app (Databricks App in production, local snapshot for development)."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Darts Performance Analyzer", page_icon="🎯", layout="wide")

import data  # noqa: E402
import ui  # noqa: E402
from views import admin, ask, leaderboard, methodology, player, tournaments  # noqa: E402

pages = st.navigation([
    st.Page(tournaments.render, title="Tournament Overview", icon="🏆", url_path="tournaments", default=True),
    st.Page(player.render, title="Player Profile", icon="👤", url_path="player"),
    st.Page(leaderboard.render, title="PI Leaderboard", icon="📊", url_path="leaderboard"),
    st.Page(ask.render, title="Ask the data", icon="💬", url_path="ask"),
    st.Page(methodology.render, title="Methodology", icon="📖", url_path="methodology"),
    st.Page(admin.render, title="Data & Health", icon="⚙️", url_path="health"),
])

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
    st.caption(ui.CREDITS)

pages.run()
