"""PI Leaderboard and head-to-head calculator."""

import math

import pandas as pd
import streamlit as st

import data
import ui

# Ranking choice -> (first column = sort key, second column shown next to the name)
ORDERS = {"PDC Order of Merit": ("oom", "rank"), "Performance Index": ("rank", "oom")}
FORMATS = {"Typical match (first to 6 legs)": (6, "legs")} | {f"First to {n} legs": (n, "legs") for n in (3, 4, 5, 7, 8, 10, 11, 16, 18)} \
    | {f"First to {n} sets": (n, "sets") for n in (2, 3, 4, 5, 6, 7)}


def render() -> None:
    st.title("📊 PI Leaderboard")
    pi = data.current_pi()
    if pi.empty:
        st.warning("No Performance Index yet.")
        return
    hist = data.table("performance_index")
    snapshots = sorted(pd.to_datetime(hist["as_of_date"]).unique())
    prev = hist[pd.to_datetime(hist["as_of_date"]) == snapshots[-2]] if len(snapshots) > 1 else pd.DataFrame(columns=["player_key", "pi"])
    board = pi.merge(prev[["player_key", "pi"]].rename(columns={"pi": "pi_prev"}), on="player_key", how="left")
    board["change"] = board["pi"] - board["pi_prev"]
    official = data.players()[["player_key", "prize_money_rank"]].drop_duplicates("player_key")
    board = board.merge(official, on="player_key", how="left")
    # Current official rank; the model's own Order of Merit input only where the official one is missing.
    model_oom = board["oom_rank"].map(lambda v: round(math.exp(-v)) if pd.notna(v) and math.exp(-v) < 500 else None)
    board["oom"] = board["prize_money_rank"].fillna(model_oom)

    names = pi["player_name"].tolist()
    order = st.segmented_control("Rank by", list(ORDERS), default=next(iter(ORDERS)), key="lb_order") or next(iter(ORDERS))
    find, go_to = st.columns([4, 1], vertical_alignment="bottom")
    pick = find.selectbox("Find a player", sorted(names), index=None, placeholder="Start typing a name…", key="lb_find")
    if pick:
        board = board[board["player_name"] == pick]
        if go_to.button("Open profile →", width="stretch"):
            st.session_state["player"] = pick
            st.switch_page(st.session_state["pages"]["player"])
    first, second = ORDERS[order]
    board = board.sort_values([first, second], na_position="last")
    st.dataframe(
        board[[first, "player_name", second, "pi", "change", "effective_average", "avg_l30", "form", "elo"]],
        hide_index=True, width="stretch", height=520,
        column_config={
            "oom": st.column_config.NumberColumn("PDC OoM #", format="%d", help="Current official PDC Order of Merit (2-year prize money)"),
            "rank": st.column_config.NumberColumn("PI #", format="%d", help="Position by Performance Index"),
            "player_name": "Player",
            "change": st.column_config.NumberColumn("PI vs last month", format="%+.2f"),
            "pi": st.column_config.ProgressColumn("PI", min_value=0.0, max_value=10.0, format="%.2f", help=ui.PI_HELP),
            "effective_average": st.column_config.NumberColumn("Effective Average", format="%.1f", help=ui.EFFECTIVE_AVERAGE_HELP),
            "avg_l30": st.column_config.NumberColumn("3-Dart Avg (L30)", format="%.2f"),
            "form": st.column_config.NumberColumn("Form", format="%+.2f"),
            "elo": st.column_config.NumberColumn("Elo", format="%.0f")})
    top = pi.sort_values("rank")["pi"].tolist()
    if len(top) >= 20:
        st.caption(f"A gap in PI is a head-to-head chance: #1 vs #2 ({top[0]:.2f} vs {top[1]:.2f}) is "
                   f"{ui.pct(ui.head_to_head(top[0], top[1]))} in a typical match, #1 vs #20 ({top[19]:.2f}) "
                   f"{ui.pct(ui.head_to_head(top[0], top[19]))}. The scale stretches towards 0 and 10, so the same gap "
                   "means more at the top than around 5. Try any pair below.")

    st.subheader("Head to head")
    c1, c2, c3 = st.columns([3, 3, 3])
    a = c1.selectbox("Player A", names, index=0, key="h2h_a")
    b = c2.selectbox("Player B", names, index=min(1, len(names) - 1), key="h2h_b")
    fmt = c3.selectbox("Format", list(FORMATS), key="h2h_format")
    ra, rb = pi[pi["player_name"] == a].iloc[0], pi[pi["player_name"] == b].iloc[0]
    first_to, unit = FORMATS[fmt]
    official_rank = dict(zip(official["player_key"], official["prize_money_rank"]))

    def _oom(r) -> str:
        rank = official_rank.get(r["player_key"])
        return f"#{int(rank)}" if rank is not None and pd.notna(rank) else ui.oom_rank(r["oom_rank"])

    p = ui.match_probability(ui.head_to_head(ra["pi"], rb["pi"]), first_to, unit)
    st.progress(p, text=f"**{a}** {ui.pct(p, 1)}  ·  {ui.pct(1 - p, 1)} **{b}**")
    comp = pd.DataFrame({
        "": ["PI", "Effective Average", "3-Dart Average (L30)", "Form", "Elo", "Order of Merit"],
        a: [ui.num(ra["pi"], 2), ui.num(ra["effective_average"]), ui.num(ra["avg_l30"], 2), f"{ra['form']:+.2f}",
            ui.num(ra["elo"], 0), _oom(ra)],
        b: [ui.num(rb["pi"], 2), ui.num(rb["effective_average"]), ui.num(rb["avg_l30"], 2), f"{rb['form']:+.2f}",
            ui.num(rb["elo"], 0), _oom(rb)]})
    st.dataframe(comp, hide_index=True, width="stretch")
    st.caption("Longer formats favour the stronger player: luck evens out over more legs.")
