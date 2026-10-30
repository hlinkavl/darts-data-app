# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Performance Index (step 3)
# MAGIC Scores every tracked player with the active model version: PI (typical match), PI Major (match on a major),
# MAGIC Effective Average and the contribution of each predictor. Snapshots on the 1st of every month since 2024
# MAGIC give the history; the snapshot after the latest match is flagged `is_current`.

# COMMAND ----------

# MAGIC %pip install -q statsmodels==0.15.0 scikit-learn

# COMMAND ----------

import os
import sys

import pandas as pd

sys.path.append(os.path.abspath(".."))
from analytics import pipeline

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")

# COMMAND ----------

def active_version() -> str:
    """The active model (promotion policy); falls back to the latest fit before the registry existed."""
    if spark.catalog.tableExists("darts_gold.pi_model_registry"):
        rows = spark.sql("SELECT version FROM darts_gold.pi_model_registry WHERE status = 'active' "
                         "ORDER BY decided_at DESC LIMIT 1").collect()
        if rows:
            return rows[0][0]
    return spark.sql("SELECT max(version) FROM darts_gold.pi_coefficients").first()[0]

version = active_version()
coefficients = spark.sql(f"SELECT * FROM darts_gold.pi_coefficients WHERE version = '{version}'").toPandas()
elo_history = spark.sql(f"SELECT * FROM darts_gold.elo_history WHERE version = '{version}'").toPandas()
player_matches = spark.sql("""
    SELECT match_key, player_key, opponent_key, match_date, round, tournament_key, is_major, won,
           points, darts, first9_points, first9_darts, checkouts_hit, checkout_attempts, one_eighties
    FROM darts_silver.player_matches
""").toPandas()
players = spark.sql("SELECT player_key, player_name FROM darts_silver.players WHERE is_tracked").toPandas()

last_match = pd.to_datetime(player_matches["match_date"]).max()
current = last_match + pd.Timedelta(days=1)
as_of_dates = list(pd.date_range("2024-01-01", current, freq="MS")) + [current]
print(f"model {version}, {len(players)} players, {len(as_of_dates)} snapshots, current = {current.date()}")

# COMMAND ----------

rankings = spark.sql("SELECT snapshot_date, player_key, rank FROM darts_silver.rankings").toPandas()
index = pipeline.score(player_matches, elo_history, coefficients, players["player_key"].tolist(), as_of_dates,
                       rankings=rankings)
index = index.merge(players, on="player_key", how="left")
index["is_current"] = index["as_of_date"] == current.normalize()
index["as_of_date"] = pd.to_datetime(index["as_of_date"]).dt.date
index["model_version"] = version

lead = ["as_of_date", "is_current", "player_key", "player_name", "rank", "pi", "rank_major", "pi_major",
        "effective_average", "effective_average_major"]
index = index[lead + [c for c in index.columns if c not in lead]]
spark.createDataFrame(index).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("darts_gold.performance_index")

display(index[index["is_current"]].sort_values("rank").head(20))

# COMMAND ----------

# MAGIC %md ## Recent matches (player profiles: last 5 / last 10)

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE VIEW darts_gold.player_recent_matches AS
SELECT
  m.player_key,
  p.player_name,
  row_number() OVER (PARTITION BY m.player_key ORDER BY m.match_date DESC, m.match_key DESC) AS recency,
  m.match_date, m.tournament_name, m.round, m.is_major,
  m.opponent_key, m.opponent_name,
  IF(m.won, 'W', 'L') AS result,
  concat(m.score_for, '-', m.score_against) AS score,
  m.average, m.first9_average, m.checkout_pct, m.one_eighties
FROM darts_silver.player_matches_v m
JOIN darts_silver.players p ON p.player_key = m.player_key AND p.is_tracked
""")
display(spark.sql("SELECT * FROM darts_gold.player_recent_matches WHERE player_name = 'Luke Littler' AND recency <= 5"))
