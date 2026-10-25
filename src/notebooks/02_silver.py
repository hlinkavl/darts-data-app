# Databricks notebook source
# MAGIC %md
# MAGIC # Silver: clean, typed, one row per entity
# MAGIC The Orakel `player_key` is the canonical player ID. Wikipedia background was matched to it at ingestion,
# MAGIC so all sources join on `player_key`. Ingestion is incremental, so entities are deduplicated across runs
# MAGIC (newest run wins); the current ranking comes from the latest run only.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")

# Event categories (Orakel codes) treated as "big stage": World Championship, majors, World Grand Prix,
# Premier League. See docs/DESIGN.md.
BIG_STAGE = "('WC', 'MJ', 'WGP', 'U')"

def latest(table: str) -> str:
    """Rows of the most recent run only (full snapshots such as the ranking)."""
    return f"(SELECT * FROM darts_bronze.{table} WHERE _run_date = (SELECT max(_run_date) FROM darts_bronze.{table}))"

def dedup(table: str, key: str) -> str:
    """Newest version of each key across all runs (incremental datasets)."""
    return f"(SELECT * FROM darts_bronze.{table} QUALIFY row_number() OVER (PARTITION BY {key} ORDER BY _run_date DESC) = 1)"

# COMMAND ----------

# MAGIC %md ## events

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.events AS
SELECT DISTINCT
  event_key,
  tournament_key,
  tournament_name,
  to_date(event_date) AS event_date,
  to_date(start_date) AS start_date,
  to_date(end_date) AS end_date,
  category,
  currency_code,
  try_cast(regexp_replace(prize_fund, ',', '') AS BIGINT) AS prize_fund,
  event_avg,
  winner_avg,
  player_key AS winner_key,
  winner_name,
  category IN {BIG_STAGE} AS is_big_stage
FROM {dedup("orakel_events", "event_key")}
""")

# COMMAND ----------

# MAGIC %md ## player_matches (one row per player per match, stats pivoted)

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.player_matches AS
WITH m AS (SELECT * FROM {dedup("orakel_matches", "match_key, player_key, stat_name")} WHERE is_bye = 0)
SELECT
  match_key,
  player_key,
  any_value(IF(player_key = winner_key, loser_key, winner_key)) AS opponent_key,
  any_value(IF(player_key = winner_key, loser_name, winner_name)) AS opponent_name,
  any_value(to_date(match_date)) AS match_date,
  any_value(event_key) AS event_key,
  any_value(tournament_key) AS tournament_key,
  any_value(tournament_name) AS tournament_name,
  any_value(round) AS round,
  any_value(category) AS category,
  any_value(category IN {BIG_STAGE}) AS is_big_stage,
  any_value(player_key = winner_key) AS won,
  any_value(IF(player_key = winner_key, winner_score, loser_score)) AS score_for,
  any_value(IF(player_key = winner_key, loser_score, winner_score)) AS score_against,
  max(IF(stat_name = 'average', stat1, NULL)) AS points,
  max(IF(stat_name = 'average', stat2, NULL)) AS darts,
  max(IF(stat_name = 'first9_average', stat1, NULL)) AS first9_points,
  max(IF(stat_name = 'first9_average', stat2, NULL)) AS first9_darts,
  max(IF(stat_name = 'checkout_pct', stat1, NULL)) AS checkouts_hit,
  max(IF(stat_name = 'checkout_pct', stat2, NULL)) AS checkout_attempts,
  max(IF(stat_name = '180s', stat1, NULL)) AS one_eighties
FROM m
GROUP BY match_key, player_key
""")

spark.sql("""
CREATE OR REPLACE VIEW darts_silver.player_matches_v AS
SELECT
  *,
  round(3 * points / nullif(darts, 0), 2) AS average,
  round(3 * first9_points / nullif(first9_darts, 0), 2) AS first9_average,
  round(100 * checkouts_hit / nullif(checkout_attempts, 0), 2) AS checkout_pct
FROM darts_silver.player_matches
""")

# COMMAND ----------

# MAGIC %md ## matches (one row per match)

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.matches AS
SELECT
  match_key,
  any_value(to_date(match_date)) AS match_date,
  any_value(event_key) AS event_key,
  any_value(tournament_name) AS tournament_name,
  any_value(round) AS round,
  any_value(category) AS category,
  any_value(category IN {BIG_STAGE}) AS is_big_stage,
  any_value(winner_key) AS winner_key,
  any_value(winner_name) AS winner_name,
  any_value(loser_key) AS loser_key,
  any_value(loser_name) AS loser_name,
  any_value(winner_score) AS winner_score,
  any_value(loser_score) AS loser_score
FROM {dedup("orakel_matches", "match_key, player_key, stat_name")}
WHERE is_bye = 0
GROUP BY match_key
""")

# COMMAND ----------

# MAGIC %md ## players (tracked players + every opponent they faced)

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.players AS
WITH tracked AS (
  SELECT
    player_key, player_name, country, to_date(dob) AS date_of_birth,
    try_cast(regexp_replace(sum_prize_money, ',', '') AS BIGINT) AS prize_money_2y,
    rank AS prize_money_rank, tot_events
  FROM {latest("orakel_rankings")}
),
opponents AS (
  SELECT winner_key AS player_key, winner_name AS player_name FROM darts_silver.matches
  UNION
  SELECT loser_key, loser_name FROM darts_silver.matches
),
wiki AS (
  SELECT
    player_key, wikidata_id, enwiki_title, description, intro,
    nickname[0] AS nickname, image[0] AS image_file, citizenship[0] AS citizenship_qid
  FROM {dedup("wiki_player_background", "player_key")}
)
SELECT
  coalesce(t.player_key, o.player_key) AS player_key,
  coalesce(t.player_name, o.player_name) AS player_name,
  t.country, t.date_of_birth, t.prize_money_2y, t.prize_money_rank, t.tot_events,
  t.player_key IS NOT NULL AS is_tracked,
  w.nickname, w.wikidata_id, w.enwiki_title, w.description, w.intro, w.image_file, w.citizenship_qid
FROM tracked t
FULL OUTER JOIN (SELECT player_key, any_value(player_name) AS player_name FROM opponents GROUP BY player_key) o
  ON t.player_key = o.player_key
LEFT JOIN wiki w ON w.player_key = coalesce(t.player_key, o.player_key)
""")

# COMMAND ----------

# MAGIC %md ## rankings (snapshot history) and tournament pages

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE darts_silver.rankings AS
SELECT DISTINCT
  to_date(left(_run_date, 10)) AS snapshot_date,
  rank,
  player_key,
  player_name,
  try_cast(regexp_replace(sum_prize_money, ',', '') AS BIGINT) AS prize_money_2y
FROM darts_bronze.orakel_rankings
""")

spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.tournament_pages AS
SELECT title, revid, wikitext, error, to_date(left(_run_date, 10)) AS fetched_on
FROM {dedup("wiki_tournament_pages", "title")}
""")

for t in ["events", "player_matches", "matches", "players", "rankings", "tournament_pages"]:
    print(t, spark.table(f"darts_silver.{t}").count())
