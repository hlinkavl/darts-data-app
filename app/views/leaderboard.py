"""PI Leaderboard and head-to-head calculator."""

import math
from html import escape

import pandas as pd
import streamlit as st

import data
import ui

OPEN_ICON = "↗"
HIGHLIGHT = "background-color: rgba(57, 135, 229, 0.30); font-weight: 700"
TABLE_FORMATS = {"oom": "{:.0f}", "rank": "{:.0f}", "pi": "{:.2f}", "change": "{:+.2f}", "effective_average": "{:.1f}",
                 "avg_l30": "{:.2f}", "form": "{:+.2f}", "elo": "{:.0f}"}
# Ranking choice -> (first column = sort key, second column shown next to the name)
ORDERS = {"PDC Order of Merit": ("oom", "rank"), "Performance Index": ("rank", "oom")}
FORMATS = {"Typical match (first to 6 legs)": (6, "legs")} | {f"First to {n} legs": (n, "legs") for n in (3, 4, 5, 7, 8, 10, 11, 16, 18)} \
    | {f"First to {n} sets": (n, "sets") for n in (2, 3, 4, 5, 6, 7)}


def _open_profile(name: str) -> None:
    st.session_state["open_player"] = name
    st.switch_page(st.session_state["pages"]["player"])


def _h2h_card(ra: pd.Series, rb: pd.Series, p: float, fmt: str, photos: dict, oom) -> str:
    """Both players with photos and their win chances in big type, a split bar between them."""
    def side(r, chance, color, align):
        return (f"<div style='flex:1;text-align:{align};min-width:0'>"
                f"{ui.avatar(photos.get(r['player_key']), 84, name=r['player_name'], ring=color)}"
                f"<div style='font-weight:700;color:{ui.TEXT};margin-top:6px'>{escape(r['player_name'])}</div>"
                f"<div style='color:{ui.TEXT_2};font-size:0.8em'>{oom(r)} Order of Merit · PI {ui.num(r['pi'], 2)}</div>"
                f"<div style='font-size:2.8em;font-weight:800;color:{ui.TEXT};line-height:1.1;margin-top:6px'>{ui.pct(chance, 1)}</div>"
                f"</div>")
    return (f"<div style='border:1px solid {ui.GRID};border-radius:12px;padding:18px 20px;margin:6px 0 12px'>"
            f"<div style='display:flex;align-items:flex-end;gap:16px'>{side(ra, p, ui.SERIES[0], 'left')}"
            f"<div style='color:{ui.TEXT_2};padding-bottom:18px'>vs</div>{side(rb, 1 - p, ui.SERIES[1], 'right')}</div>"
            f"<div style='display:flex;height:12px;border-radius:6px;overflow:hidden;gap:2px;margin-top:12px'>"
            f"<div style='width:{100 * p:.1f}%;background:{ui.SERIES[0]}'></div><div style='flex:1;background:{ui.SERIES[1]}'></div></div>"
            f"<div style='text-align:center;color:{ui.TEXT_2};font-size:0.85em;margin-top:8px'>Chance to win · {escape(fmt.lower())}</div>"
            f"</div>")


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
    pick = st.selectbox("Find a player", sorted(names), index=None, placeholder="Start typing a name…", key="lb_find")
    first, second = ORDERS[order]
    board = board.sort_values([first, second], na_position="last").reset_index(drop=True)
    board["open"] = OPEN_ICON
    columns = ["open", first, "player_name", second, "pi", "change", "effective_average", "avg_l30", "form", "elo"]
    shown = board
    if pick:
        # A table cannot be scrolled from code: the player is pinned as the first row, the full table follows
        # (with the player highlighted in place), so it still scrolls from #1.
        shown = pd.concat([board[board["player_name"] == pick], board], ignore_index=True)
        st.caption(f"{pick} is pinned at the top and highlighted in the table. Clear the search to unpin.")
    styled = shown[columns].style.apply(
        lambda r: [HIGHLIGHT if r["player_name"] == pick else "" for _ in r], axis=1).format(TABLE_FORMATS, na_rep="–")
    picked = st.dataframe(
        styled,
        hide_index=True, width="stretch", height=520,
        column_config={
            "open": st.column_config.TextColumn("", width=34, help="Open the player's profile"),
            "oom": st.column_config.NumberColumn("PDC OoM #", help="Current official PDC Order of Merit (2-year prize money)"),
            "rank": st.column_config.NumberColumn("PI #", help="Position by Performance Index"),
            "player_name": "Player",
            "change": st.column_config.NumberColumn("PI vs last month", format="%+.2f"),
            "pi": st.column_config.ProgressColumn("PI", min_value=0.0, max_value=10.0, format="%.2f", help=ui.PI_HELP),
            "effective_average": st.column_config.NumberColumn("Effective Average", format="%.1f", help=ui.EFFECTIVE_AVERAGE_HELP),
            "avg_l30": st.column_config.NumberColumn("3-Dart Avg (L30)", format="%.2f"),
            "form": st.column_config.NumberColumn("Form", format="%+.2f"),
            "elo": st.column_config.NumberColumn("Elo", format="%.0f")},
        on_select="rerun", selection_mode="single-cell", key="lb_table")
    cells = picked.selection.cells if picked else []
    if cells and cells[0][1] in ("open", "player_name"):
        _open_profile(shown["player_name"].iloc[cells[0][0]])
    st.caption(f"Click {OPEN_ICON} or a name to open the player's profile.")
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
    photos = dict(zip(data.players()["player_key"], data.players()["image_file"]))
    st.markdown(_h2h_card(ra, rb, p, fmt, photos, _oom), unsafe_allow_html=True)
    comp = pd.DataFrame({
        "": ["PI", "Effective Average", "3-Dart Average (L30)", "Form", "Elo", "Order of Merit"],
        a: [ui.num(ra["pi"], 2), ui.num(ra["effective_average"]), ui.num(ra["avg_l30"], 2), f"{ra['form']:+.2f}",
            ui.num(ra["elo"], 0), _oom(ra)],
        b: [ui.num(rb["pi"], 2), ui.num(rb["effective_average"]), ui.num(rb["avg_l30"], 2), f"{rb['form']:+.2f}",
            ui.num(rb["elo"], 0), _oom(rb)]})
    st.dataframe(comp, hide_index=True, width="stretch")
    st.caption("Longer formats favour the stronger player: luck evens out over more legs.")
