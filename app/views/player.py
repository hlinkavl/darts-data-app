"""Player Profile: PI and what drives it, PI over time, recent form, big-stage indicator, background."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui


def _history_chart(hist: pd.DataFrame) -> go.Figure:
    hist = hist.sort_values("as_of_date")
    fig = go.Figure(go.Scatter(
        x=pd.to_datetime(hist["as_of_date"]), y=hist["pi"], mode="lines+markers",
        line=dict(color=ui.SERIES[0], width=2), marker=dict(size=8, color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        hovertemplate="%{x|%b %Y}: PI %{y:.2f}<extra></extra>"))
    fig.add_hline(y=5, line_dash="dot", line_color=ui.TEXT_2, annotation_text="average top-32 player",
                  annotation_font_color=ui.TEXT_2, annotation_position="bottom right")
    return ui.layout(fig, height=280, yaxis=dict(title="PI", range=[0, 10]), hovermode="x")


def render() -> None:
    st.title("👤 Player Profile")
    pi = data.current_pi()
    if pi.empty:
        st.warning("No Performance Index yet.")
        return
    names = pi.sort_values("rank")["player_name"].tolist()
    default = st.session_state.get("player", names[0])
    name = st.selectbox("Player", names, index=names.index(default) if default in names else 0, key="player")
    row = pi[pi["player_name"] == name].iloc[0]
    info = data.players()
    info = info[info["player_key"] == row["player_key"]]
    info = info.iloc[0] if len(info) else pd.Series(dtype=object)

    nickname = info.get("nickname")
    st.markdown(f"## {name}" + (f" · *“{nickname}”*" if isinstance(nickname, str) and nickname else ""))
    meta = []
    if isinstance(info.get("country"), str):
        meta.append(info["country"])
    dob = pd.to_datetime(info.get("date_of_birth"), errors="coerce")
    if pd.notna(dob):
        meta.append(f"{int((pd.Timestamp(date.today()) - dob).days // 365.25)} years")
    meta.append(f"Order of Merit {ui.oom_rank(row.get('oom_rank'))}")
    st.caption(" · ".join(meta))

    c = st.columns(5)
    c[0].metric("Performance Index", ui.num(row["pi"], 2), help="10 × chance to beat an average top-32 player in a typical match")
    c[1].metric("PI rank", f"#{int(row['rank'])}")
    c[2].metric("Effective Average", ui.num(row["effective_average"]), help="The whole strength in 3-dart-average points")
    c[3].metric("3-Dart Average (L30)", ui.num(row["avg_l30"], 2))
    c[4].metric("Form (L10 vs L30)", f"{row['form']:+.2f}" if pd.notna(row["form"]) else "–",
                help="Average of the last 10 matches minus the last 30")

    coef = data.versioned("pi_coefficients")
    left, right = st.columns(2)
    with left:
        st.subheader("What drives the PI")
        st.plotly_chart(ui.contributions_chart(row, coef["predictor"].tolist()), width="stretch",
                        config={"displayModeBar": False})
        st.caption("Blue raises, red lowers the chance against the average top-32 player. The parts add up to the PI.")
    with right:
        st.subheader("PI over time")
        hist = data.table("performance_index")
        st.plotly_chart(_history_chart(hist[hist["player_key"] == row["player_key"]]), width="stretch",
                        config={"displayModeBar": False})

    st.subheader("Recent form")
    recent = data.table("player_recent_matches")
    recent = recent[recent["player_key"] == row["player_key"]].sort_values("recency").head(10)
    if len(recent):
        st.markdown(f"Last 5: {ui.form_chips(recent['result'].head(5).tolist())}")
        show = recent.assign(match_date=pd.to_datetime(recent["match_date"]).dt.date)[
            ["match_date", "tournament_name", "round", "opponent_name", "result", "score", "average", "checkout_pct"]]
        st.dataframe(show, hide_index=True, width="stretch", column_config={
            "match_date": "Date", "tournament_name": "Event", "round": "Round", "opponent_name": "Opponent",
            "result": "", "score": "Score", "average": st.column_config.NumberColumn("Average", format="%.2f"),
            "checkout_pct": st.column_config.NumberColumn("Checkout %", format="%.1f")})

    stage = row.get("stage_delta")
    if pd.notna(stage):
        st.subheader("On the big stage")
        st.metric("Stage Delta", f"{stage:+.2f}", help="3-dart average on stage events (majors, European Tour, World Series, "
                  "Premier League) minus on floor events, last 24 months, shrunk for small samples")
        st.caption("Information only: it narrowly misses the model's selection rules, so it does not change the PI. "
                   "See Methodology.")

    st.subheader("Background")
    intro = info.get("intro")
    if isinstance(intro, str) and intro:
        text = intro if len(intro) < 600 else intro[:600].rsplit(". ", 1)[0] + "."
        st.write(text)
        title = info.get("enwiki_title")
        if isinstance(title, str):
            st.caption(f"Source: [Wikipedia – {title}](https://en.wikipedia.org/wiki/{title.replace(' ', '_')}) (CC BY-SA)")
    else:
        st.caption("No Wikipedia background found for this player yet.")
    st.caption("AI summary of form and interviews (PDC news): coming soon.")
