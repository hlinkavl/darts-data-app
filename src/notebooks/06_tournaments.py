# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Tournament Overview
# MAGIC - **Season calendar** of the majors: dates from Wikipedia infoboxes, winners from Orakel.
# MAGIC - **Draws** parsed from Wikipedia. Finished events are **backtested** with strengths as of the start date
# MAGIC   (weights refitted on earlier matches only). Events with a draw that are not finished get **predictions**:
# MAGIC   a Monte Carlo of the draw, with played matches fixed (live bracket).
# MAGIC - **Upcoming matches** from Orakel's feed: PI vs PI, win probability, head-to-head.
# MAGIC Methodology: docs/TOURNAMENT_PREDICTIONS.md.

# COMMAND ----------

# MAGIC %pip install -q statsmodels==0.15.0 scikit-learn

# COMMAND ----------

import os
import sys
from datetime import date

import numpy as np
import pandas as pd
import yaml

sys.path.append(os.path.abspath(".."))
from analytics import bracket, calendar, elo, pipeline, tournament
from analytics.formats import match_probability

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")
today = date.today()

with open("../../config/majors.yml") as f:
    MAJORS = yaml.safe_load(f)["majors"]

# COMMAND ----------

pages = spark.sql("SELECT title, wikitext FROM darts_silver.tournament_pages WHERE error IS NULL").toPandas()
events = spark.sql("SELECT tournament_key, event_date, winner_name, winner_avg FROM darts_silver.events WHERE is_major").toPandas()
players = spark.sql("SELECT player_key, player_name FROM darts_silver.players").toPandas()
current = spark.sql("""
    SELECT player_key, strength_major AS strength, pi, pi_major, effective_average, avg_l30, form
    FROM darts_gold.performance_index WHERE is_current
""").toPandas()
def active_version() -> str:
    """The active model (promotion policy); falls back to the latest fit before the registry existed."""
    if spark.catalog.tableExists("darts_gold.pi_model_registry"):
        rows = spark.sql("SELECT version FROM darts_gold.pi_model_registry WHERE status = 'active' "
                         "ORDER BY decided_at DESC LIMIT 1").collect()
        if rows:
            return rows[0][0]
    return spark.sql("SELECT max(version) FROM darts_gold.pi_coefficients").first()[0]

version = active_version()
elo_history = spark.sql(f"SELECT * FROM darts_gold.elo_history WHERE version = '{version}'").toPandas()
elo_latest = (elo_history.sort_values(["match_date", "match_key"]).groupby("player_key")["elo_post"].last()
              .rename("elo").reset_index())
predictors = spark.sql(f"SELECT predictor FROM darts_gold.pi_coefficients WHERE version = '{version}'").toPandas()["predictor"].tolist()
elo_row = spark.sql(f"SELECT k, major_multiplier FROM darts_gold.pi_elo_tuning WHERE version = '{version}' AND selected").first()
elo_params = elo.EloParams(float(elo_row.k), float(elo_row.major_multiplier))
print(f"model {version}, predictors {predictors}, {elo_params}")

def save(df: pd.DataFrame, table: str) -> None:
    out = df.assign(computed_at=pd.Timestamp.now(tz="UTC"), model_version=version)
    for col in out.columns:  # all-null columns have no type Spark can infer
        if out[col].isna().all():
            out[col] = out[col].astype("string")
    spark.createDataFrame(out).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"darts_gold.{table}")
    print(f"darts_gold.{table}: {len(out)} rows")

# COMMAND ----------

# MAGIC %md ## Season calendar

# COMMAND ----------

rows, draws = [], {}
for page in pages.itertuples():
    found = calendar.match_major(page.title, MAJORS)
    if not found:
        continue
    key, edition = found
    start, end = calendar.infobox_dates(page.wikitext)
    draw = bracket.build_draw(page.title, page.wikitext)
    if draw:
        draws[page.title] = draw
    final_winner = draw.rounds[-1].matches[0].winner if draw else None
    rows.append({"tournament_key": key, "tournament_name": MAJORS[key]["name"], "edition": edition,
                 "wiki_title": page.title, "start_date": pd.Timestamp(start) if start else pd.NaT,
                 "end_date": pd.Timestamp(end) if end else pd.NaT, "has_draw": draw is not None,
                 "winner_name": final_winner, "winner_avg": np.nan})
cal = pd.DataFrame(rows)

# Winners from Orakel (final date within the event dates); majors without a Wikipedia page come from Orakel alone.
events["event_date"] = pd.to_datetime(events["event_date"])
extra = []
for ev in events[events["event_date"] >= pd.Timestamp(today.year - 1, 1, 1)].itertuples():
    hit = cal.index[(cal.tournament_key == ev.tournament_key) & (cal.start_date <= ev.event_date)
                    & (cal.end_date >= ev.event_date)]
    if len(hit):
        if ev.winner_name:
            cal.loc[hit, ["winner_name", "winner_avg"]] = [ev.winner_name, ev.winner_avg]
    else:
        extra.append({"tournament_key": ev.tournament_key, "tournament_name": MAJORS[ev.tournament_key]["name"],
                      "edition": ev.event_date.year, "wiki_title": None, "start_date": pd.NaT,
                      "end_date": ev.event_date, "has_draw": False,
                      "winner_name": ev.winner_name or None, "winner_avg": ev.winner_avg})
cal = pd.concat([cal, pd.DataFrame(extra)], ignore_index=True)

# Majors of the current season with no data yet (no Wikipedia page, not in Orakel's calendar) still get a row.
for key, m in MAJORS.items():
    if not ((cal.tournament_key == key) & (cal.edition == today.year)).any():
        cal.loc[len(cal)] = {"tournament_key": key, "tournament_name": m["name"], "edition": today.year,
                             "wiki_title": m["wiki"].format(year=today.year), "start_date": pd.NaT, "end_date": pd.NaT,
                             "has_draw": False, "winner_name": None, "winner_avg": np.nan}

today_ts = pd.Timestamp(today)
cal["status"] = np.select(
    [cal.end_date.isna(), cal.end_date < today_ts, cal.start_date <= today_ts],
    ["date unknown", "completed", "in progress"], default="upcoming")
cal["season"] = cal["edition"]
cal = cal.sort_values("end_date", na_position="last").reset_index(drop=True)
save(cal, "majors_calendar")
display(cal)

# COMMAND ----------

# MAGIC %md ## Draws: backtests (finished) and predictions (not finished)

# COMMAND ----------

player_matches = spark.sql("""
    SELECT match_key, player_key, opponent_key, match_date, tournament_key, is_major, won,
           points, darts, first9_points, first9_darts, checkouts_hit, checkout_attempts, one_eighties
    FROM darts_silver.player_matches
""").toPandas()
matches = spark.sql("SELECT match_key, match_date, winner_key, loser_key, is_major FROM darts_silver.matches").toPandas()
history = None  # built only if there is something to backtest

draw_matches, predictions, bt_matches, bt_summary = [], [], [], []
for c in cal[cal.has_draw].itertuples():
    draw = draws[c.wiki_title]
    finished = draw.rounds[-1].matches[0].winner is not None
    meta = {"tournament_key": c.tournament_key, "tournament_name": c.tournament_name, "edition": c.edition,
            "wiki_title": c.wiki_title}
    if finished:
        if pd.isna(c.start_date):
            continue
        if history is None:
            history = pipeline.StrengthHistory(player_matches, matches, predictors, elo_params)
        strengths, elo_now = history.at(c.start_date)
        mode, as_of = "backtest", c.start_date
    else:
        strengths, elo_now = current[["player_key", "strength"]], elo_latest
        played = any(m.winner for r in draw.rounds for m in r.matches)
        mode, as_of = ("live" if played else "pre-tournament"), today

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
                p_typ = 1 / (1 + np.exp(-(s[m.player_a] - s[m.player_b])))
                p_a = match_probability(p_typ, rnd.first_to or 6, rnd.unit or "legs")
            draw_matches.append({**meta, "mode": mode, "round_order": r + 1, "round_name": rnd.name,
                                 "first_to": rnd.first_to, "unit": rnd.unit, "slot": m.slot,
                                 "player_a": m.player_a, "player_b": m.player_b, "seed_a": m.seed_a, "seed_b": m.seed_b,
                                 "score_a": m.score_a, "score_b": m.score_b, "avg_a": m.avg_a, "avg_b": m.avg_b,
                                 "winner": m.winner, "walkover": m.walkover, "p_a": p_a})
    if finished:
        bt = tournament.backtest_matches(draw, slots)
        bt_matches.append(bt.assign(**meta))
        bt_summary.append(tournament.backtest_summary(bt, sim, draw).assign(**meta))
    print(f"{c.wiki_title}: {mode}, {len(draw.players)} players")

if predictions:
    save(pd.concat(predictions, ignore_index=True), "tournament_predictions")
    save(pd.DataFrame(draw_matches), "tournament_draw_matches")
if bt_matches:
    save(pd.concat(bt_matches, ignore_index=True), "tournament_backtest_matches")
    summary = pd.concat(bt_summary, ignore_index=True)
    save(summary, "tournament_backtest_summary")
    display(summary)

# COMMAND ----------

# MAGIC %md ## Upcoming matches (Orakel feed)

# COMMAND ----------

if spark.catalog.tableExists("darts_silver.upcoming_matches"):
    up = spark.table("darts_silver.upcoming_matches").toPandas()
    tracked = current.set_index("player_key")
    slope, intercept = np.polyfit(*current.merge(elo_latest, on="player_key")[["elo", "strength"]].to_numpy().T, 1)
    elo_map = dict(zip(elo_latest.player_key, elo_latest.elo))

    def strength_of(key):
        if key in tracked.index:
            return tracked.at[key, "strength"], "pi_model"
        if key in elo_map:
            return intercept + slope * elo_map[key], "elo_estimate"
        return current["strength"].quantile(tournament.FALLBACK_QUANTILE), "fallback"

    h2h = spark.sql("SELECT winner_key, loser_key FROM darts_silver.matches").toPandas()
    wins = h2h.groupby(["winner_key", "loser_key"]).size().to_dict()
    cards = []
    for u in up.itertuples():
        sa, src_a = strength_of(u.player_a_key)
        sb, src_b = strength_of(u.player_b_key)
        card = {**u._asdict(), "strength_a": sa, "strength_b": sb, "source_a": src_a, "source_b": src_b,
                "p_a": 1 / (1 + np.exp(-(sa - sb))),
                "h2h_wins_a": wins.get((u.player_a_key, u.player_b_key), 0),
                "h2h_wins_b": wins.get((u.player_b_key, u.player_a_key), 0)}
        for side, key in (("a", u.player_a_key), ("b", u.player_b_key)):
            for col in ("pi", "pi_major", "effective_average", "avg_l30", "form"):
                card[f"{col}_{side}"] = tracked.at[key, col] if key in tracked.index else None
        cards.append(card)
    cards = pd.DataFrame(cards).drop(columns=["Index"], errors="ignore")
    if len(cards):
        save(cards, "upcoming_matches")
        display(cards)
        UPCOMING_DONE = True

if not globals().get("UPCOMING_DONE"):
    # Nothing scheduled: replace the table with an empty one, so old cards never linger.
    spark.sql("""
        CREATE OR REPLACE TABLE darts_gold.upcoming_matches (
          start_time TIMESTAMP, event_title STRING, round_name STRING, is_major BOOLEAN,
          player_a_key BIGINT, player_a_name STRING, player_b_key BIGINT, player_b_name STRING,
          pi_a DOUBLE, pi_b DOUBLE, pi_major_a DOUBLE, pi_major_b DOUBLE,
          effective_average_a DOUBLE, effective_average_b DOUBLE, avg_l30_a DOUBLE, avg_l30_b DOUBLE,
          form_a DOUBLE, form_b DOUBLE, p_a DOUBLE, h2h_wins_a BIGINT, h2h_wins_b BIGINT,
          computed_at TIMESTAMP, model_version STRING)""")
    print("no upcoming matches in the feed: darts_gold.upcoming_matches is empty")
