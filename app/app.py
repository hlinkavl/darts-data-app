"""Darts Performance Analyzer: Streamlit app (Databricks App; public copy on Streamlit Community Cloud; local snapshot
for development)."""

import importlib
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Darts Performance Analyzer", page_icon="🎯", layout="wide")

import data  # noqa: E402
import ui  # noqa: E402
from views import admin, ask, leaderboard, methodology, player, tournaments  # noqa: E402

import refresh  # noqa: E402


def _reload_changed(*modules) -> None:
    """Streamlit Community Cloud pulls a redeploy into the running process: it reruns this script but keeps the
    modules imported earlier, so a changed ui.py would stay old. Reload every app module whose file changed."""
    for m in modules:
        mtime = Path(m.__file__).stat().st_mtime
        if mtime > getattr(m, "_loaded_mtime", 0):
            importlib.reload(m)
            m._loaded_mtime = mtime


_reload_changed(data, ui, refresh, admin, ask, leaderboard, methodology, player, tournaments)

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
pages = st.navigation(list(PAGES.values()), position="top")

st.markdown(ui.CSS, unsafe_allow_html=True)
# On a phone Streamlit folds the top menu into the sidebar, so a row of pills (shown on phones only, ui.CSS) keeps
# the pages one tap away.
SHORT = {"tournaments": "🏆 Tournaments", "player": "👤 Player", "leaderboard": "📊 Leaderboard", "ask": "🔎 Ask",
         "methodology": "📖 Methodology", "health": "⚙️ Health"}
current = next(k for k, p in PAGES.items() if p.url_path == pages.url_path)
target = st.session_state.pop("nav_target", None)
if target and target != SHORT[current]:
    st.switch_page(PAGES[next(k for k, v in SHORT.items() if v == target)])
st.session_state["mobile_nav"] = SHORT[current]
with st.container(key="mobile_nav_row"):
    st.pills("Pages", [SHORT[k] for k in PAGES], key="mobile_nav", label_visibility="collapsed",
             on_change=lambda: st.session_state.update(nav_target=st.session_state["mobile_nav"]))
with st.sidebar:
    st.markdown(ui.sidebar_status(data.data_status()), unsafe_allow_html=True)

pages.run()
