"""Tournament Overview: title chances, the draw as a bracket, match details, players to watch, season, upcoming."""

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data
import ui

BRACKET_ROUNDS = 4  # last 16 to the final
BRACKET_SLOT_PX = 84  # height per first-column match: a two-row box plus spacing, so boxes never get squeezed
OUTSIDER_FAVOURITES = 8     # Beat the odds: the model's top title favourites are not outsiders
OUTSIDER_MAX_CHANCE = 0.25  # ... and a run is a surprise only if it had less than this chance
RISING_MONTHS = 3  # players to watch: PI change over this window
DATE_COLOR = "#8cb8ee"  # soft blue, as the Effective Average in the player profile
NO_DRAW = "no draw"  # a major in the calendar whose draw is not published yet


def _photos() -> dict[str, str]:
    """name key -> Wikimedia image file, to show photos next to names from the Wikipedia draws."""
    p = data.players()
    if p.empty or "image_file" not in p.columns:
        return {}
    p = p.dropna(subset=["image_file"])
    return {ui.name_key(n): f for n, f in zip(p["player_name"], p["image_file"])}


def _avatar(photos: dict, name, size: int = 34) -> str:
    return ui.avatar(photos.get(ui.name_key(name)), size, name=name)


def _name(x) -> str | None:
    """A player name, or None when the spot is empty (None, "" or NaN all occur)."""
    return x.strip() if isinstance(x, str) and x.strip() else None


def _known(col: pd.Series) -> pd.Series:
    return col.map(lambda x: _name(x) is not None).astype(bool)


def _seed(s) -> str:
    s = "" if s is None or (isinstance(s, float) and pd.isna(s)) else str(s).strip()
    return f"({s})" if s and s.lower() not in ("none", "nan") else ""


def _date(d, fmt: str = "%d %b %Y") -> str:
    return f"{pd.Timestamp(d):{fmt}}" if d is not None and pd.notna(d) else "–"


def _short_title(title: str) -> str:
    return title.replace(" (darts)", "")


# --------------------------------------------------------------------------------------- tournament picker

def _date_range(start, end) -> str:
    """'22–25 Oct 2026', '28 Sep – 4 Oct 2026', '11 Dec 2026 – 3 Jan 2027', 'dates TBC'."""
    if start is None or pd.isna(start) or end is None or pd.isna(end):
        return "dates TBC"
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    if a.year != b.year:
        return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {b:%b %Y}"
    return f"{a.day} {a:%b} – {b.day} {b:%b %Y}"


def _events(preds: pd.DataFrame, cal: pd.DataFrame) -> list[dict]:
    """Every major as one timeline, newest first: ✅ finished, 🔴 in progress, 🗓️ upcoming. Majors without a
    published draw are listed too (mode "no draw") and only show a note. Without confirmed dates an event is
    placed by last year's dates."""
    cal = cal.drop_duplicates("wiki_title").set_index("wiki_title") if len(cal) else pd.DataFrame()
    pairs = list(preds[["wiki_title", "mode"]].drop_duplicates().itertuples(index=False, name=None))
    with_draw = {t for t, _ in pairs}
    if len(cal):
        pending = cal[cal["status"].isin(["upcoming", "in progress", "date unknown"]) & ~cal.index.isin(with_draw)]
        pairs += [(t, NO_DRAW) for t in pending.index if isinstance(t, str)]
    out = []
    for title, mode in pairs:
        row = cal.loc[title] if title in cal.index else None
        start, end = (row["start_date"], row["end_date"]) if row is not None else (None, None)
        status = row["status"] if row is not None else None
        name = f"{row['tournament_name']} {int(row['edition'])}" if row is not None else _short_title(title)
        when = pd.Timestamp(start if start is not None and pd.notna(start) else end) \
            if (start is not None and pd.notna(start)) or (end is not None and pd.notna(end)) else None
        if when is None and row is not None:  # dates not confirmed yet: last year's edition + 1 year
            last = cal[(cal["tournament_key"] == row["tournament_key"]) & (cal["edition"] == row["edition"] - 1)]
            last_date = last["start_date"].fillna(last["end_date"]).dropna() if len(last) else pd.Series(dtype="datetime64[ns]")
            when = pd.Timestamp(last_date.iloc[0]) + pd.DateOffset(years=1) if len(last_date) else None
        dates = _date_range(start, end)
        if mode == "backtest":
            winner = row["winner_name"] if row is not None and isinstance(row["winner_name"], str) else None
            label = f"✅ {name}" + (f" ({winner})" if winner else "") + f"  |  {dates}"
        elif mode == "live" or status == "in progress":
            label = f"🔴 {name} · live  |  {dates}"
        else:
            label = f"🗓️ {name}  |  {dates}"
        out.append({"title": title, "mode": mode, "label": label, "name": name, "dates": dates, "start": start,
                    "end": end, "when": when})
    return sorted(out, key=lambda e: e["when"].value if e["when"] is not None else float("inf"), reverse=True)


def _default_event(events: list[dict]) -> int:
    """Live event, else the next upcoming one with a draw, else the latest finished one."""
    for wanted in (("live",), ("pre-tournament",), ("backtest",)):
        hits = [k for k, e in enumerate(events) if e["mode"] in wanted]
        if hits:
            return hits[-1] if wanted == ("pre-tournament",) else hits[0]  # nearest upcoming is the last one
    return 0


STATUS_PILL = {"backtest": ("Finished", "#2a3a2a", "#8fd18f"), "live": ("Live", "#4a2323", "#ff8a8a"),
               "pre-tournament": ("Upcoming", "#22324a", "#8cb8ee")}


def _stage(draw: pd.DataFrame) -> str:
    """Where a running event is: the first round with a match still to play ('Semi-finals · 1 of 2 played')."""
    for order in sorted(draw["round_order"].unique()):
        rnd = draw[draw["round_order"] == order]
        done = int(_known(rnd["winner"]).sum())
        if done < len(rnd):
            name = rnd["round_name"].iloc[0]
            return f"{name} · {done} of {len(rnd)} played" if done else f"{name} next"
    return "Finished"


def _header(ev: dict, preds: pd.DataFrame, draw: pd.DataFrame, cal: pd.DataFrame) -> None:
    """One compact card: event name with a status pill, dates, and up to three facts in normal-size text."""
    mode = ev["mode"]
    fav = preds[preds["round_name"] == "Winner"].nlargest(1, "p_reach")
    favourite = f"{fav['player_name'].iloc[0]} · {ui.pct(fav['p_reach'].iloc[0], 1)}" if len(fav) else "–"
    facts, note = [], ""
    if mode == "backtest":
        bts = data.table("tournament_backtest_summary")
        b = bts[(bts["wiki_title"] == ev["title"]) & (bts["metric_set"] == "model, round format")]
        avg = cal.loc[cal["wiki_title"] == ev["title"], "winner_avg"]
        if len(b):
            b = b.iloc[0]
            avg_txt = f" ({avg.iloc[0]:.1f} final avg)" if len(avg) and pd.notna(avg.iloc[0]) else ""
            facts = [("Champion", f"🏆 {b.champion}{avg_txt}"),
                     ("Champion's chance before the event", f"{ui.pct(b.champion_p_title, 1)} (#{int(b.champion_rank_by_p_title)} in the model)"),
                     ("Pre-match favourite won", f"{ui.num(b.favourite_won_pct, 0)} % of {int(b.matches)} matches")]
        note = "Everything below is what the model predicted before the first match."
    elif mode == "live":
        facts = [("Stage", _stage(draw)), ("Title favourite now", favourite)]
        note = "Played matches are fixed; the rest of the draw is simulated again after every refresh."
    else:
        days = (pd.Timestamp(ev["start"]).normalize() - pd.Timestamp.now().normalize()).days \
            if ev["start"] is not None and pd.notna(ev["start"]) else None
        facts = [("Starts", (f"{pd.Timestamp(ev['start']):%a %d %b}, " if days else "")
                  + ("tomorrow" if days == 1 else (f"in {days} days" if days and days > 1 else "–"))),
                 ("Stage", _stage(draw)), ("Title favourite", favourite)]
        note = "Predictions from the players' current form."
    label, bg, fg = STATUS_PILL.get(mode, STATUS_PILL["pre-tournament"])
    cells = "".join(f"<div><div style='color:{ui.TEXT_2};font-size:0.78em'>{escape(k)}</div>"
                    f"<div style='color:{ui.TEXT};font-weight:600;margin-top:2px'>{escape(v)}</div></div>" for k, v in facts)
    st.markdown(
        f"<div style='border:1px solid {ui.GRID};border-radius:12px;padding:16px 20px;margin:6px 0 18px'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap'>"
        f"<div><div style='font-size:1.35em;font-weight:700;color:{ui.TEXT}'>{escape(ev['name'])}</div>"
        f"<div style='color:{DATE_COLOR};font-size:0.9em;margin-top:2px'>{escape(ev['dates'])}</div></div>"
        f"<span style='background:{bg};color:{fg};border-radius:999px;padding:3px 12px;font-size:0.82em;"
        f"font-weight:600'>{label}</span></div>"
        + (f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px 28px;"
           f"border-top:1px solid {ui.GRID};margin-top:14px;padding-top:12px'>{cells}</div>" if cells else "")
        + f"<div style='color:{ui.TEXT_2};font-size:0.8em;margin-top:12px'>{escape(note)}</div></div>",
        unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------- predictions

def _title_chart(winners: pd.DataFrame) -> go.Figure:
    top = winners.nlargest(16, "p_reach").sort_values("p_reach")
    fig = go.Figure(go.Bar(
        x=top["p_reach"], y=top["player_name"], orientation="h", marker=dict(color=ui.SERIES[0], line=dict(color=ui.SURFACE, width=2)),
        text=[ui.pct(v, 1) for v in top["p_reach"]], textposition="outside", textfont=dict(color=ui.TEXT_2),
        hovertemplate="%{y}: %{x:.1%} to win the title<extra></extra>", cliponaxis=False))
    fig = ui.layout(fig, height=60 + 28 * len(top), xaxis=dict(tickformat=".0%", title="chance to win the title",
                                                                range=[0, top["p_reach"].max() * 1.22]))
    fig.update_traces(cliponaxis=True)
    return fig


def _all_title_chances(preds: pd.DataFrame) -> None:
    """Every player's title chance (the chart shows the top 16)."""
    winners = preds[preds["round_name"] == "Winner"].sort_values("p_reach", ascending=False)
    if len(winners) <= 16:
        return
    with st.expander(f"All {len(winners)} players"):
        table = winners.assign(seed=winners["seed"].map(lambda v: _seed(v).strip("()")),
                               rank=range(1, len(winners) + 1))[["rank", "player_name", "seed", "p_reach"]]
        st.dataframe(table, hide_index=True, width="stretch", height=min(36 + 35 * len(table), 420),
                     column_config={"rank": st.column_config.NumberColumn("#", width=40), "player_name": "Player",
                                    "seed": st.column_config.TextColumn("Seed", width=60),
                                    "p_reach": st.column_config.ProgressColumn("Chance to win the title", min_value=0.0,
                                                                               max_value=float(table["p_reach"].max()),
                                                                               format="percent")})


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


def _momentum(as_of) -> pd.DataFrame:
    """PI change over the 3 months before `as_of` and current form, from the monthly PI snapshots (each computed
    only from earlier matches, so backtests do not look ahead)."""
    hist = data.table("performance_index")
    if hist.empty:
        return pd.DataFrame(columns=["player_key", "pi_change", "form"])
    when = pd.to_datetime(hist["as_of_date"])
    now_d = when[when <= pd.Timestamp(as_of)].max()
    then_d = when[when <= now_d - pd.DateOffset(months=RISING_MONTHS)].max() if pd.notna(now_d) else pd.NaT
    if pd.isna(now_d) or pd.isna(then_d):
        return pd.DataFrame(columns=["player_key", "pi_change", "form"])
    form = "form_major" if "form_major" in hist.columns else "form"  # the model's form input since Nov 2026
    now = hist[when == now_d][["player_key", "pi", form]].rename(columns={form: "form"})
    then = hist[when == then_d][["player_key", "pi"]].rename(columns={"pi": "pi_then"})
    m = now.merge(then, on="player_key")
    return m.assign(pi_change=m["pi"] - m["pi_then"])[["player_key", "pi_change", "form"]]


def _short_round(name: str) -> str:
    """'Quarter-finals' -> 'QF', 'First round' -> '1st round'."""
    ordinals = {"First": "1st", "Second": "2nd", "Third": "3rd", "Fourth": "4th", "Fifth": "5th"}
    first, _, rest = name.partition(" ")
    return {"Quarter-finals": "QF", "Semi-finals": "SF"}.get(name, f"{ordinals[first]} {rest}" if first in ordinals else name)


def _result(name: str, draw: pd.DataFrame, mode: str, seed) -> str:
    """How far the player got: Champion, Runner-up, Out in QF; Still in during a live event; the seed before it."""
    if mode == "pre-tournament" or draw.empty:
        return f"seed {_seed(seed).strip('()')}" if _seed(seed) else "unseeded"
    played = draw[(draw["player_a"] == name) | (draw["player_b"] == name)].sort_values("round_order")
    if played.empty:
        return ""
    last, final = played.iloc[-1], draw["round_order"].max()
    if _name(last.winner) == name:
        return "🏆 Champion" if last.round_order == final else f"Still in · next {_short_round(_next_round(draw, last))}"
    if _name(last.winner):
        return "Runner-up" if last.round_order == final else f"Out in {_short_round(last.round_name)}"
    return f"Still in · {_short_round(last.round_name)}"


def _next_round(draw: pd.DataFrame, match) -> str:
    later = draw[draw["round_order"] > match.round_order].sort_values("round_order")
    return later["round_name"].iloc[0] if len(later) else match.round_name


def _player_card(photos: dict, name: str, tag: str, main: str, main_color: str, detail: str) -> str:
    return (f"<div style='display:flex;align-items:center;gap:12px;border:1px solid {ui.GRID};border-radius:10px;"
            f"padding:10px 12px;margin:8px 0'>{_avatar(photos, name, 46)}<div style='min-width:0'>"
            f"<div><b>{escape(name)}</b> <span style='color:{ui.TEXT_2};font-size:0.85em'>{escape(tag)}</span></div>"
            f"<div style='color:{main_color};font-weight:700;margin-top:2px'>{main}</div>"
            f"<div style='color:{ui.TEXT_2};font-size:0.82em'>{detail}</div></div></div>")


def _on_the_rise(preds: pd.DataFrame, draw: pd.DataFrame, mode: str, photos: dict) -> None:
    """Upcoming and live events: the biggest PI gain over the 3 months before the event, with positive form."""
    st.subheader("On the rise")
    winners = preds[preds["round_name"] == "Winner"].dropna(subset=["player_key"])
    cand = winners.merge(_momentum(preds["as_of"].iloc[0]), on="player_key")
    rising = cand[(cand["pi_change"] > 0) & (cand["form"] > 0)].nlargest(3, "pi_change")
    if len(rising) < 3:
        rising = pd.concat([rising, cand.drop(rising.index).nlargest(3 - len(rising), "pi_change")])
    if rising.empty:
        st.caption("Not enough PI history for the players in this draw.")
        return
    cards = "".join(_player_card(photos, r.player_name, _result(r.player_name, draw, mode, r.seed),
                                 f"{'▲' if r.pi_change >= 0 else '▼'} {r.pi_change:+.2f} PI in {RISING_MONTHS} months",
                                 ui.WIN if r.pi_change >= 0 else ui.LOSS,
                                 f"Form {r.form:+.2f} · title chance {ui.pct(r.p_reach, 1)}") for r in rising.itertuples())
    st.markdown(cards, unsafe_allow_html=True)
    st.caption(f"The biggest PI gains over the {RISING_MONTHS} months before the event, with positive form on majors "
               "(last 6 major matches vs last 20).")


def _beat_the_odds(preds: pd.DataFrame, draw: pd.DataFrame, photos: dict) -> None:
    """Finished events: outsiders (not among the model's favourites) who reached at least the quarter-finals,
    the least likely runs first."""
    st.subheader("Beat the odds")
    first, last = preds["round_order"].min(), preds["round_order"].max()
    title = preds[preds["round_order"] == last]
    favourites = set(title.nlargest(max(OUTSIDER_FAVOURITES, title["player_name"].nunique() // 8), "p_reach")["player_name"])
    last_eight = last - 3  # Winner, Final, Semi-finals, Quarter-finals
    reached = {}
    for m in draw.itertuples():
        for name in (_name(m.player_a), _name(m.player_b)):
            if name:
                reached[name] = max(reached.get(name, first), m.round_order + (1 if _name(m.winner) == name else 0))
    rows = []
    for name, r in reached.items():
        p_here = preds.loc[(preds["player_name"] == name) & (preds["round_order"] == r), "p_reach"]
        if name not in favourites and r >= last_eight and len(p_here) and p_here.iloc[0] < OUTSIDER_MAX_CHANCE:
            rank = int((title["p_reach"] > title.loc[title["player_name"] == name, "p_reach"].max()).sum()) + 1
            rows.append({"player_name": name, "p_here": float(p_here.iloc[0]), "rank": rank})
    best = pd.DataFrame(rows).nsmallest(3, "p_here") if rows else pd.DataFrame()
    if best.empty:
        st.caption("No outsider reached the quarter-finals: the favourites dominated.")
        return
    cards = "".join(_player_card(photos, " ".join(r.player_name.split()),
                                 _result(r.player_name, draw, "backtest", None),
                                 f"{ui.pct(r.p_here, 0 if r.p_here >= 0.1 else 1)} chance to get this far", ui.WIN,
                                 f"#{r.rank} in the model's title ranking before the event")
                    for r in best.itertuples())
    st.markdown(cards, unsafe_allow_html=True)
    st.caption(f"Outsiders (outside the model's top {OUTSIDER_FAVOURITES} title favourites) who reached at least the "
               "quarter-finals, the least likely runs first.")


# ----------------------------------------------------------------------------------------------- bracket

def _format(m) -> str:
    return f"first to {int(m.first_to)} {m.unit}" if pd.notna(m.first_to) else ""


def _bracket_box(m, short: dict, final: bool = False, projected: tuple = (None, None)) -> str:
    """One match: surname, the model's pre-match chance (small) and the score; the winner's row in green (with a
    trophy in the final). A spot not decided yet shows the most likely player in grey italics, without a number:
    their chance to get there is not a match chance, and two of them next to each other would not add up to 100 %
    (`projected` = (name, chance) per side)."""
    empty = pd.Series({"player_a": None, "player_b": None, "winner": None, "walkover": False, "score_a": None,
                       "score_b": None, "p_a": float("nan"), "seed_a": None, "seed_b": None, "avg_a": None,
                       "avg_b": None, "first_to": float("nan"), "unit": None})
    m = empty if m is None else m
    winner = _name(m.winner)
    played = winner is not None
    rows = []
    for name, score, p, proj in ((_name(m.player_a), m.score_a, m.p_a, projected[0]),
                                 (_name(m.player_b), m.score_b, 1 - m.p_a, projected[1])):
        if not name and proj:
            rows.append((short.get(proj[0], proj[0]), "", "", False, False, True))  # no %: see the docstring
            continue
        won = played and name == winner
        score_txt = ("w/o" if won else "") if m.walkover is True else (ui.num(score, 0) if played else "")
        p_txt = ui.pct(p) if name and pd.notna(p) else ""
        label = (short.get(name, name) + (" 🏆" if final and won else "")) if name else "TBD"
        rows.append((label, p_txt, score_txt, won, played, False))
    # Three looks: played (solid, winner in green), upcoming (both players known: blue frame and a label),
    # projected (a spot still open: dashed frame, the model's most likely player in grey italics).
    upcoming = not played and all(not r[5] and r[0] != "TBD" for r in rows)
    projected_box = any(r[5] for r in rows)
    html = (f"<div style='font-size:0.68em;font-weight:700;letter-spacing:.06em;color:{ui.SERIES[0]};"
            f"padding:3px 8px 0'>UPCOMING</div>") if upcoming else ""
    for i, (name, p, score, won, played_row, proj) in enumerate(rows):
        if won:
            style = f"background:rgba(12,163,12,.16);border-left:3px solid {ui.WIN};color:{ui.TEXT};font-weight:700"
        elif proj:
            style = f"border-left:3px solid transparent;color:{ui.TEXT_2};font-style:italic"
        else:
            style = (f"border-left:3px solid transparent;"
                     f"color:{ui.TEXT_2 if played_row or name == 'TBD' else ui.TEXT}")
        sep = f"border-top:1px solid {ui.GRID};" if i else ""
        html += (f"<div style='display:flex;align-items:center;gap:6px;padding:4px 8px;{sep}{style}'>"
                 f"<span style='flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{escape(name)}</span>"
                 f"<span style='font-size:0.75em;color:{ui.TEXT_2};font-weight:400;font-style:normal'>{p}</span>"
                 f"<span style='min-width:22px;text-align:right'>{score}</span></div>")
    if upcoming:
        frame = f"border:1.5px solid {ui.SERIES[0]};background:#1f2733"
    elif projected_box or not played:
        frame = f"border:1.5px dashed {ui.GRID};background:transparent"
    else:
        frame = f"border:1px solid {ui.GRID};background:#222220"
    return (f"<div style='{frame};border-radius:6px;font-size:0.88em;margin:5px 0;overflow:hidden;"
            f"flex-shrink:0'>{html}</div>")


def _projector(preds: pd.DataFrame):
    """For a spot not decided yet: the player most likely to reach it and that chance. Player draw position s plays
    match s // 2^k in the k-th round after the first; side A holds the first half of that section."""
    first = preds["round_order"].min()
    slots = preds[preds["round_order"] == first][["slot", "player_name"]]
    reach = preds.pivot_table(index="player_name", columns="round_order", values="p_reach")

    def best(order: int, match: int, side: int):
        width = 2 ** (order - first)
        lo = (2 * match + side) * width
        names = slots[(slots["slot"] >= lo) & (slots["slot"] < lo + width)]["player_name"]
        if names.empty or order not in reach.columns:
            return None
        r = reach.reindex(names)[order].dropna()
        return (r.idxmax(), float(r.max())) if len(r) else None
    return best


def _bracket(matches: pd.DataFrame, preds: pd.DataFrame) -> None:
    """The last rounds as a bracket: a match in slot i feeds slot i // 2 of the next round."""
    orders = sorted(matches["round_order"].unique())[-BRACKET_ROUNDS:]
    short = ui.surnames(pd.concat([matches["player_a"], matches["player_b"], preds["player_name"]]))
    best = _projector(preds)
    height = 2 ** (len(orders) - 1) * BRACKET_SLOT_PX
    # On a phone only two rounds fit: start at the first round that is not finished (finished event: the last two).
    open_k = [k for k, o in enumerate(orders)
              if not matches.loc[matches["round_order"] == o, "winner"].map(_name).notna().all()]
    first_shown = open_k[0] if open_k else max(0, len(orders) - 2)
    cols, any_projected = [], False
    for k, order in enumerate(orders):
        rnd = matches[matches["round_order"] == order].drop_duplicates("slot").set_index("slot")
        boxes = ""
        for i in range(2 ** (len(orders) - 1 - k)):
            m = rnd.loc[i] if i in rnd.index else None
            projected = tuple(best(order, i, side) if m is None or not _name(m[f"player_{ab}"]) else None
                              for side, ab in ((0, "a"), (1, "b")))
            any_projected |= any(projected)
            boxes += _bracket_box(m, short, k == len(orders) - 1, projected)
        cols.append(f"<div class='{'br-early' if k < first_shown else ''}' "
                    f"style='flex:1;min-width:165px;display:flex;flex-direction:column'>"
                    f"<div style='text-align:center;color:{ui.TEXT_2};font-size:0.8em;margin-bottom:4px'>"
                    f"{escape(matches.loc[matches['round_order'] == order, 'round_name'].iloc[0])}</div>"
                    f"<div style='height:{height}px;display:flex;flex-direction:column;justify-content:space-around'>{boxes}</div></div>")
    sw = "display:inline-block;width:14px;height:10px;border-radius:3px;vertical-align:middle;margin-right:5px"
    legend = [f"<span><span style='{sw};background:rgba(12,163,12,.35);border-left:3px solid {ui.WIN}'></span>Played (winner)</span>",
              f"<span><span style='{sw};border:1.5px solid {ui.SERIES[0]};background:#1f2733'></span>Upcoming</span>"]
    if any_projected:
        legend.append(f"<span><span style='{sw};border:1.5px dashed {ui.TEXT_2}'></span><i>Not decided yet: the model's "
                      f"most likely player</i></span>")
    st.markdown(f"<div style='display:flex;flex-wrap:wrap;gap:6px 18px;color:{ui.TEXT_2};font-size:0.8em;"
                f"margin:0 0 8px'>{''.join(legend)}</div>"
                f"<div style='display:flex;gap:14px;overflow-x:auto;padding-bottom:6px'>{''.join(cols)}</div>",
                unsafe_allow_html=True)
    st.caption("The small % is the model's chance to win the match, before it is played. Every match with full "
               "names, day and averages: Matches above."
               + (" On a phone the bracket starts at the current round; swipe for later rounds." if first_shown else ""))


def _match_card(m, photos: dict) -> str:
    """A compact card: one row per player (photo, name, and at the right the chance, or the score once played), then
    the pre-match chance as a thin bar; a played match shows its pre-match numbers over the bar. The photo's ring
    has the player's colour in the bar (blue on top, orange below)."""
    winner = _name(m.winner)
    played = winner is not None

    def row(name, seed, score, chance, ring):
        name = _name(name)
        if not name:
            return f"<div class='mc-row' style='color:{ui.TEXT_2}'>TBD</div>"
        won = played and name == winner
        right = (("w/o" if won else "") if m.walkover is True else ui.num(score, 0)) if played else ui.pct(chance)
        return (f"<div class='mc-row' style='color:{ui.TEXT if won or not played else ui.TEXT_2};"
                f"font-weight:{700 if won else 400}'>"
                f"{ui.avatar(photos.get(ui.name_key(name)), 26, name=name, ring=ring)}<span class='mc-name'>{escape(name)} "
                f"<span style='color:{ui.TEXT_2};font-weight:400;font-size:0.82em'>{_seed(seed)}</span></span>"
                f"<span style='color:{ui.WIN if won else (ui.TEXT_2 if played else ui.TEXT)};font-weight:700'>"
                f"{right}</span></div>")

    p = m.p_a if pd.notna(m.p_a) else None
    chance = ""
    if p is not None:  # an open match has its chances next to the names; a played one keeps them over the bar
        chance = ((f"<div style='display:flex;justify-content:space-between;align-items:baseline;margin-top:6px;"
                   f"font-size:0.85em'><b style='color:{ui.TEXT_2}'>{ui.pct(p)}</b>"
                   f"<span style='color:{ui.TEXT_2};font-size:0.85em'>before the match</span>"
                   f"<b style='color:{ui.TEXT_2}'>{ui.pct(1 - p)}</b></div>") if played else "") + (
                  f"<div style='display:flex;height:6px;border-radius:3px;overflow:hidden;gap:2px;"
                  f"margin-top:{2 if played else 6}px'>"
                  f"<div style='width:{round(100 * p)}%;background:{ui.SERIES[0]}'></div>"
                  f"<div style='flex:1;background:{ui.SERIES[1]}'></div></div>")
    return (f"<div style='border:1px solid {ui.GRID};border-radius:10px;padding:8px 10px;background:#20201f'>"
            + row(m.player_a, m.seed_a, m.score_a, p, ui.SERIES[0])
            + row(m.player_b, m.seed_b, m.score_b, 1 - p if p is not None else None, ui.SERIES[1]) + chance + "</div>")


def _upcoming_info() -> dict:
    """Upcoming matches (date, both PIs, head-to-head record) by the pair of names, for the match cards."""
    up = data.table("upcoming_matches")
    return {frozenset((r.player_a_name, r.player_b_name)): r for r in up.itertuples()} if len(up) else {}


def _round_status(rnd: pd.DataFrame) -> str:
    played = int(_known(rnd["winner"]).sum())
    if played == len(rnd):
        return "played"
    if played:
        return f"{played} of {len(rnd)} played"
    return "next" if (_known(rnd["player_a"]) & _known(rnd["player_b"])).any() else "not decided yet"


def _match_details(matches: pd.DataFrame, photos: dict, event_key: str, info: dict) -> None:
    """One round at a time, in playing order; opens on the round being played (finished events: the final).
    info: upcoming matches by pair of names; their day goes into the round's chips."""
    rounds = (matches[["round_order", "round_name", "first_to", "unit"]].drop_duplicates("round_order")
              .sort_values("round_order"))
    status = [_round_status(matches[matches["round_order"] == o]) for o in rounds["round_order"]]
    icon = {"played": "✅"}
    labels = [f"{icon.get(x, '🔴' if ' of ' in x else '🗓️')} {r.round_name} · {x}"
              for r, x in zip(rounds.itertuples(), status)]
    current = next((i for i, x in enumerate(status) if x == "next" or " of " in x), len(labels) - 1)
    choice = st.selectbox("Round", range(len(labels)), index=current, format_func=lambda i: labels[i],
                          key=f"draw_round_{event_key}")  # own default per event
    rnd = matches[matches["round_order"] == rounds["round_order"].iloc[choice]].sort_values("slot")
    r = rounds.iloc[choice]
    shown = [m for m in rnd.itertuples() if _name(m.player_a) and _name(m.player_b)]
    days = sorted({pd.Timestamp(u.start_time).normalize() for m in shown
                   if (u := info.get(frozenset((_name(m.player_a), _name(m.player_b))))) is not None})
    # The round's key facts as chips above the cards: when, the format, how far it is.
    chips = ([f"🗓️ {', '.join(f'{d:%a %d %b}' for d in days)}"] if days else []) \
        + ([f"🎯 First to {int(r.first_to)} {r.unit}"] if pd.notna(r.first_to) else []) \
        + [f"{icon.get(status[choice], '🔴' if ' of ' in status[choice] else '⏳')} {status[choice].capitalize()}"]
    st.markdown("<div style='display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 12px'>" + "".join(
        f"<span style='border:1px solid {ui.GRID};background:#262624;border-radius:999px;padding:4px 12px;"
        f"color:{ui.TEXT};font-size:0.9em;font-weight:600'>{escape(c)}</span>" for c in chips) + "</div>",
        unsafe_allow_html=True)
    if shown:  # early rounds: narrow cards, three or more per row; the last rounds: two per row; phones: one
        grid = "mc-grid-2" if len(rnd) <= 4 else "mc-grid"
        st.markdown(f"<div class='{grid}'>{''.join(_match_card(m, photos) for m in shown)}</div>",
                    unsafe_allow_html=True)
        st.caption("Chances in this round's format. The ring around each photo shows the player's colour in the bar.")
    else:
        st.caption("The players of this round are not known yet; the road to the final below shows who is most likely.")


# ------------------------------------------------------------------------------------- upcoming, season

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
    rows["Predictions"] = rows["has_draw"].map({True: "✓ draw", False: ""})
    st.dataframe(rows[["tournament_name", "Dates", "Status", "Winner", "Predictions"]].rename(columns={"tournament_name": "Major"}),
                 hide_index=True, width="stretch",
                 column_config={"Major": st.column_config.TextColumn("Major", width=270),
                                "Dates": st.column_config.TextColumn("Dates", width=150),
                                "Status": st.column_config.TextColumn("Status", width=125),
                                "Winner": st.column_config.TextColumn("Winner", width=270),
                                "Predictions": st.column_config.TextColumn("Predictions", width=95,
                                                                           help="✓ draw = title chances and bracket available")})


def render() -> None:
    st.title("🏆 Tournament Overview")
    cal, preds = data.table("majors_calendar"), data.table("tournament_predictions")
    if len(cal):
        nxt = cal[cal["status"].isin(["in progress", "upcoming"])].sort_values("start_date").head(1)
        if len(nxt):
            n = nxt.iloc[0]
            when = _date_range(n.start_date, n.end_date)
            st.caption(f"{'🔴 Now' if n.status == 'in progress' else '🗓️ Next major'}: **{n.tournament_name}** · {when}"
                       + ("" if n.has_draw else " · predictions appear once the draw is published"))

    tab_pred, tab_season = st.tabs(["Predictions", "Season calendar"])
    with tab_pred:
        events = _events(preds if len(preds) else pd.DataFrame(columns=["wiki_title", "mode"]), cal)
        ev = None
        if not events:
            st.info("No majors in the calendar yet.")
        else:
            i = st.selectbox("Tournament", range(len(events)), index=_default_event(events), key="event",
                             format_func=lambda k: events[k]["label"])
            ev = events[i]
            if ev["mode"] == NO_DRAW:
                when = (f"It starts on {_date(ev['start'])}. " if ev["start"] is not None and pd.notna(ev["start"])
                        else "The dates are not confirmed yet. ")
                st.info(f"**{ev['name']}**: the draw is not published yet. {when}Title chances, the "
                        "bracket and match predictions appear here automatically once it is, usually a few days "
                        "before the first match.")
                ev = None
        if ev is not None:
            pr = preds[(preds["wiki_title"] == ev["title"]) & (preds["mode"] == ev["mode"])]
            dm = data.table("tournament_draw_matches")
            draw = dm[(dm["wiki_title"] == ev["title"]) & (dm["mode"] == ev["mode"])]
            _header(ev, pr, draw, cal)
            photos = _photos()
            left, right = st.columns([3, 2], gap="large")
            with left:
                st.subheader("Chance to win the title")
                winners = pr[pr["round_name"] == "Winner"]
                # during an event the players already out have 0 %; before it nobody is out
                alive = winners[winners["p_reach"] > 0] if ev["mode"] == "live" else winners
                st.plotly_chart(_title_chart(alive if len(alive) else winners), width="stretch",
                                config={"displayModeBar": False})
                if 0 < len(alive) < len(winners):
                    st.caption(f"Players still in the draw; {len(winners) - len(alive)} are already out.")
                _all_title_chances(pr)
            with right:
                if ev["mode"] == "backtest":
                    _beat_the_odds(pr, draw, photos)
                else:
                    _on_the_rise(pr, draw, ev["mode"], photos)
            if draw.empty:
                st.info("The draw is not published yet.")
            else:
                st.subheader("Matches")
                _match_details(draw, photos, f"{ev['title']}_{ev['mode']}", _upcoming_info())
                late = draw["round_order"].nunique() > BRACKET_ROUNDS
                st.subheader("Road to the final" if late else "The draw")
                _bracket(draw, pr)
            with st.expander("Round by round: every player's chance to reach each round"):
                _round_table(pr)
    with tab_season:
        _season(cal)
