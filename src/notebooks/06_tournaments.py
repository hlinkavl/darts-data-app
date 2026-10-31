# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Tournament Overview
# MAGIC - **Season calendar** of the majors: dates from Wikipedia infoboxes, winners from Orakel.
# MAGIC - **Draws** parsed from Wikipedia. Finished events are **backtested** with strengths as of the start date
# MAGIC   (weights refitted on earlier matches only). Events with a draw that are not finished get **predictions**:
# MAGIC   a Monte Carlo of the draw, with played matches fixed (live bracket).
# MAGIC - **Upcoming matches** from the Mastercaller match center: PI vs PI, win probability, head-to-head.
# MAGIC The logic lives in src/analytics/overview.py (also used for the local app snapshot).
# MAGIC Methodology: docs/TOURNAMENT_PREDICTIONS.md.

# COMMAND ----------

# MAGIC %pip install -q statsmodels==0.15.0 scikit-learn

# COMMAND ----------

import os
import sys
from datetime import date

import pandas as pd
import yaml

sys.path.append(os.path.abspath(".."))
from analytics import elo, overview, pipeline

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

cal, draws = overview.season_calendar(pages, events, MAJORS, today)
save(cal, "majors_calendar")
display(cal)

# COMMAND ----------

# MAGIC %md ## Draws: backtests (finished) and predictions (not finished)

# COMMAND ----------

player_matches = spark.sql("""
    SELECT match_key, player_key, opponent_key, match_date, round, tournament_key, is_major, won,
           points, darts, first9_points, first9_darts, checkouts_hit, checkout_attempts, one_eighties
    FROM darts_silver.player_matches
""").toPandas()
matches = spark.sql("SELECT match_key, match_date, round, winner_key, loser_key, is_major FROM darts_silver.matches").toPandas()
rankings = spark.sql("SELECT snapshot_date, player_key, rank FROM darts_silver.rankings").toPandas()

outputs = overview.draw_outputs(
    cal, draws, players, current, elo_latest,
    strength_history=lambda: pipeline.StrengthHistory(player_matches, matches, predictors, elo_params, rankings=rankings),
    today=today)
for table, df in outputs.items():
    save(df, table)
if "tournament_backtest_summary" in outputs:
    display(outputs["tournament_backtest_summary"])

# COMMAND ----------

# MAGIC %md ## Upcoming matches (Mastercaller match center)

# COMMAND ----------

up = (spark.table("darts_silver.upcoming_matches").toPandas() if spark.catalog.tableExists("darts_silver.upcoming_matches")
      else pd.DataFrame(columns=["player_a_key", "player_b_key"]))
cards = overview.upcoming_cards(up, current, elo_latest, matches[["winner_key", "loser_key"]])
if len(cards):
    save(cards, "upcoming_matches")
    display(cards)
else:
    # Nothing scheduled: replace the table with an empty one, so old cards never linger.
    spark.sql("""
        CREATE OR REPLACE TABLE darts_gold.upcoming_matches (
          start_time TIMESTAMP, event_title STRING, round_name STRING, is_major BOOLEAN,
          player_a_key BIGINT, player_a_name STRING, player_b_key BIGINT, player_b_name STRING,
          pi_a DOUBLE, pi_b DOUBLE, pi_major_a DOUBLE, pi_major_b DOUBLE,
          effective_average_a DOUBLE, effective_average_b DOUBLE, avg_l30_a DOUBLE, avg_l30_b DOUBLE,
          form_a DOUBLE, form_b DOUBLE, p_a DOUBLE, h2h_wins_a BIGINT, h2h_wins_b BIGINT,
          computed_at TIMESTAMP, model_version STRING)""")
    print("no upcoming matches: darts_gold.upcoming_matches is empty")
