"""Player Profile: photo and key facts, PI over time, recent form, big-stage indicator, background, titles."""

import re
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui

COUNTRY = {"ENG": "England", "SCO": "Scotland", "WAL": "Wales", "NIR": "Northern Ireland", "IRL": "Ireland",
           "NED": "Netherlands", "BEL": "Belgium", "GER": "Germany", "AUT": "Austria", "POL": "Poland", "CZE": "Czech Republic",
           "ESP": "Spain", "POR": "Portugal", "LTU": "Lithuania", "LAT": "Latvia", "SWE": "Sweden", "DEN": "Denmark",
           "NOR": "Norway", "FIN": "Finland", "SUI": "Switzerland", "ITA": "Italy", "FRA": "France", "HUN": "Hungary",
           "AUS": "Australia", "NZL": "New Zealand", "CAN": "Canada", "USA": "United States", "JPN": "Japan", "PHI": "Philippines",
           "RSA": "South Africa", "CRO": "Croatia", "GIB": "Gibraltar", "SVK": "Slovakia", "SLO": "Slovenia", "EST": "Estonia"}


def _history_chart(hist: pd.DataFrame) -> go.Figure:
    hist = hist.sort_values("as_of_date")
    fig = go.Figure(go.Scatter(
        x=pd.to_datetime(hist["as_of_date"]), y=hist["pi"], mode="lines+markers",
        line=dict(color=ui.SERIES[0], width=2), marker=dict(size=8, color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        hovertemplate="%{x|%b %Y}: PI %{y:.2f}<extra></extra>"))
    fig.add_hline(y=5, line_dash="dot", line_color=ui.TEXT_2, annotation_text="average top-32 player",
                  annotation_font_color=ui.TEXT_2, annotation_position="bottom right")
    return ui.layout(fig, height=300, yaxis=dict(title="PI", range=[0, 10]), hovermode="x")


def _sentences(text: str, n: int) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text.strip())
    return [p for p in parts if p][:n]


def _facts(row: pd.Series, info: pd.Series) -> pd.DataFrame:
    facts = []
    dob = pd.to_datetime(info.get("date_of_birth"), errors="coerce")
    if pd.notna(dob):
        facts.append(("Born", f"{dob:%d %B %Y} ({int((pd.Timestamp(date.today()) - dob).days // 365.25)} years)"))
    country = info.get("country")
    if isinstance(country, str):
        facts.append(("Country", COUNTRY.get(country, country)))
    if isinstance(info.get("nickname"), str):
        facts.append(("Nickname", f"“{info['nickname']}”"))
    money = info.get("prize_money_2y")
    if pd.notna(money):
        facts.append(("Prize money (2 years)", f"£{int(money):,}"))
    return pd.DataFrame(facts, columns=["", " "])


def _titles(player_key: int) -> None:
    t = data.table("player_titles")
    t = t[t["player_key"] == player_key] if len(t) else t
    st.subheader("🏆 Titles")
    if t.empty:
        st.caption("No titles in our data (PDC events since 2021).")
        return
    majors = t[t["title_group"] == "Major"].sort_values("event_date", ascending=False)
    if len(majors):
        st.markdown("**Majors**")
        for r in majors.itertuples():
            st.markdown(f"- {pd.Timestamp(r.event_date).year} · {r.tournament_name}")
    counts = t[t["title_group"] != "Major"].groupby("title_group").agg(titles=("tournament_name", "size"),
                                                                       last=("event_date", "max")).reset_index()
    if len(counts):
        counts["last"] = pd.to_datetime(counts["last"]).dt.strftime("%b %Y")
        st.dataframe(counts.rename(columns={"title_group": "Other titles", "titles": "Wins", "last": "Most recent"}),
                     hide_index=True, width="stretch")
    st.caption("Events won since 2021 in our data (PDC tours and majors).")


def render() -> None:
    st.title("👤 Player Profile")
    pi = data.current_pi()
    if pi.empty:
        st.warning("No Performance Index yet.")
        return
    names = pi.sort_values("rank")["player_name"].tolist()
    default = st.session_state.get("player", names[0])
    name = st.selectbox("Player", names, index=names.index(default) if default in names else 0, key="player",
                        placeholder="Type a name…")
    row = pi[pi["player_name"] == name].iloc[0]
    info = data.players()
    info = info[info["player_key"] == row["player_key"]]
    info = info.iloc[0] if len(info) else pd.Series(dtype=object)

    photo, head = st.columns([1, 4])
    with photo:
        url = ui.photo_url(info.get("image_file"), 360)
        if url:
            st.image(url, width=170)
            st.caption(ui.photo_credit(info["image_file"]))
    with head:
        nickname = info.get("nickname")
        st.markdown(f"## {name}" + (f" · *“{nickname}”*" if isinstance(nickname, str) and nickname else ""))
        c = st.columns(4)
        oom = info.get("prize_money_rank")
        c[0].metric("PDC Order of Merit", f"#{int(oom)}" if pd.notna(oom) else ui.oom_rank(row.get("oom_rank")),
                    help="Current position in the official PDC ranking (2-year prize money)")
        c[1].metric("Performance Index", ui.num(row["pi"], 2), help=ui.PI_HELP)
        c[2].metric("PI rank", f"#{int(row['rank'])}")
        c[3].metric("Effective Average", ui.num(row["effective_average"]), help=ui.EFFECTIVE_AVERAGE_HELP)
        d = st.columns(4)
        d[0].metric("3-Dart Average (L30)", ui.num(row["avg_l30"], 2), help="Points ÷ darts × 3 over the last 30 matches")
        d[1].metric("Form (L10 vs L30)", f"{row['form']:+.2f}" if pd.notna(row["form"]) else "–",
                    help="Average of the last 10 matches minus the average of the last 30")
        d[2].metric("Opponent-Weighted Elo", ui.num(row["elo"], 0), help="Rating from results: wins over strong players count more")
        stage = row.get("stage_delta")
        d[3].metric("Stage Delta", f"{stage:+.2f}" if pd.notna(stage) else "–",
                    help="Average on stage events (majors, European Tour, World Series, Premier League) minus on floor events, "
                         "last 24 months. Information only: it narrowly misses the model's selection rules and does not change the PI.")

    st.subheader("PI over time")
    hist = data.table("performance_index")
    st.plotly_chart(_history_chart(hist[hist["player_key"] == row["player_key"]]), width="stretch",
                    config={"displayModeBar": False})
    st.caption("Monthly snapshots, each computed only from matches before that date (with the current model's weights).")

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

    st.subheader("Profile")
    facts_col, bio_col = st.columns([2, 3])
    with facts_col:
        st.dataframe(_facts(row, info), hide_index=True, width="stretch")
    with bio_col:
        intro = info.get("intro")
        if isinstance(intro, str) and intro:
            for s in _sentences(intro, 4):
                st.markdown(f"- {s}")
            title = info.get("enwiki_title")
            if isinstance(title, str):
                st.caption(f"Source: [Wikipedia – {title}](https://en.wikipedia.org/wiki/{title.replace(' ', '_')}) (CC BY-SA)")
        else:
            st.caption("No Wikipedia background found for this player yet.")
        st.caption("AI summary of form and interviews (PDC news): coming soon.")

    _titles(int(row["player_key"]))
