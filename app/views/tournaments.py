"""Tournament Overview: title chances, the draw round by round, players to watch, upcoming matches, season."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui

MODE_LABEL = {"live": "🔴 live", "pre-tournament": "pre-tournament", "backtest": "backtest (what the model predicted before the event)"}


def _events(preds: pd.DataFrame) -> list[tuple[str, str]]:
    ev = preds[["wiki_title", "mode", "edition"]].drop_duplicates()
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


def _draw_explorer(matches: pd.DataFrame) -> None:
    rounds = matches[["round_order", "round_name", "first_to", "unit"]].drop_duplicates().sort_values("round_order")
    labels = [f"{r.round_name}" + (f" (first to {int(r.first_to)} {r.unit})" if pd.notna(r.first_to) else "")
              for r in rounds.itertuples()]
    choice = st.selectbox("Round", range(len(labels)), format_func=lambda i: labels[i], key="draw_round")
    rnd = matches[matches["round_order"] == rounds["round_order"].iloc[choice]].sort_values("slot")
    for m in rnd.itertuples():
        if not m.player_a and not m.player_b:
            continue
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 4, 5])
            seed = lambda s: f"({s}) " if s and s not in ("None", "nan") else ""
            win_a, win_b = m.winner == m.player_a, m.winner == m.player_b
            c1.markdown(f"{'**' if win_a else ''}{seed(m.seed_a)}{m.player_a or 'TBD'}{'**' if win_a else ''}")
            c3.markdown(f"<div style='text-align:right'>{'**' if win_b else ''}{m.player_b or 'TBD'} {seed(m.seed_b)}{'**' if win_b else ''}</div>",
                        unsafe_allow_html=True)
            if pd.notna(m.p_a):
                c2.progress(float(m.p_a), text=f"{ui.pct(m.p_a)} – {ui.pct(1 - m.p_a)}")
            if m.winner:
                fav = m.player_a if (m.p_a or 0) >= 0.5 else m.player_b
                upset = " · ⚡ upset" if pd.notna(m.p_a) and m.winner != fav else ""
                score = "walkover" if m.walkover else f"{ui.num(m.score_a, 0)}–{ui.num(m.score_b, 0)}"
                avgs = f" · averages {ui.num(m.avg_a, 2)} / {ui.num(m.avg_b, 2)}" if pd.notna(m.avg_a) else ""
                c2.caption(f"{score}{avgs}{upset}")


def _players_to_watch(preds: pd.DataFrame) -> None:
    """Model only (no odds): unseeded or lower-seeded players with the best chance to go deep."""
    rounds = preds[["round_order", "round_name"]].drop_duplicates().sort_values("round_order")
    qf = rounds[rounds["round_name"].str.contains("Quarter", case=False)]
    target = qf["round_order"].iloc[0] if len(qf) else rounds["round_order"].iloc[-3]
    deep = preds[preds["round_order"] == target].copy()
    seed = pd.to_numeric(deep["seed"], errors="coerce")
    deep = deep[seed.isna() | (seed > 8)].nlargest(3, "p_reach")
    cols = st.columns(3)
    for col, r in zip(cols, deep.itertuples()):
        col.metric(r.player_name, ui.pct(r.p_reach), help=f"Chance to reach the {qf['round_name'].iloc[0] if len(qf) else 'last 8'}"
                   f" ({'unseeded' if pd.isna(pd.to_numeric(r.seed, errors='coerce')) else 'seed ' + str(r.seed)})")
    st.caption("Dark horses: unseeded or seeded below 8, ranked by their chance to reach the last 8. Based on the model only.")


def _upcoming(up: pd.DataFrame) -> None:
    if up.empty:
        st.info("No scheduled matches right now. They appear here as soon as a draw or order of play is published.")
        return
    for m in up.sort_values("start_time").itertuples():
        with st.container(border=True):
            st.caption(f"{m.event_title} · {m.round_name} · {pd.Timestamp(m.start_time):%a %d %b %H:%M}")
            c1, c2, c3 = st.columns([4, 4, 4])
            c1.markdown(f"**{m.player_a_name}**  \nPI {ui.num(m.pi_a, 2)} · eff. avg {ui.num(m.effective_average_a)}")
            c2.progress(float(m.p_a), text=f"{ui.pct(m.p_a)} – {ui.pct(1 - m.p_a)}")
            c2.caption(f"Head-to-head {int(m.h2h_wins_a)}–{int(m.h2h_wins_b)} · typical match (first to 6 legs)")
            c3.markdown(f"<div style='text-align:right'><b>{m.player_b_name}</b><br>PI {ui.num(m.pi_b, 2)} · eff. avg "
                        f"{ui.num(m.effective_average_b)}</div>", unsafe_allow_html=True)


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


def render() -> None:
    st.title("🏆 Tournament Overview")
    cal, preds = data.table("majors_calendar"), data.table("tournament_predictions")
    if len(cal):
        nxt = cal[cal["status"].isin(["in progress", "upcoming"])].sort_values("start_date").head(1)
        if len(nxt):
            n = nxt.iloc[0]
            when = f"{pd.Timestamp(n.start_date):%d %b} – {pd.Timestamp(n.end_date):%d %b %Y}" if pd.notna(n.start_date) else "dates to be confirmed"
            st.info(f"**{'Now' if n.status == 'in progress' else 'Next major'}: {n.tournament_name}** · {when}"
                    + ("" if n.has_draw else " · predictions appear once the draw is published"))

    tab_pred, tab_up, tab_season = st.tabs(["Predictions", "Upcoming matches", "Season calendar"])
    with tab_pred:
        if preds.empty:
            st.info("No draw available yet.")
        else:
            events = _events(preds)
            i = st.selectbox("Tournament", range(len(events)), key="event",
                             format_func=lambda k: f"{events[k][0]} · {MODE_LABEL.get(events[k][1], events[k][1])}")
            title, mode = events[i]
            ev = preds[(preds["wiki_title"] == title) & (preds["mode"] == mode)]
            winners = ev[ev["round_name"] == "Winner"]
            if mode == "backtest":
                bts = data.table("tournament_backtest_summary")
                b = bts[(bts["wiki_title"] == title) & (bts["metric_set"] == "model, round format")]
                if len(b):
                    b = b.iloc[0]
                    st.caption(f"Backtest: strengths as of the first day, weights fitted on earlier matches only. "
                               f"Champion **{b.champion}** had {ui.pct(b.champion_p_title, 1)} before the event "
                               f"(#{int(b.champion_rank_by_p_title)} in the model). The pre-match favourite won "
                               f"{ui.num(b.favourite_won_pct, 0)} % of {int(b.matches)} matches.")
            left, right = st.columns([3, 2])
            with left:
                st.subheader("Chance to win the title")
                st.plotly_chart(_title_chart(winners), width="stretch", config={"displayModeBar": False})
            with right:
                st.subheader("Players to watch")
                _players_to_watch(ev)
            st.subheader("Round by round")
            _round_table(ev)
            st.subheader("The draw")
            dm = data.table("tournament_draw_matches")
            _draw_explorer(dm[(dm["wiki_title"] == title) & (dm["mode"] == mode)])
            st.caption("Probabilities use each round's format (legs or sets); see Methodology.")
    with tab_up:
        _upcoming(data.table("upcoming_matches"))
    with tab_season:
        _season(cal)
