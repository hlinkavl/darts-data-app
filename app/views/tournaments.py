"""Tournament Overview: title chances, the draw round by round, players to watch, upcoming matches, season."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui

STATUS = {"backtest": "✅ Finished", "live": "🔴 In progress", "pre-tournament": "🗓️ Not started"}


def _photos() -> dict[str, str]:
    """name key -> Wikimedia image file, to show photos next to names from the Wikipedia draws."""
    p = data.players()
    if p.empty or "image_file" not in p.columns:
        return {}
    p = p.dropna(subset=["image_file"])
    return {ui.name_key(n): f for n, f in zip(p["player_name"], p["image_file"])}


def _seed(s) -> str:
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s).strip()
    return f"({s})" if s and s.lower() not in ("none", "nan") else ""


def _events(preds: pd.DataFrame) -> list[tuple[str, str]]:
    ev = preds[["wiki_title", "mode"]].drop_duplicates()
    ev["order"] = ev["mode"].map({"live": 0, "pre-tournament": 1, "backtest": 2})
    ev = ev.sort_values(["order", "wiki_title"], ascending=[True, False])
    return list(ev[["wiki_title", "mode"]].itertuples(index=False, name=None))


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


def _match_card(m, photos: dict) -> None:
    """Score and winner first; the model's pre-match probability underneath."""
    played = bool(m.winner)
    win_a, win_b = played and m.winner == m.player_a, played and m.winner == m.player_b

    def side(name, seed, won, align):
        if not name:
            return f"<div style='flex:1;text-align:{align};color:{ui.TEXT_2}'>TBD</div>"
        style = f"font-weight:700;color:{ui.TEXT}" if won else (f"color:{ui.TEXT_2}" if played else f"color:{ui.TEXT}")
        img = ui.avatar(photos.get(ui.name_key(name)))
        tick = " ✓" if won else ""
        label = f"{name} <span style='color:{ui.TEXT_2};font-weight:400'>{_seed(seed)}</span>{tick}"
        inner = f"{label}{img}" if align == "right" else f"{img}{label}"
        return f"<div style='flex:1;text-align:{align};{style}'>{inner}</div>"

    if played:
        centre = "w/o" if m.walkover else f"{ui.num(m.score_a, 0)} – {ui.num(m.score_b, 0)}"
        centre_html = f"<div style='min-width:96px;text-align:center;font-size:1.35em;font-weight:700;color:{ui.TEXT}'>{centre}</div>"
    else:
        centre_html = f"<div style='min-width:96px;text-align:center;color:{ui.TEXT_2}'>vs</div>"
    st.markdown(f"<div style='display:flex;align-items:center;gap:10px'>{side(m.player_a, m.seed_a, win_a, 'right')}"
                f"{centre_html}{side(m.player_b, m.seed_b, win_b, 'left')}</div>", unsafe_allow_html=True)

    notes = []
    if pd.notna(m.p_a):
        notes.append(f"Model before the match: {ui.pct(m.p_a)} – {ui.pct(1 - m.p_a)}")
        if played and not m.walkover and m.winner != (m.player_a if m.p_a >= 0.5 else m.player_b):
            notes.append("⚡ upset")
    if pd.notna(m.avg_a) and pd.notna(m.avg_b):
        notes.append(f"averages {ui.num(m.avg_a, 2)} – {ui.num(m.avg_b, 2)}")
    if notes:
        st.markdown(f"<div style='text-align:center;color:{ui.TEXT_2};font-size:0.85em'>{' · '.join(notes)}</div>",
                    unsafe_allow_html=True)


def _draw_explorer(matches: pd.DataFrame, photos: dict) -> None:
    rounds = matches[["round_order", "round_name", "first_to", "unit"]].drop_duplicates().sort_values("round_order")
    labels = [f"{r.round_name}" + (f" (first to {int(r.first_to)} {r.unit})" if pd.notna(r.first_to) else "")
              for r in rounds.itertuples()]
    choice = st.selectbox("Round", range(len(labels)), index=len(labels) - 1, format_func=lambda i: labels[i], key="draw_round")
    rnd = matches[matches["round_order"] == rounds["round_order"].iloc[choice]].sort_values("slot")
    for m in rnd.itertuples():
        if m.player_a or m.player_b:
            with st.container(border=True):
                _match_card(m, photos)


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
        st.markdown(f"<div style='display:flex;align-items:center;margin:6px 0'>{ui.avatar(photos.get(ui.name_key(r.player_name)), 40)}"
                    f"<div><b>{r.player_name}</b> <span style='color:{ui.TEXT_2}'>{seed_txt}</span><br>"
                    f"<span style='font-size:1.2em'>{ui.pct(r.p_reach)}</span> <span style='color:{ui.TEXT_2}'>to reach the last 8</span>"
                    f"</div></div>", unsafe_allow_html=True)
    st.caption("Dark horses: unseeded or seeded below 8, ranked by their chance to reach the last 8. Model only.")


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
                st.markdown(f"{ui.avatar(photos.get(ui.name_key(m.player_a_name)), 40)}**{m.player_a_name}**", unsafe_allow_html=True)
                a1, a2 = st.columns(2)
                a1.metric("PI", ui.num(m.pi_a, 2), help=ui.PI_HELP)
                a2.metric("Effective Average", ui.num(m.effective_average_a), help=ui.EFFECTIVE_AVERAGE_HELP)
            with c2:
                st.progress(float(m.p_a), text=f"{ui.pct(m.p_a)} – {ui.pct(1 - m.p_a)}")
                st.caption(f"Head-to-head {int(m.h2h_wins_a)}–{int(m.h2h_wins_b)} · typical match (first to 6 legs)")
            with c3:
                st.markdown(f"<div style='text-align:right'><b>{m.player_b_name}</b>{ui.avatar(photos.get(ui.name_key(m.player_b_name)), 40)}</div>",
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
    icon = {"completed": "✅ completed", "in progress": "🔴 in progress", "upcoming": "🗓️ upcoming", "date unknown": "❔ date unknown"}
    rows["Status"] = rows["status"].map(icon)
    rows["Dates"] = [f"{pd.Timestamp(s):%d %b} – {pd.Timestamp(e):%d %b %Y}" if pd.notna(s) and pd.notna(e)
                     else (f"{pd.Timestamp(e):%d %b %Y}" if pd.notna(e) else "–") for s, e in zip(rows.start_date, rows.end_date)]
    rows["Winner"] = [f"{w} ({ui.num(a, 2)})" if w and pd.notna(a) else (w or "–") for w, a in zip(rows.winner_name, rows.winner_avg)]
    rows["Predictions"] = rows["has_draw"].map({True: "✓ draw available", False: ""})
    st.dataframe(rows[["tournament_name", "Dates", "Status", "Winner", "Predictions"]].rename(columns={"tournament_name": "Major"}),
                 hide_index=True, width="stretch")


def _status_banner(title: str, mode: str, cal: pd.DataFrame) -> None:
    if mode == "backtest":
        bts = data.table("tournament_backtest_summary")
        b = bts[(bts["wiki_title"] == title) & (bts["metric_set"] == "model, round format")]
        if len(b):
            b = b.iloc[0]
            st.success(f"**✅ Finished · Champion: {b.champion}.** Before the event the model gave him "
                       f"{ui.pct(b.champion_p_title, 1)} (#{int(b.champion_rank_by_p_title)} in its ranking); the pre-match "
                       f"favourite won {ui.num(b.favourite_won_pct, 0)} % of {int(b.matches)} matches. Everything below is "
                       "what the model predicted before the first match (strengths as of the first day).")
    elif mode == "live":
        st.error("**🔴 In progress.** Matches already played are fixed; the rest of the draw is simulated again after every refresh.")
    else:
        row = cal[cal["wiki_title"] == title]
        when = f" · starts {pd.Timestamp(row['start_date'].iloc[0]):%d %b %Y}" if len(row) and pd.notna(row["start_date"].iloc[0]) else ""
        st.info(f"**🗓️ Not started{when}.** Predictions from the players' current form.")


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

    tab_pred, tab_up, tab_season = st.tabs(["Predictions", "Upcoming matches", "Season calendar"])
    with tab_pred:
        if preds.empty:
            st.info("No draw available yet.")
        else:
            events = _events(preds)
            i = st.selectbox("Tournament", range(len(events)), key="event",
                             format_func=lambda k: f"{STATUS.get(events[k][1], '')} · {events[k][0]}")
            title, mode = events[i]
            ev = preds[(preds["wiki_title"] == title) & (preds["mode"] == mode)]
            _status_banner(title, mode, cal)
            photos = _photos()
            left, right = st.columns([3, 2])
            with left:
                st.subheader("Chance to win the title")
                st.plotly_chart(_title_chart(ev[ev["round_name"] == "Winner"]), width="stretch", config={"displayModeBar": False})
            with right:
                st.subheader("Players to watch")
                _players_to_watch(ev, photos)
            st.subheader("The draw")
            dm = data.table("tournament_draw_matches")
            _draw_explorer(dm[(dm["wiki_title"] == title) & (dm["mode"] == mode)], photos)
            st.caption("Probabilities use each round's format (legs or sets); see Methodology.")
            with st.expander("Round by round: every player's chance to reach each round"):
                _round_table(ev)
    with tab_up:
        _upcoming(data.table("upcoming_matches"))
    with tab_season:
        _season(cal)
