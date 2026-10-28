# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Performance Index (step 3)
# MAGIC Scores every tracked player with the latest model version: PI (typical match), PI Major (match on a major),
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

version = spark.sql("SELECT max(version) FROM darts_gold.pi_coefficients").first()[0]
coefficients = spark.sql(f"SELECT * FROM darts_gold.pi_coefficients WHERE version = '{version}'").toPandas()
elo_history = spark.table("darts_gold.elo_history").toPandas()
player_matches = spark.sql("""
    SELECT match_key, player_key, opponent_key, match_date, tournament_key, is_major, won,
           points, darts, first9_points, first9_darts, checkouts_hit, checkout_attempts, one_eighties
    FROM darts_silver.player_matches
""").toPandas()
players = spark.sql("SELECT player_key, player_name FROM darts_silver.players WHERE is_tracked").toPandas()

last_match = pd.to_datetime(player_matches["match_date"]).max()
current = last_match + pd.Timedelta(days=1)
as_of_dates = list(pd.date_range("2024-01-01", current, freq="MS")) + [current]
print(f"model {version}, {len(players)} players, {len(as_of_dates)} snapshots, current = {current.date()}")

# COMMAND ----------

index = pipeline.score(player_matches, elo_history, coefficients, players["player_key"].tolist(), as_of_dates)
index = index.merge(players, on="player_key", how="left")
index["is_current"] = index["as_of_date"] == current.normalize()
index["as_of_date"] = pd.to_datetime(index["as_of_date"]).dt.date
index["model_version"] = version

lead = ["as_of_date", "is_current", "player_key", "player_name", "rank", "pi", "rank_major", "pi_major",
        "effective_average", "effective_average_major"]
index = index[lead + [c for c in index.columns if c not in lead]]
spark.createDataFrame(index).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("darts_gold.performance_index")

display(index[index["is_current"]].sort_values("rank").head(20))
