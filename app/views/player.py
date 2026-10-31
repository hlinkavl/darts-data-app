"""Player Profile: photo, Order of Merit and PI, the PI breakdown, PI over time, recent form, profile, titles."""

import re
from datetime import date
from html import escape

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

# How each PI input is shown in the breakdown: label, value format, one-line explanation.
INPUTS = {
    "avg_l30": ("3-Dart Average (L30)", lambda v: f"{v:.2f}", "Points per 3 darts over the last 30 matches"),
    "form": ("Form (L10 vs L30)", lambda v: f"{v:+.2f}",
             "Average of the last 10 matches minus the last 30; below zero = currently under the usual level"),
    "elo": ("Opponent-Weighted Elo", lambda v: f"{v:.0f}", "Rating from results: wins over strong players count more"),
    "oom_rank": ("PDC Order of Merit", lambda v: ui.oom_rank(v), "Official ranking (2-year prize money)"),
}
LABEL = f"color:{ui.TEXT_2};font-size:0.78em;text-transform:uppercase;letter-spacing:.04em"


def _history_chart(hist: pd.DataFrame) -> go.Figure:
    hist = hist.sort_values("as_of_date")
    fig = go.Figure(go.Scatter(
        x=pd.to_datetime(hist["as_of_date"]), y=hist["pi"], mode="lines+markers",
        line=dict(color=ui.SERIES[0], width=2), marker=dict(size=8, color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        hovertemplate="%{x|%b %Y}: PI %{y:.2f}<extra></extra>"))
    fig.add_hline(y=5, line_dash="dot", line_color=ui.TEXT_2, annotation_text="average top-32 player",
                  annotation_font_color=ui.TEXT_2, annotation_position="bottom right")
    return ui.layout(fig, height=300, yaxis=dict(title="PI", range=[0, 10]), hovermode="x")


def _header(name: str, row: pd.Series, info: pd.Series) -> None:
    """One card: round photo | '#<Order of Merit> Name' with nickname, country and age | PI | Effective Average."""
    nickname = info.get("nickname")
    sub = [f"“{escape(nickname)}”" if isinstance(nickname, str) and nickname else None,
           COUNTRY.get(info.get("country"), info.get("country")) if isinstance(info.get("country"), str) else None]
    dob = pd.to_datetime(info.get("date_of_birth"), errors="coerce")
    if pd.notna(dob):
        sub.append(f"{int((pd.Timestamp(date.today()) - dob).days // 365.25)} years")
    oom = info.get("prize_money_rank")
    oom_txt = f"#{int(oom)}" if pd.notna(oom) else ui.oom_rank(row.get("oom_rank"))
    image = info.get("image_file")

    with st.container(border=True):
        photo, who, score, effective = st.columns([1.2, 3, 1.4, 1.4], vertical_alignment="center")
        photo.markdown(f"<div style='text-align:center'>{ui.avatar(image, 128, name=name, ring=ui.GRID)}</div>",
                       unsafe_allow_html=True)
        who.markdown(
            f"<div style='font-size:2.1em;font-weight:700;line-height:1.2;color:{ui.TEXT}'>"
            f"<span title='Current position in the official PDC Order of Merit' style='color:{ui.TEXT_2}'>{oom_txt}</span> "
            f"{escape(name)}</div>"
            f"<div style='color:{ui.TEXT_2};margin-top:4px'>{' · '.join(s for s in sub if s)}</div>"
            f"<div style='color:{ui.TEXT_2};font-size:0.8em;margin-top:8px'>{oom_txt} in the PDC Order of Merit</div>",
            unsafe_allow_html=True)
        score.markdown(
            f"<div title='{escape(ui.PI_HELP)}' style='text-align:center'>"
            f"<div style='{LABEL}'>Performance Index ⓘ</div>"
            f"<div style='font-size:2.6em;font-weight:700;color:{ui.TEXT};line-height:1.1'>{ui.num(row['pi'], 2)}</div>"
            f"<div style='color:{ui.TEXT_2};font-size:0.85em'>#{int(row['rank'])} by PI</div></div>",
            unsafe_allow_html=True)
        base = row.get("ref_avg_l30")
        effective.markdown(
            f"<div title='{escape(ui.EFFECTIVE_AVERAGE_HELP)}' style='text-align:center'>"
            f"<div style='{LABEL}'>Effective Average ⓘ</div>"
            f"<div style='font-size:2.6em;font-weight:700;color:{ui.TEXT};line-height:1.1'>{ui.num(row['effective_average'])}</div>"
            f"<div style='color:{ui.TEXT_2};font-size:0.85em'>"
            f"{f'vs {ui.num(base)} top-32 average' if base is not None and pd.notna(base) else ''}</div></div>",
            unsafe_allow_html=True)


def _breakdown(row: pd.Series) -> None:
    """The player next to an average top-32 player in each PI input; the gap in 3-dart-average points. The last
    row adds them up: Effective Average vs the top-32 average. How gaps are converted is on the Methodology page."""
    coef = data.versioned("pi_coefficients").set_index("predictor")
    per_point = coef["beta_per_unit"].get("avg_l30")
    rows = []
    for p in [p for p in INPUTS if p in coef.index]:
        label, fmt, help_text = INPUTS[p]
        value, ref, contrib = row.get(p), row.get(f"ref_{p}"), row.get(f"contrib_{p}")
        if value is None or pd.isna(value) or not per_point or pd.isna(contrib):
            continue
        ref_txt = (ui.oom_rank(ref) if p == "oom_rank" else fmt(ref)) if ref is not None and pd.notna(ref) else "–"
        rows.append((label, help_text, fmt(value), ref_txt, contrib / per_point, False))
    base = row.get("ref_avg_l30")
    if rows and base is not None and pd.notna(base):
        # Shown to one decimal, the gaps must add up to the total as displayed: round the total from the displayed
        # numbers and give the rounding remainder to the largest gap.
        total = round(round(row["effective_average"], 1) - round(base, 1), 1)
        gaps = [round(r[4], 1) for r in rows]
        big = max(range(len(gaps)), key=lambda i: abs(gaps[i]))
        gaps[big] = round(gaps[big] + total - sum(gaps), 1)
        rows = [r[:4] + (g, r[5]) for r, g in zip(rows, gaps)]
        rows.append(("Effective Average", ui.EFFECTIVE_AVERAGE_HELP, ui.num(row["effective_average"]), ui.num(base),
                     total, True))

    st.subheader("PI breakdown")
    grid = "display:grid;grid-template-columns:2.2fr 1fr 1fr 1fr;gap:8px;align-items:center;padding:9px 4px"
    head = "".join(f"<div style='text-align:{a}'>{t}</div>" for t, a in
                   (("", "left"), ("Player", "right"), ("Top-32 average", "right"), ("Gap", "right")))
    html = f"<div style='{grid};color:{ui.TEXT_2};font-size:0.8em;border-bottom:1px solid {ui.GRID}'>{head}</div>"
    for label, help_text, value, ref_txt, pts, total in rows:
        line = f"border-top:2px solid {ui.GRID};margin-top:2px" if total else f"border-bottom:1px solid {ui.GRID}"
        gap = f"{'▲' if pts >= 0 else '▼'} {pts:+.1f}"
        html += (f"<div style='{grid};{line}'>"
                 f"<div title='{escape(help_text)}' style='color:{ui.TEXT};font-weight:{700 if total else 400}'>{label}</div>"
                 f"<div style='text-align:right;color:{ui.TEXT};font-weight:700;font-size:1.1em'>{value}</div>"
                 f"<div style='text-align:right;color:{ui.TEXT};font-weight:700'>{ref_txt}</div>"
                 f"<div style='text-align:right;color:{ui.WIN if pts >= 0 else ui.LOSS};font-weight:700'>{gap}</div></div>")
    st.markdown(f"<div style='max-width:760px'>{html}</div>", unsafe_allow_html=True)
    st.caption("Gap = what the input adds to (▲) or takes from (▼) the player's 3-dart average compared with an average "
               "top-32 player; together they make the Effective Average. How each gap is converted: see Methodology.")
    stage = row.get("stage_delta")
    if stage is not None and pd.notna(stage):
        st.caption(f"Stage Delta {stage:+.2f} · information only, not part of the PI: average on stage events minus "
                   "floor events over the last 24 months.")


def _recent_form(row: pd.Series, info_all: pd.DataFrame) -> None:
    st.subheader("Recent form")
    recent = data.table("player_recent_matches")
    recent = recent[recent["player_key"] == row["player_key"]].sort_values("recency").head(5)
    if recent.empty:
        st.caption("No recent matches.")
        return
    photos = dict(zip(info_all["player_key"], info_all["image_file"])) if "image_file" in info_all.columns else {}
    cards = []
    for m in recent.itertuples():
        won = m.result == "W"
        score = str(m.score).replace("-", " – ") if isinstance(m.score, str) else ""
        me = (f"<div style='flex:1;text-align:right;color:{ui.WIN if won else ui.TEXT_2};font-weight:{700 if won else 400}'>"
              f"{escape(m.player_name)}{ui.avatar(photos.get(m.player_key), 36, name=m.player_name)}</div>")
        opp = (f"<div style='flex:1;color:{ui.TEXT_2 if won else ui.WIN};font-weight:{400 if won else 700}'>"
               f"{ui.avatar(photos.get(m.opponent_key), 36, name=m.opponent_name)}{escape(str(m.opponent_name))}</div>")
        stats = " · ".join(s for s in (f"average {ui.num(m.average, 2)}" if pd.notna(m.average) else "",
                                       f"checkout {ui.num(m.checkout_pct)} %" if pd.notna(m.checkout_pct) else "") if s)
        cards.append(
            f"<div style='border:2px solid {ui.WIN if won else ui.LOSS};border-radius:10px;padding:10px 14px;margin:8px 0'>"
            f"<div style='color:{ui.TEXT_2};font-size:0.8em;margin-bottom:6px'>{'✓ Won' if won else '✗ Lost'} · "
            f"{pd.Timestamp(m.match_date):%d %b %Y} · {escape(str(m.tournament_name))} · {escape(str(m.round))}</div>"
            f"<div style='display:flex;align-items:center;gap:10px'>{me}"
            f"<div style='min-width:80px;text-align:center;font-size:1.3em;font-weight:700;color:{ui.TEXT}'>{score}</div>{opp}</div>"
            f"<div style='text-align:center;color:{ui.TEXT_2};font-size:0.8em;margin-top:6px'>{stats}</div></div>")
    st.markdown("".join(cards), unsafe_allow_html=True)


def _sentences(text: str, n: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(text.split()))
    return " ".join(p for p in parts[:n] if p)


def _profile(info: pd.Series) -> None:
    """One paragraph: the Wikipedia intro plus the facts it does not mention."""
    st.subheader("Profile")
    intro = info.get("intro") if isinstance(info.get("intro"), str) else ""
    text = _sentences(intro, 4) if intro else ""
    extra = []
    nickname = info.get("nickname")
    if isinstance(nickname, str) and nickname and nickname not in text:
        extra.append(f"Nickname: “{nickname}”.")
    dob = pd.to_datetime(info.get("date_of_birth"), errors="coerce")
    if pd.notna(dob) and str(dob.year) not in text:
        extra.append(f"Born {dob:%d %B %Y}.")
    if not text and isinstance(info.get("country"), str):
        extra.append(f"Plays for {COUNTRY.get(info['country'], info['country'])}.")
    money = info.get("prize_money_2y")
    if pd.notna(money):
        extra.append(f"Prize money over the last two years: £{int(money):,}.")
    paragraph = " ".join([text] + extra).strip()
    st.markdown(paragraph or "No background yet.")
    sources = []
    title = info.get("enwiki_title")
    if isinstance(title, str) and intro:
        sources.append(f"Text: [Wikipedia – {title}](https://en.wikipedia.org/wiki/{title.replace(' ', '_')}) (CC BY-SA)")
    if isinstance(info.get("image_file"), str):
        sources.append(ui.photo_credit(info["image_file"]))
    sources.append("AI summary of form and interviews (PDC news): coming soon")
    st.caption(" · ".join(sources))


def _titles(player_key: int) -> None:
    st.subheader("🏆 Titles")
    t = data.table("player_titles")
    t = t[t["player_key"] == player_key].sort_values("event_date", ascending=False) if len(t) else t
    if t.empty:
        st.caption("No titles in our data (PDC events since 2021).")
        return

    def line(r) -> str:
        major = " · **Major**" if r.title_group == "Major" else f" · {r.title_group}"
        return f"- {pd.Timestamp(r.event_date):%b %Y} · {r.tournament_name}{major}"

    majors = int((t["title_group"] == "Major").sum())
    st.caption(f"{len(t)} titles since 2021, {majors} of them majors.")
    st.markdown("\n".join(line(r) for r in t.head(5).itertuples()))
    if len(t) > 5:
        with st.expander(f"All {len(t)} titles"):
            st.markdown("\n".join(line(r) for r in t.itertuples()))


def render() -> None:
    st.title("👤 Player Profile")
    pi = data.current_pi()
    if pi.empty:
        st.warning("No Performance Index yet.")
        return
    names = pi.sort_values("rank")["player_name"].tolist()
    wanted = st.session_state.pop("open_player", None)  # set by the leaderboard before switching here
    if wanted in names:
        st.session_state["player"] = wanted
    if st.session_state.get("player") not in names:
        st.session_state["player"] = names[0]
    name = st.selectbox("Player", names, key="player", placeholder="Type a name…")
    row = pi[pi["player_name"] == name].iloc[0]
    info_all = data.players()
    info = info_all[info_all["player_key"] == row["player_key"]]
    info = info.iloc[0] if len(info) else pd.Series(dtype=object)

    _header(name, row, info)
    _breakdown(row)

    st.subheader("PI over time")
    hist = data.table("performance_index")
    st.plotly_chart(_history_chart(hist[hist["player_key"] == row["player_key"]]), width="stretch",
                    config={"displayModeBar": False})
    st.caption("Monthly snapshots, each computed only from matches before that date (with the current model's weights).")

    _recent_form(row, info_all)
    _profile(info)
    _titles(int(row["player_key"]))
