"""Tournament Overview: title chances, the draw as a bracket, match details, players to watch, season, upcoming."""

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui

BRACKET_ROUNDS = 4  # last 16 to the final
MODE_ORDER = {"live": 0, "pre-tournament": 1, "backtest": 2}


def _photos() -> dict[str, str]:
    """name key -> Wikimedia image file, to show photos next to names from the Wikipedia draws."""
    p = data.players()
    if p.empty or "image_file" not in p.columns:
        return {}
    p = p.dropna(subset=["image_file"])
    return {ui.name_key(n): f for n, f in zip(p["player_name"], p["image_file"])}


def _avatar(photos: dict, name, size: int = 34) -> str:
    return ui.avatar(photos.get(ui.name_key(name)), size, name=name)


def _seed(s) -> str:
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s).strip()
    return f"({s})" if s and s.lower() not in ("none", "nan") else ""


def _date(d, fmt: str = "%d %b %Y") -> str:
    return f"{pd.Timestamp(d):{fmt}}" if d is not None and pd.notna(d) else "–"


def _short_title(title: str) -> str:
    return title.replace(" (darts)", "")


# --------------------------------------------------------------------------------------- tournament picker

def _events(preds: pd.DataFrame, cal: pd.DataFrame) -> list[dict]:
    """One entry per (tournament, mode) with a label: final date and champion for finished events."""
    cal = cal.drop_duplicates("wiki_title").set_index("wiki_title") if len(cal) else pd.DataFrame()
    out = []
    for title, mode in preds[["wiki_title", "mode"]].drop_duplicates().itertuples(index=False, name=None):
        row = cal.loc[title] if title in cal.index else None
        start, end = (row["start_date"], row["end_date"]) if row is not None else (None, None)
        if mode == "backtest":
            winner = row["winner_name"] if row is not None and isinstance(row["winner_name"], str) else None
            label = f"{_short_title(title)}" + (f" ({winner})" if winner else "") + f" · {_date(end, '%b %Y')}"
        elif mode == "live":
            label = f"🔴 {_short_title(title)} · in progress"
        else:
            label = f"🗓️ {_short_title(title)} · starts {_date(start)}"
        newest_first = -pd.Timestamp(end).value if end is not None and pd.notna(end) else 0
        out.append({"title": title, "mode": mode, "label": label, "start": start, "end": end,
                    "sort": (MODE_ORDER.get(mode, 3), newest_first)})
    return sorted(out, key=lambda e: e["sort"])


def _status_block(ev: dict, preds: pd.DataFrame, draw: pd.DataFrame, cal: pd.DataFrame) -> None:
    title, mode = ev["title"], ev["mode"]
    dates = (f"{_date(ev['start'], '%d %b')} – {_date(ev['end'])}" if ev["start"] is not None and pd.notna(ev["start"])
             else _date(ev["end"]))
    fav = preds[preds["round_name"] == "Winner"].nlargest(1, "p_reach")
    favourite = f"{fav['player_name'].iloc[0]} · {ui.pct(fav['p_reach'].iloc[0], 1)}" if len(fav) else "–"
    if mode == "backtest":
        rows = [("Status", "✅ Finished"), ("Final", _date(ev["end"]))]
        note = "Everything below is what the model predicted before the first match (strengths as of the first day)."
        cal_row = cal[cal["wiki_title"] == title]
        bts = data.table("tournament_backtest_summary")
        b = bts[(bts["wiki_title"] == title) & (bts["metric_set"] == "model, round format")]
        if len(b):
            b = b.iloc[0]
            avg = cal_row["winner_avg"].iloc[0] if len(cal_row) else None
            rows += [("Champion", f"🏆 {b.champion}" + (f" · avg {ui.num(avg, 2)}" if avg is not None and pd.notna(avg) else "")),
                     ("Champion's chance before the event",
                      f"{ui.pct(b.champion_p_title, 1)} · #{int(b.champion_rank_by_p_title)} in the model's ranking"),
                     ("Pre-match favourite won", f"{ui.num(b.favourite_won_pct, 0)} % of {int(b.matches)} matches")]
    elif mode == "live":
        known = draw[draw["player_a"].astype(bool) & draw["player_b"].astype(bool)]
        played = int(known["winner"].astype(bool).sum())
        rows = [("Status", "🔴 In progress"), ("Dates", dates), ("Matches played", f"{played} of {len(known)} drawn"),
                ("Title favourite now", favourite)]
        note = "Played matches are fixed; the rest of the draw is simulated again after every refresh."
    else:
        rows = [("Status", "🗓️ Not started"), ("Dates", dates), ("Players", f"{preds['player_name'].nunique()}"),
                ("Title favourite", favourite)]
        note = "Predictions from the players' current form."
    st.markdown(ui.info_block(rows, note), unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------- predictions

def _title_chart(winners: pd.DataFrame) -> go.Figure:
    top = winners.nlargest(16, "p_reach").sort_values("p_reach")
    fig = go.Figure(go.Bar(
        x=top["p_reach"], y=top["player_name"], orientation="h", marker=dict(color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        text=[ui.pct(v, 1) for v in top["p_reach"]], textposition="outside", textfont=dict(color=ui.TEXT_2),
        hovertemplate="%{y}: %{x:.1%} to win the title<extra></extra>", cliponaxis=False))
    return ui.layout(fig, height=60 + 28 * len(top), xaxis=dict(tickformat=".0%", title="chance to win the title"))


def _round_table(preds: pd.DataFrame) -> None:
    rounds = preds[["round_order", "round_name"]].drop_duplicates().sort_values("round_order")
    preds = preds.assign(seed=preds["seed"].map(lambda s: _seed(s).strip("()")))
    wide = preds.pivot_table(index=["player_name", "seed", "source"], columns="round_order", values="p_reach").reset_index()
    labels = {r.round_order: ("Title" if r.round_name == "Winner" else f"Reach {r.round_name}") for r in rounds.itertuples()}
    first = rounds["round_order"].min()
    wide = wide.drop(columns=[first]).rename(columns=labels).sort_values(labels[rounds["round_order"].max()], ascending=False)
    cols = [labels[o] for o in rounds["round_order"] if o != first]
    st.dataframe(
        wide[["player_name", "seed"] + cols + ["source"]], hide_index=True, width="stretch", height=420,
        column_config={"player_name": "Player", "seed": "Seed",
                       "source": st.column_config.TextColumn("Strength from", help="pi_model = Performance Index; "
                                                             "elo_estimate = untracked player, estimated from Elo; fallback = no data"),
                       **{c: st.column_config.ProgressColumn(c, min_value=0.0, max_value=1.0, format="percent") for c in cols}})


def _players_to_watch(preds: pd.DataFrame, photos: dict) -> None:
    """Model only (no odds): unseeded or lower-seeded players with the best chance to go deep."""
    rounds = preds[["round_order", "round_name"]].drop_duplicates().sort_values("round_order")
    qf = rounds[rounds["round_name"].str.contains("Quarter", case=False)]
    target = qf["round_order"].iloc[0] if len(qf) else rounds["round_order"].iloc[-3]
    deep = preds[preds["round_order"] == target].copy()
    seed = pd.to_numeric(deep["seed"].map(lambda s: _seed(s).strip("()")), errors="coerce")
    deep = deep[seed.isna() | (seed > 8)].nlargest(3, "p_reach")
    for r in deep.itertuples():
        seed_txt = _seed(r.seed) or "unseeded"
        st.markdown(f"<div style='display:flex;align-items:center;margin:6px 0'>{_avatar(photos, r.player_name, 40)}"
                    f"<div><b>{escape(r.player_name)}</b> <span style='color:{ui.TEXT_2}'>{seed_txt}</span><br>"
                    f"<span style='font-size:1.2em'>{ui.pct(r.p_reach)}</span> <span style='color:{ui.TEXT_2}'>to reach the last 8</span>"
                    f"</div></div>", unsafe_allow_html=True)
    st.caption("Dark horses: unseeded or seeded below 8, ranked by their chance to reach the last 8. Model only.")


# ----------------------------------------------------------------------------------------------- bracket

def _format(m) -> str:
    return f"first to {int(m.first_to)} {m.unit}" if pd.notna(m.first_to) else ""


def _bracket_box(m, short: dict) -> str:
    """One match: surname, the model's pre-match chance (small) and the score; the winner's row in green."""
    if m is None:
        rows, tip = [("TBD", "", "", False, False)] * 2, "Not drawn yet"
    else:
        played = bool(m.winner)
        rows = []
        for name, score, p in ((m.player_a, m.score_a, m.p_a), (m.player_b, m.score_b, 1 - m.p_a)):
            won = played and name == m.winner
            score_txt = ("w/o" if won else "") if m.walkover else (ui.num(score, 0) if played else "")
            p_txt = ui.pct(p) if name and pd.notna(p) else ""
            rows.append((short.get(name, "TBD") if name else "TBD", p_txt, score_txt, won, played))
        tip = " · ".join(t for t in (
            f"{m.player_a or 'TBD'} {_seed(m.seed_a)} vs {m.player_b or 'TBD'} {_seed(m.seed_b)}",
            _format(m),
            f"model before the match {ui.pct(m.p_a)} – {ui.pct(1 - m.p_a)}" if pd.notna(m.p_a) else "",
            f"averages {ui.num(m.avg_a, 2)} – {ui.num(m.avg_b, 2)}" if pd.notna(m.avg_a) and pd.notna(m.avg_b) else "") if t)
    html = ""
    for i, (name, p, score, won, played) in enumerate(rows):
        style = (f"background:rgba(12,163,12,.16);border-left:3px solid {ui.WIN};color:{ui.TEXT};font-weight:700" if won
                 else f"border-left:3px solid transparent;color:{ui.TEXT_2 if played or name == 'TBD' else ui.TEXT}")
        sep = f"border-top:1px solid {ui.GRID};" if i else ""
        html += (f"<div style='display:flex;align-items:center;gap:6px;padding:4px 8px;{sep}{style}'>"
                 f"<span style='flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{escape(name)}</span>"
                 f"<span style='font-size:0.75em;color:{ui.TEXT_2};font-weight:400'>{p}</span>"
                 f"<span style='min-width:22px;text-align:right'>{score}</span></div>")
    return (f"<div title='{escape(tip)}' style='border:1px solid {ui.GRID};border-radius:6px;background:#222220;"
            f"font-size:0.88em;margin:5px 0;overflow:hidden'>{html}</div>")


def _bracket(matches: pd.DataFrame) -> None:
    """The last rounds as a bracket: a match in slot i feeds slot i // 2 of the next round."""
    orders = sorted(matches["round_order"].unique())[-BRACKET_ROUNDS:]
    short = ui.surnames(pd.concat([matches["player_a"], matches["player_b"]]))
    height = 2 ** (len(orders) - 1) * 66
    cols = []
    for k, order in enumerate(orders):
        rnd = matches[matches["round_order"] == order].drop_duplicates("slot").set_index("slot")
        boxes = "".join(_bracket_box(rnd.loc[i] if i in rnd.index else None, short) for i in range(2 ** (len(orders) - 1 - k)))
        cols.append(f"<div style='flex:1;min-width:165px;display:flex;flex-direction:column'>"
                    f"<div style='text-align:center;color:{ui.TEXT_2};font-size:0.8em;margin-bottom:4px'>"
                    f"{escape(rnd['round_name'].iloc[0])}</div>"
                    f"<div style='height:{height}px;display:flex;flex-direction:column;justify-content:space-around'>{boxes}</div></div>")
    final = matches[matches["round_order"] == orders[-1]]
    champion = final["winner"].iloc[0] if len(final) and final["winner"].iloc[0] else None
    if champion:
        cols.append(f"<div style='min-width:110px;display:flex;flex-direction:column'>"
                    f"<div style='text-align:center;color:{ui.TEXT_2};font-size:0.8em;margin-bottom:4px'>Champion</div>"
                    f"<div style='height:{height}px;display:flex;align-items:center;justify-content:center;"
                    f"font-weight:700;color:{ui.TEXT}'>🏆 {escape(short.get(champion, champion))}</div></div>")
    st.markdown(f"<div style='display:flex;gap:14px;overflow-x:auto;padding-bottom:6px'>{''.join(cols)}</div>",
                unsafe_allow_html=True)
    st.caption("Green = winner. The small % is the model's chance before the match. Hover over a match for full names, "
               "format and averages; every round with details is below.")


def _match_card(m, photos: dict) -> str:
    """Score and winner first; the model's pre-match chance as a bar; averages small."""
    played = bool(m.winner)

    def side(name, seed, align):
        if not name:
            return f"<div style='flex:1;text-align:{align};color:{ui.TEXT_2}'>TBD</div>"
        won = played and name == m.winner
        color = ui.WIN if won else (ui.TEXT_2 if played else ui.TEXT)
        label = (f"<span style='color:{color};font-weight:{700 if won else 400}'>{escape(name)}{' ✓' if won else ''}</span>"
                 f" <span style='color:{ui.TEXT_2}'>{_seed(seed)}</span>")
        img = _avatar(photos, name, 36)
        inner = f"{label}{img}" if align == "right" else f"{img}{label}"
        return f"<div style='flex:1;text-align:{align}'>{inner}</div>"

    centre = ("w/o" if m.walkover else f"{ui.num(m.score_a, 0)} – {ui.num(m.score_b, 0)}") if played else "vs"
    centre_style = f"font-size:1.35em;font-weight:700;color:{ui.TEXT}" if played else f"color:{ui.TEXT_2}"
    html = (f"<div style='display:flex;align-items:center;gap:10px'>{side(m.player_a, m.seed_a, 'right')}"
            f"<div style='min-width:90px;text-align:center;{centre_style}'>{centre}</div>{side(m.player_b, m.seed_b, 'left')}</div>")
    if pd.notna(m.p_a):
        upset = played and not m.walkover and m.winner != (m.player_a if m.p_a >= 0.5 else m.player_b)
        html += (f"<div style='max-width:460px;margin:10px auto 0'>"
                 f"<div style='display:flex;justify-content:space-between;align-items:baseline;font-weight:700;color:{ui.TEXT}'>"
                 f"<span>{ui.pct(m.p_a)}</span><span style='font-weight:400;color:{ui.TEXT_2};font-size:0.82em'>"
                 f"model before the match{' · ⚡ upset' if upset else ''}</span><span>{ui.pct(1 - m.p_a)}</span></div>"
                 f"<div style='display:flex;height:8px;border-radius:4px;overflow:hidden;gap:2px;margin-top:3px'>"
                 f"<div style='width:{round(100 * m.p_a)}%;background:{ui.SERIES[0]}'></div>"
                 f"<div style='flex:1;background:{ui.SERIES[1]}'></div></div></div>")
    if pd.notna(m.avg_a) and pd.notna(m.avg_b):
        html += (f"<div style='text-align:center;color:{ui.TEXT_2};font-size:0.8em;margin-top:6px'>"
                 f"averages {ui.num(m.avg_a, 2)} – {ui.num(m.avg_b, 2)}</div>")
    return f"<div style='border:1px solid {ui.GRID};border-radius:10px;padding:12px 14px;margin:8px 0'>{html}</div>"


def _match_details(matches: pd.DataFrame, photos: dict) -> None:
    """Rounds from the final backwards: the latest rounds first, the early rounds one click away."""
    rounds = (matches[["round_order", "round_name", "first_to", "unit"]].drop_duplicates("round_order")
              .sort_values("round_order", ascending=False))
    labels = [r.round_name + (f" · first to {int(r.first_to)} {r.unit}" if pd.notna(r.first_to) else "") for r in rounds.itertuples()]
    choice = st.selectbox("Round", range(len(labels)), index=0, format_func=lambda i: labels[i], key="draw_round")
    rnd = matches[matches["round_order"] == rounds["round_order"].iloc[choice]].sort_values("slot")
    st.markdown("".join(_match_card(m, photos) for m in rnd.itertuples() if m.player_a or m.player_b), unsafe_allow_html=True)


# ------------------------------------------------------------------------------------- upcoming, season

def _upcoming(up: pd.DataFrame) -> None:
    if up.empty:
        st.info("No scheduled matches right now. They appear here as soon as a draw or order of play is published.")
        return
    photos = _photos()
    for m in up.sort_values("start_time").itertuples():
        with st.container(border=True):
            st.caption(f"{m.event_title} · {m.round_name} · {pd.Timestamp(m.start_time):%a %d %b %H:%M}")
            c1, c2, c3 = st.columns([4, 4, 4])
            with c1:
                st.markdown(f"{_avatar(photos, m.player_a_name, 40)}**{m.player_a_name}**", unsafe_allow_html=True)
                a1, a2 = st.columns(2)
                a1.metric("PI", ui.num(m.pi_a, 2), help=ui.PI_HELP)
                a2.metric("Effective Average", ui.num(m.effective_average_a), help=ui.EFFECTIVE_AVERAGE_HELP)
            with c2:
                st.progress(float(m.p_a), text=f"{ui.pct(m.p_a)} – {ui.pct(1 - m.p_a)}")
                st.caption(f"Head-to-head {int(m.h2h_wins_a)}–{int(m.h2h_wins_b)} · typical match (first to 6 legs)")
            with c3:
                st.markdown(f"<div style='text-align:right'><b>{escape(m.player_b_name)}</b>{_avatar(photos, m.player_b_name, 40)}</div>",
                            unsafe_allow_html=True)
                b1, b2 = st.columns(2)
                b1.metric("PI", ui.num(m.pi_b, 2), help=ui.PI_HELP)
                b2.metric("Effective Average", ui.num(m.effective_average_b), help=ui.EFFECTIVE_AVERAGE_HELP)


def _season(cal: pd.DataFrame) -> None:
    if cal.empty:
        st.info("No calendar yet.")
        return
    seasons = sorted(cal["season"].dropna().unique(), reverse=True)
    season = st.selectbox("Season", seasons, index=0, key="season")
    rows = cal[cal["season"] == season].copy()
    # Upcoming first, then newest to oldest; events without dates yet go to the top.
    rows["_when"] = pd.to_datetime(rows["start_date"]).fillna(pd.to_datetime(rows["end_date"]))
    rows = rows.sort_values("_when", ascending=False, na_position="first")
    icon = {"completed": "✅ completed", "in progress": "🔴 in progress", "upcoming": "🗓️ upcoming", "date unknown": "❔ date unknown"}
    rows["Status"] = rows["status"].map(icon)
    rows["Dates"] = [f"{pd.Timestamp(s):%d %b} – {pd.Timestamp(e):%d %b %Y}" if pd.notna(s) and pd.notna(e)
                     else (f"{pd.Timestamp(e):%d %b %Y}" if pd.notna(e) else "–") for s, e in zip(rows.start_date, rows.end_date)]
    rows["Winner"] = [f"{w} ({ui.num(a, 2)})" if w and pd.notna(a) else (w or "–") for w, a in zip(rows.winner_name, rows.winner_avg)]
    rows["Predictions"] = rows["has_draw"].map({True: "✓ draw available", False: ""})
    st.dataframe(rows[["tournament_name", "Dates", "Status", "Winner", "Predictions"]].rename(columns={"tournament_name": "Major"}),
                 hide_index=True, width="stretch")


def render() -> None:
    st.title("🏆 Tournament Overview")
    cal, preds = data.table("majors_calendar"), data.table("tournament_predictions")
    if len(cal):
        nxt = cal[cal["status"].isin(["in progress", "upcoming"])].sort_values("start_date").head(1)
        if len(nxt):
            n = nxt.iloc[0]
            when = f"{pd.Timestamp(n.start_date):%d %b} – {pd.Timestamp(n.end_date):%d %b %Y}" if pd.notna(n.start_date) else "dates to be confirmed"
            st.caption(f"{'🔴 Now' if n.status == 'in progress' else '🗓️ Next major'}: **{n.tournament_name}** · {when}"
                       + ("" if n.has_draw else " · predictions appear once the draw is published"))

    tab_pred, tab_season, tab_up = st.tabs(["Predictions", "Season calendar", "Upcoming matches"])
    with tab_pred:
        if preds.empty:
            st.info("No draw available yet.")
        else:
            events = _events(preds, cal)
            i = st.selectbox("Tournament", range(len(events)), key="event", format_func=lambda k: events[k]["label"])
            ev = events[i]
            pr = preds[(preds["wiki_title"] == ev["title"]) & (preds["mode"] == ev["mode"])]
            dm = data.table("tournament_draw_matches")
            draw = dm[(dm["wiki_title"] == ev["title"]) & (dm["mode"] == ev["mode"])]
            _status_block(ev, pr, draw, cal)
            photos = _photos()
            left, right = st.columns([3, 2])
            with left:
                st.subheader("Chance to win the title")
                st.plotly_chart(_title_chart(pr[pr["round_name"] == "Winner"]), width="stretch", config={"displayModeBar": False})
            with right:
                st.subheader("Players to watch")
                _players_to_watch(pr, photos)
            st.subheader("The draw")
            if draw.empty:
                st.info("The draw is not published yet.")
            else:
                _bracket(draw)
                st.subheader("Match details")
                _match_details(draw, photos)
                st.caption("Probabilities use each round's format (legs or sets); see Methodology.")
            with st.expander("Round by round: every player's chance to reach each round"):
                _round_table(pr)
    with tab_season:
        _season(cal)
    with tab_up:
        _upcoming(data.table("upcoming_matches"))
