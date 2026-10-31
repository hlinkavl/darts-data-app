"""Tournament Overview tables: season calendar, draw predictions / backtests, upcoming match cards.

Pure pandas, shared by the Databricks notebook 06_tournaments and the local app snapshot.
"""

from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd

from . import bracket, calendar, tournament
from .formats import match_probability


def season_calendar(pages: pd.DataFrame, events: pd.DataFrame, majors: dict, today: date) -> tuple[pd.DataFrame, dict]:
    """Majors with dates (Wikipedia infobox), status and winners (results data), plus the parsed draws by title.

    pages: title, wikitext (pages that exist). events: tournament_key, event_date, winner_name, winner_avg (majors).
    """
    rows, draws = [], {}
    for page in pages.itertuples():
        found = calendar.match_major(page.title, majors)
        if not found:
            continue
        key, edition = found
        start, end = calendar.infobox_dates(page.wikitext)
        draw = bracket.build_draw(page.title, page.wikitext)
        if draw:
            draws[page.title] = draw
        rows.append({"tournament_key": key, "tournament_name": majors[key]["name"], "edition": edition,
                     "wiki_title": page.title, "start_date": pd.Timestamp(start) if start else pd.NaT,
                     "end_date": pd.Timestamp(end) if end else pd.NaT, "has_draw": draw is not None,
                     "winner_name": draw.rounds[-1].matches[0].winner if draw else None, "winner_avg": np.nan})
    cal = pd.DataFrame(rows, columns=["tournament_key", "tournament_name", "edition", "wiki_title", "start_date",
                                      "end_date", "has_draw", "winner_name", "winner_avg"])

    # Winners from the results data (final date within the event dates); majors without a page come from there alone.
    events = events.assign(event_date=pd.to_datetime(events["event_date"]))
    extra = []
    for ev in events[events["event_date"] >= pd.Timestamp(today.year - 1, 1, 1)].itertuples():
        hit = cal.index[(cal.tournament_key == ev.tournament_key) & (cal.start_date <= ev.event_date)
                        & (cal.end_date >= ev.event_date)]
        if len(hit):
            if ev.winner_name:
                cal.loc[hit, ["winner_name", "winner_avg"]] = [ev.winner_name, ev.winner_avg]
        elif ev.tournament_key in majors:
            extra.append({"tournament_key": ev.tournament_key, "tournament_name": majors[ev.tournament_key]["name"],
                          "edition": ev.event_date.year, "wiki_title": None, "start_date": pd.NaT,
                          "end_date": ev.event_date, "has_draw": False,
                          "winner_name": ev.winner_name or None, "winner_avg": ev.winner_avg})
    cal = pd.concat([cal, pd.DataFrame(extra)], ignore_index=True) if extra else cal

    # Majors of the current season with no data yet (no Wikipedia page, no results) still get a row.
    for key, m in majors.items():
        if not ((cal.tournament_key == key) & (cal.edition == today.year)).any():
            cal.loc[len(cal)] = {"tournament_key": key, "tournament_name": m["name"], "edition": today.year,
                                 "wiki_title": m["wiki"].format(year=today.year), "start_date": pd.NaT,
                                 "end_date": pd.NaT, "has_draw": False, "winner_name": None, "winner_avg": np.nan}

    today_ts = pd.Timestamp(today)
    cal["status"] = np.select([cal.end_date.isna(), cal.end_date < today_ts, cal.start_date <= today_ts],
                              ["date unknown", "completed", "in progress"], default="upcoming")
    cal["season"] = cal["edition"]
    return cal.sort_values("end_date", na_position="last").reset_index(drop=True), draws


def draw_outputs(cal: pd.DataFrame, draws: dict, players: pd.DataFrame, current: pd.DataFrame,
                 elo_latest: pd.DataFrame, strength_history: Callable[[], object], today: date) -> dict[str, pd.DataFrame]:
    """Simulations for every parsed draw: backtests for finished events (strengths as of the start date, from
    strength_history() built lazily), predictions for the others (current strengths; live if matches were played).

    current: player_key, strength (current PI model, major strength). elo_latest: player_key, elo.
    """
    history = None
    predictions, draw_matches, bt_matches, bt_summary = [], [], [], []
    for c in cal[cal.has_draw].itertuples():
        draw = draws[c.wiki_title]
        finished = draw.rounds[-1].matches[0].winner is not None
        meta = {"tournament_key": c.tournament_key, "tournament_name": c.tournament_name, "edition": c.edition,
                "wiki_title": c.wiki_title}
        if finished:
            if pd.isna(c.start_date):
                continue
            history = history or strength_history()
            strengths, elo_now = history.at(c.start_date)
            mode, as_of = "backtest", c.start_date
        else:
            strengths, elo_now = current[["player_key", "strength"]], elo_latest
            played = any(m.winner for r in draw.rounds for m in r.matches)
            mode, as_of = ("live" if played else "pre-tournament"), pd.Timestamp(today)

        slots = tournament.draw_strengths(draw, players, strengths, elo_now)
        sim = tournament.simulate(draw, slots, fix_played=(mode == "live"))
        seeds = [s for m in draw.rounds[0].matches for s in (m.seed_a, m.seed_b)]
        sim = sim.merge(slots[["slot", "player_key", "strength", "source"]], on="slot")
        sim["seed"] = sim["slot"].map(dict(enumerate(seeds)))
        predictions.append(sim.assign(mode=mode, as_of=as_of, **meta))

        s = dict(zip(slots.player_name, slots.strength))
        for r, rnd in enumerate(draw.rounds):
            for m in rnd.matches:
                p_a = None
                if m.player_a in s and m.player_b in s:
                    p_a = match_probability(1 / (1 + np.exp(-(s[m.player_a] - s[m.player_b]))),
                                            rnd.first_to or 6, rnd.unit or "legs")
                draw_matches.append({**meta, "mode": mode, "round_order": r + 1, "round_name": rnd.name,
                                     "first_to": rnd.first_to, "unit": rnd.unit, "slot": m.slot,
                                     "player_a": m.player_a, "player_b": m.player_b, "seed_a": m.seed_a,
                                     "seed_b": m.seed_b, "score_a": m.score_a, "score_b": m.score_b,
                                     "avg_a": m.avg_a, "avg_b": m.avg_b, "winner": m.winner,
                                     "walkover": m.walkover, "p_a": p_a})
        if finished:
            bt = tournament.backtest_matches(draw, slots)
            bt_matches.append(bt.assign(**meta))
            bt_summary.append(tournament.backtest_summary(bt, sim, draw).assign(**meta))

    out = {}
    if predictions:
        out["tournament_predictions"] = pd.concat(predictions, ignore_index=True)
        out["tournament_draw_matches"] = pd.DataFrame(draw_matches)
    if bt_matches:
        out["tournament_backtest_matches"] = pd.concat(bt_matches, ignore_index=True)
        out["tournament_backtest_summary"] = pd.concat(bt_summary, ignore_index=True)
    return out


UPCOMING_COLUMNS = ["start_time", "event_title", "round_name", "is_major", "player_a_key", "player_a_name",
                    "player_b_key", "player_b_name", "pi_a", "pi_b", "pi_major_a", "pi_major_b",
                    "effective_average_a", "effective_average_b", "avg_l30_a", "avg_l30_b", "form_a", "form_b",
                    "p_a", "h2h_wins_a", "h2h_wins_b"]


def upcoming_cards(upcoming: pd.DataFrame, current: pd.DataFrame, elo_latest: pd.DataFrame,
                   results: pd.DataFrame) -> pd.DataFrame:
    """Cards for scheduled matches: PI of both players, P(A wins) in a typical match, head-to-head.

    current: player_key, strength, pi, pi_major, effective_average, avg_l30, form. results: winner_key, loser_key.
    Untracked players get a strength estimated from their Elo; players without any data the 5th percentile.
    """
    if upcoming.empty:
        return pd.DataFrame(columns=UPCOMING_COLUMNS)
    tracked = current.set_index("player_key")
    slope, intercept = np.polyfit(*current.merge(elo_latest, on="player_key")[["elo", "strength"]].to_numpy().T, 1)
    elo_map = dict(zip(elo_latest.player_key, elo_latest.elo))

    def strength_of(key):
        if key in tracked.index:
            return tracked.at[key, "strength"]
        if key in elo_map:
            return intercept + slope * elo_map[key]
        return current["strength"].quantile(tournament.FALLBACK_QUANTILE)

    wins = results.groupby(["winner_key", "loser_key"]).size().to_dict()
    cards = []
    for u in upcoming.itertuples(index=False):
        sa, sb = strength_of(u.player_a_key), strength_of(u.player_b_key)
        card = {c: getattr(u, c, None) for c in ("start_time", "event_title", "round_name", "is_major",
                                                  "player_a_key", "player_a_name", "player_b_key", "player_b_name")}
        card |= {"p_a": 1 / (1 + np.exp(-(sa - sb))),
                 "h2h_wins_a": wins.get((u.player_a_key, u.player_b_key), 0),
                 "h2h_wins_b": wins.get((u.player_b_key, u.player_a_key), 0)}
        for side, key in (("a", u.player_a_key), ("b", u.player_b_key)):
            for col in ("pi", "pi_major", "effective_average", "avg_l30", "form"):
                card[f"{col}_{side}"] = tracked.at[key, col] if key in tracked.index else None
        cards.append(card)
    return pd.DataFrame(cards)[UPCOMING_COLUMNS]
