# Databricks notebook source
# MAGIC %md
# MAGIC # Data quality checks (silver)
# MAGIC Hard checks fail the job run; soft checks are reported only.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")

def scalar(sql: str):
    return spark.sql(sql).first()[0]

HARD = {
    "player_matches has rows":
        "SELECT count(*) > 0 FROM darts_silver.player_matches",
    "no duplicate (match_key, player_key)":
        "SELECT count(*) = count(DISTINCT match_key, player_key) FROM darts_silver.player_matches",
    "no duplicate match_key":
        "SELECT count(*) = count(DISTINCT match_key) FROM darts_silver.matches",
    "winner differs from loser":
        "SELECT count_if(winner_key = loser_key) = 0 FROM darts_silver.matches",
    "averages within 30-140":
        "SELECT count_if(average NOT BETWEEN 30 AND 140) = 0 FROM darts_silver.player_matches_v",
    "checkouts hit <= attempts":
        "SELECT count_if(checkouts_hit > checkout_attempts) = 0 FROM darts_silver.player_matches",
    "players contains tracked players":
        "SELECT count_if(NOT is_tracked) < count(*) FROM darts_silver.players",
}

SOFT = {
    "matches without average stats (%)":
        "SELECT round(100 * count_if(darts IS NULL) / count(*), 2) FROM darts_silver.player_matches",
    "tracked players without matches":
        """SELECT count(*) FROM darts_silver.players p
           WHERE is_tracked AND NOT EXISTS (SELECT 1 FROM darts_silver.player_matches m WHERE m.player_key = p.player_key)""",
    "tracked players matched to Wikidata (%)":
        "SELECT round(100 * count_if(wikidata_id IS NOT NULL) / count(*), 1) FROM darts_silver.players WHERE is_tracked",
    "player_matches rows": "SELECT count(*) FROM darts_silver.player_matches",
    "matches rows": "SELECT count(*) FROM darts_silver.matches",
    "date range": "SELECT concat(min(match_date), ' .. ', max(match_date)) FROM darts_silver.matches",
}

# COMMAND ----------

failures = [name for name, sql in HARD.items() if not scalar(sql)]
for name in HARD:
    print(("FAIL " if name in failures else "ok   ") + name)
for name, sql in SOFT.items():
    print(f"info {name}: {scalar(sql)}")

if failures:
    raise AssertionError(f"Data quality checks failed: {failures}")
