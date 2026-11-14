# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Performance Index (step 3)
# MAGIC Scores every tracked player with the active model version: PI (typical match), PI Major (match on a major),
# MAGIC Effective Average and the contribution of each predictor. Snapshots on the 1st of every month since 2024
# MAGIC give the history; the snapshot after the newest data (match or Order of Merit) is flagged `is_current`.

# COMMAND ----------

# MAGIC %pip install -q statsmodels==0.15.0 scikit-learn

# COMMAND ----------

import hashlib
import os
import sys

import pandas as pd

sys.path.append(os.path.abspath(".."))
from analytics import elo, pipeline, titles

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
    SELECT match_key, player_key, opponent_key, match_date, round, tournament_key, is_major, won, category,
           points, darts, first9_points, first9_darts, checkouts_hit, checkout_attempts, one_eighties,
           score_for, score_against
    FROM darts_silver.player_matches
""").toPandas()
players = spark.sql("SELECT player_key, player_name FROM darts_silver.players WHERE is_tracked").toPandas()

rankings = spark.sql("SELECT snapshot_date, player_key, rank FROM darts_silver.rankings").toPandas()

# The current snapshot sees everything up to the newest data of either kind. Since Nov 2026 results arrive only
# from the majors, so weeks can pass without a match while the Order of Merit (rank, momentum) keeps moving.
last_match = pd.to_datetime(player_matches["match_date"]).max()
last_ranking = pd.to_datetime(rankings["snapshot_date"]).max()
current = max(last_match, last_ranking).normalize() + pd.Timedelta(days=1)
as_of_dates = list(pd.date_range("2024-01-01", current, freq="MS")) + [current]
print(f"model {version}, {len(players)} players, {len(as_of_dates)} snapshots, current = {current.date()} "
      f"(last match {last_match.date()}, last ranking {last_ranking.date()})")

# COMMAND ----------

# Monthly snapshots of the past do not change while the model and the tracked players stay the same (each uses
# only matches before its date), so they are reused; the current one and the last RECENT_DAYS days (late results)
# are computed again. A new model version or a change in the tracked players recomputes everything, because the
# reference player (mean of the top 32 in each snapshot) depends on who is scored.
RECENT_DAYS = 7
# Fingerprint of who is scored (players without data drop out of a snapshot, so the table alone can't tell).
tracked_hash = hashlib.sha1(",".join(map(str, sorted(players["player_key"]))).encode()).hexdigest()
reused = pd.DataFrame()
table = "darts_gold.performance_index"
if spark.catalog.tableExists(table) and "tracked_hash" in spark.table(table).columns:
    old_index = spark.sql(f"SELECT * FROM {table} WHERE model_version = '{version}' AND tracked_hash = '{tracked_hash}' "
                          "AND NOT is_current").toPandas()
    if len(old_index):
        keep_before = (current - pd.Timedelta(days=RECENT_DAYS)).normalize()
        reused = old_index[pd.to_datetime(old_index["as_of_date"]) < keep_before]
done = set(pd.to_datetime(reused["as_of_date"])) if len(reused) else set()
to_score = [d for d in as_of_dates if d not in done]
print(f"reusing {len(done)} snapshots, scoring {len(to_score)}")

major_elo_history = None
if "major_elo" in set(coefficients["predictor"]):  # Big-Stage Elo: replayed on the majors with the model's Elo settings
    m = spark.sql(f"SELECT elo_k, elo_major_multiplier FROM darts_gold.pi_model_registry WHERE version = '{version}'").first()
    majors = spark.sql("SELECT match_key, match_date, round, winner_key, loser_key, is_major FROM darts_silver.matches "
                       "WHERE is_major").toPandas()
    major_elo_history = elo.run_elo(majors.assign(match_date=pd.to_datetime(majors["match_date"])),
                                    elo.EloParams(float(m.elo_k), float(m.elo_major_multiplier)))
index = pipeline.score(player_matches, elo_history, coefficients, players["player_key"].tolist(), to_score,
                       rankings=rankings, major_elo_history=major_elo_history)
index = index.merge(players, on="player_key", how="left")
index["is_current"] = index["as_of_date"] == current.normalize()
index["as_of_date"] = pd.to_datetime(index["as_of_date"]).dt.date
index["model_version"] = version
index["tracked_hash"] = tracked_hash
if len(reused):
    reused = reused.assign(as_of_date=pd.to_datetime(reused["as_of_date"]).dt.date)
    index = pd.concat([reused[[c for c in index.columns if c in reused.columns]], index], ignore_index=True)

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
  -- within a day the later round first (fewer players left); match ids don't follow the order of play
  -- (same rule as analytics/rounds.players_left)
  row_number() OVER (PARTITION BY m.player_key ORDER BY m.match_date DESC, CASE
      WHEN lower(m.round) RLIKE 'last *[0-9]+' THEN cast(regexp_extract(lower(m.round), 'last *([0-9]+)', 1) AS INT)
      WHEN lower(m.round) LIKE '%quarter%' THEN 8
      WHEN lower(m.round) LIKE '%semi%' THEN 4
      WHEN lower(m.round) LIKE '%final%' THEN 2
      WHEN lower(m.round) RLIKE '(round|rd) *[0-9]+' THEN 4096 / pow(2, cast(regexp_extract(lower(m.round), '(round|rd) *([0-9]+)', 2) AS INT))
      ELSE 4096 END ASC, m.match_key DESC) AS recency,
  m.match_date, m.tournament_name, m.round, m.is_major,
  m.opponent_key, m.opponent_name,
  IF(m.won, 'W', 'L') AS result,
  concat(m.score_for, '-', m.score_against) AS score,
  m.average, m.first9_average, m.checkout_pct, m.one_eighties
FROM darts_silver.player_matches_v m
JOIN darts_silver.players p ON p.player_key = m.player_key AND p.is_tracked
""")
display(spark.sql("SELECT * FROM darts_gold.player_recent_matches WHERE player_name = 'Luke Littler' AND recency <= 5"))

# COMMAND ----------

# MAGIC %md ## Titles (player profiles: events won since 2021)

# COMMAND ----------

events = spark.sql("""
    SELECT event_date, tournament_name, category, is_major, winner_key, winner_name FROM darts_silver.events
""").toPandas()
spark.createDataFrame(titles.player_titles(events)).write.mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable("darts_gold.player_titles")
