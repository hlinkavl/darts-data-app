# Databricks notebook source
# MAGIC %md
# MAGIC # Silver: clean, typed, one row per entity, all sources unified
# MAGIC - **Results:** Darts Orakel until 28 Oct 2026 (exact points and darts, detailed stats), Mastercaller until
# MAGIC   9 Nov 2026 (3-dart averages; darts estimated from legs), both kept as history. Since then the majors from the
# MAGIC   Wikipedia draws (score and 3-dart averages per match). Matches present in two sources come from the older one.
# MAGIC - **Players:** one `player_key` across sources. Orakel keys are kept; Mastercaller and Wikipedia names are
# MAGIC   matched to them in `player_crosswalk` (manual fixes: config/player_aliases.yml); new players get a stable new key.
# MAGIC - **Tracked players and rankings:** the official PDC Order of Merit (Wikipedia data module), top 150.
# MAGIC Ingestion is incremental, so entities are deduplicated across runs (newest run wins).

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")

import hashlib
import os
import re
import sys
import unicodedata

import pandas as pd
import yaml

sys.path.append(os.path.abspath(".."))  # src/, for the shared analytics package
from analytics import wiki_results

with open("../../config/majors.yml") as f:
    MAJORS = yaml.safe_load(f)["majors"]  # {tournament_key: {name, wiki, mastercaller}}
with open("../../config/mastercaller_series.yml") as f:
    SERIES = yaml.safe_load(f)
ALIASES = {}
if os.path.exists("../../config/player_aliases.yml"):
    with open("../../config/player_aliases.yml") as f:
        ALIASES = yaml.safe_load(f) or {}

MAJOR_KEYS = "(" + ", ".join(str(k) for k in MAJORS) + ")"
TRACKED_PLAYERS = 150
ESTIMATED_LEGS_PER_SET = 4.0        # sets are first to 3 legs
DARTS_PER_LEG_AT_AVG = 1503.0       # darts per leg ~ 3 * 501 / average (validated on Orakel data, docs/MAINTENANCE.md, section 8)
NEW_KEY_BASE = 900_000_000          # keys for players unknown to Orakel
MC_KEY_BASE = 1_000_000_000_000     # match/event keys for Mastercaller rows (Orakel keys are < 10^7)
WIKI_KEY_BASE = 2_000_000_000_000   # match/event keys for results from Wikipedia draws

def has(table: str) -> bool:
    return spark.catalog.tableExists(f"darts_bronze.{table}")

def latest(table: str) -> str:
    """Rows of the most recent run only (full snapshots such as the ranking)."""
    return f"(SELECT * FROM darts_bronze.{table} WHERE _run_date = (SELECT max(_run_date) FROM darts_bronze.{table}))"

def unescape(col: str) -> str:
    """Orakel names are HTML-escaped in older runs (e.g. O&#039;Connor)."""
    return f"replace(replace(replace({col}, '&#039;', \"'\"), '&quot;', '\"'), '&amp;', '&')"

def dedup(table: str, key: str) -> str:
    """Newest version of each key across all runs (incremental datasets)."""
    return f"(SELECT * FROM darts_bronze.{table} QUALIFY row_number() OVER (PARTITION BY {key} ORDER BY _run_date DESC) = 1)"

def sql_map(mapping: dict, col: str, default: str = "NULL") -> str:
    cases = " ".join(f"WHEN '{k}' THEN {v}" for k, v in mapping.items())
    return f"(CASE {col} {cases} ELSE {default} END)" if mapping else default

SERIES_MAJOR = {m["mastercaller"]: int(k) for k, m in MAJORS.items() if m.get("mastercaller")}
SERIES_CATEGORY = {s: "'PT'" for s in SERIES.get("players_championship", [])}
SERIES_CATEGORY |= {s: "'ET'" for s in SERIES.get("european_tour", [])}
SERIES_CATEGORY |= {s: "'WS'" for s in SERIES.get("world_series", [])}
SERIES_CATEGORY |= {s: "'MJ'" for s in SERIES_MAJOR}

# COMMAND ----------

# MAGIC %md ## Orakel (until 28 Oct 2026)

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW o_player_matches AS
WITH m AS (SELECT * FROM {dedup("orakel_matches", "match_key, player_key, stat_name")} WHERE is_bye = 0),
pivoted AS (
SELECT
  match_key,
  player_key,
  any_value(IF(player_key = winner_key, loser_key, winner_key)) AS opponent_key,
  any_value({unescape('IF(player_key = winner_key, loser_name, winner_name)')}) AS opponent_name,
  any_value(to_date(match_date)) AS match_date,
  any_value(event_key) AS event_key,
  any_value(tournament_key) AS tournament_key,
  any_value({unescape('tournament_name')}) AS tournament_name,
  any_value(round) AS round,
  any_value(category) AS category,
  any_value(tournament_key IN {MAJOR_KEYS}) AS is_major,
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
)
-- The source has a handful of impossible values (~0.01 %): checkouts hit > attempts, averages outside 30-140.
-- Keep the match, drop only the broken stat.
SELECT
  * EXCEPT (points, darts, checkouts_hit, checkout_attempts),
  IF(3 * points / nullif(darts, 0) BETWEEN 30 AND 140, points, NULL) AS points,
  IF(3 * points / nullif(darts, 0) BETWEEN 30 AND 140, darts, NULL) AS darts,
  IF(checkouts_hit <= checkout_attempts, checkouts_hit, NULL) AS checkouts_hit,
  IF(checkouts_hit <= checkout_attempts, checkout_attempts, NULL) AS checkout_attempts,
  'orakel' AS source,
  false AS stats_estimated
FROM pivoted
""")

spark.sql(f"""
CREATE OR REPLACE TEMP VIEW o_matches AS
SELECT
  match_key,
  any_value(to_date(match_date)) AS match_date,
  any_value(event_key) AS event_key,
  any_value(tournament_key) AS tournament_key,
  any_value({unescape('tournament_name')}) AS tournament_name,
  any_value(round) AS round,
  any_value(category) AS category,
  any_value(tournament_key IN {MAJOR_KEYS}) AS is_major,
  any_value(winner_key) AS winner_key,
  any_value({unescape('winner_name')}) AS winner_name,
  any_value(loser_key) AS loser_key,
  any_value({unescape('loser_name')}) AS loser_name,
  any_value(winner_score) AS winner_score,
  any_value(loser_score) AS loser_score,
  'orakel' AS source
FROM {dedup("orakel_matches", "match_key, player_key, stat_name")}
WHERE is_bye = 0
GROUP BY match_key
""")
ORAKEL_LAST_DATE = spark.sql("SELECT max(match_date) FROM o_matches").first()[0]
print("Orakel data until", ORAKEL_LAST_DATE)

# COMMAND ----------

# MAGIC %md ## Wikipedia draws of the majors (results since the historical sources end)

# COMMAND ----------

HISTORY_END = ORAKEL_LAST_DATE
if has("mastercaller_results"):
    HISTORY_END = max(HISTORY_END, spark.sql("SELECT max(to_date(match_date)) FROM darts_bronze.mastercaller_results").first()[0])
pages = spark.sql(f"SELECT title, wikitext FROM {dedup('wiki_tournament_pages', 'title')} WHERE error IS NULL").toPandas()
wk = wiki_results.draw_results(pages, {int(k): v for k, v in MAJORS.items()}, after=HISTORY_END)
print(f"history until {HISTORY_END}; Wikipedia draws after it: {wk['wiki_title'].nunique()} events, "
      f"{int(wk['played'].sum())} played and {int((~wk['played']).sum())} open matches")

# COMMAND ----------

# MAGIC %md ## Player crosswalk (one player_key across sources)

# COMMAND ----------

SPECIAL_LETTERS = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss"})

def norm(name: str) -> str:
    """Letters Unicode does not decompose (ł, ø, ß) are mapped first, so Białecki = Bialecki."""
    ascii_name = unicodedata.normalize("NFKD", (name or "").translate(SPECIAL_LETTERS)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", ascii_name.lower()).strip()

def new_key(normalized: str) -> int:
    return NEW_KEY_BASE + int(hashlib.sha1(normalized.encode()).hexdigest()[:6], 16)

orakel_names = spark.sql("""
    SELECT player_key, player_name, count(*) AS n FROM (
      SELECT winner_key AS player_key, winner_name AS player_name FROM o_matches
      UNION ALL SELECT loser_key, loser_name FROM o_matches)
    GROUP BY ALL
""").toPandas().sort_values("n", ascending=False)
by_norm = {}
for r in orakel_names.itertuples():        # most matches first: on a name clash the regular player wins
    by_norm.setdefault(norm(r.player_name), int(r.player_key))
alias_slug = {k: int(v) for k, v in (ALIASES.get("mastercaller") or {}).items()}
alias_name = {norm(k): int(v) for k, v in (ALIASES.get("names") or {}).items()}

def resolve(name: str, extra: str | None = None, slug: str | None = None) -> tuple[int, str]:
    if slug and slug in alias_slug:
        return alias_slug[slug], "alias"
    for candidate in (name, extra):
        n = norm(candidate or "")
        if n in alias_name:
            return alias_name[n], "alias"
        if n and n in by_norm:
            return by_norm[n], "orakel_name"
    return new_key(norm(name)), "new"

rows = []
if has("mastercaller_results"):
    mc_players = spark.sql("""
        SELECT player_a_slug AS slug, player_a_name AS name FROM darts_bronze.mastercaller_results
        UNION SELECT player_b_slug, player_b_name FROM darts_bronze.mastercaller_results
    """ + ("""
        UNION SELECT player_a_slug, player_a_name FROM darts_bronze.mastercaller_upcoming
        UNION SELECT player_b_slug, player_b_name FROM darts_bronze.mastercaller_upcoming
    """ if has("mastercaller_upcoming") else "")).toPandas().drop_duplicates("slug")
    for r in mc_players.itertuples():
        key, method = resolve(r.name, r.slug.replace("-", " "), r.slug)
        rows.append(("mastercaller", r.slug, r.name, key, method))
wiki_names = set()
for t in ("wiki_rankings", "wiki_rankings_history"):
    if has(t):
        wiki_names |= set(spark.table(f"darts_bronze.{t}").select("player_name").distinct().toPandas()["player_name"])
wiki_names |= set(wk["player_a"]) | set(wk["player_b"])  # draws include qualifiers outside the Order of Merit
mc_by_norm = {norm(r[2]): r[3] for r in rows}
for name in sorted(wiki_names):
    key, method = resolve(name)
    if method == "new" and norm(name) in mc_by_norm:
        key, method = mc_by_norm[norm(name)], "mastercaller_name"
    rows.append(("wikipedia", name, name, key, method))

crosswalk = pd.DataFrame(rows, columns=["source", "source_id", "source_name", "player_key", "match_method"])
spark.createDataFrame(crosswalk, "source STRING, source_id STRING, source_name STRING, player_key BIGINT, match_method STRING") \
    .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("darts_silver.player_crosswalk")
spark.table("darts_silver.player_crosswalk").createOrReplaceTempView("xw")
print(crosswalk.groupby(["source", "match_method"]).size())

# COMMAND ----------

# MAGIC %md ## Mastercaller (from Oct 2026): same shape as Orakel, darts estimated from legs

# COMMAND ----------

if has("mastercaller_results"):
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW mc AS
    WITH r AS (
      SELECT * FROM {dedup("mastercaller_results", "series, edition, round, player_a_slug, player_b_slug")}
      WHERE score_a IS NOT NULL AND score_b IS NOT NULL AND score_a <> score_b
    )
    SELECT
      r.*,
      {MC_KEY_BASE} + pmod(xxhash64(series, edition, round, player_a_slug, player_b_slug), {MC_KEY_BASE}) AS match_key,
      {MC_KEY_BASE} + pmod(xxhash64(series, edition), {MC_KEY_BASE}) AS event_key,
      {sql_map(SERIES_MAJOR, 'series')} AS tournament_key,
      {sql_map(SERIES_CATEGORY, 'series', "'OTHER'")} AS category,
      to_date(match_date) AS m_date,
      (score_a + score_b) * IF(unit = 'sets', {ESTIMATED_LEGS_PER_SET}, 1.0) AS legs,
      xa.player_key AS key_a, xb.player_key AS key_b
    FROM r
    JOIN xw xa ON xa.source = 'mastercaller' AND xa.source_id = r.player_a_slug
    JOIN xw xb ON xb.source = 'mastercaller' AND xb.source_id = r.player_b_slug
    """)

    side = lambda me, op: f"""
      SELECT match_key, key_{me} AS player_key, key_{op} AS opponent_key, player_{op}_name AS opponent_name,
        m_date AS match_date, event_key, tournament_key, tournament AS tournament_name, round, category,
        tournament_key IS NOT NULL AS is_major, score_{me} > score_{op} AS won,
        score_{me} AS score_for, score_{op} AS score_against,
        IF(avg_{me} BETWEEN 30 AND 140, avg_{me} / 3 * legs * {DARTS_PER_LEG_AT_AVG} / avg_{me}, NULL) AS points,
        IF(avg_{me} BETWEEN 30 AND 140, legs * {DARTS_PER_LEG_AT_AVG} / avg_{me}, NULL) AS darts
      FROM mc"""
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW mc_player_matches AS
    SELECT s.match_key, s.player_key, s.opponent_key, s.opponent_name, s.match_date, s.event_key, s.tournament_key,
           s.tournament_name, s.round, s.category, s.is_major, s.won, s.score_for, s.score_against,
           CAST(NULL AS DOUBLE) AS first9_points, CAST(NULL AS DOUBLE) AS first9_darts,
           CAST(NULL AS DOUBLE) AS one_eighties, s.points, s.darts,
           CAST(NULL AS DOUBLE) AS checkouts_hit, CAST(NULL AS DOUBLE) AS checkout_attempts,
           'mastercaller' AS source, true AS stats_estimated
    FROM ({side('a', 'b')} UNION ALL {side('b', 'a')}) s
    -- matches Orakel already has (same day, same two players) come from Orakel
    LEFT ANTI JOIN o_player_matches o
      ON o.match_date = s.match_date AND o.player_key = s.player_key AND o.opponent_key = s.opponent_key
    """)
    spark.sql("""
    CREATE OR REPLACE TEMP VIEW mc_matches AS
    SELECT match_key, m_date AS match_date, event_key, tournament_key, tournament AS tournament_name, round, category,
           tournament_key IS NOT NULL AS is_major,
           IF(score_a > score_b, key_a, key_b) AS winner_key, IF(score_a > score_b, player_a_name, player_b_name) AS winner_name,
           IF(score_a > score_b, key_b, key_a) AS loser_key, IF(score_a > score_b, player_b_name, player_a_name) AS loser_name,
           greatest(score_a, score_b) AS winner_score, least(score_a, score_b) AS loser_score, 'mastercaller' AS source
    FROM mc
    WHERE match_key IN (SELECT match_key FROM mc_player_matches)
    """)
else:
    spark.sql("CREATE OR REPLACE TEMP VIEW mc_player_matches AS SELECT * FROM o_player_matches WHERE false")
    spark.sql("CREATE OR REPLACE TEMP VIEW mc_matches AS SELECT * FROM o_matches WHERE false")

# COMMAND ----------

# MAGIC %md ## Wikipedia results: same shape, darts estimated from legs like Mastercaller

# COMMAND ----------

WK_SCHEMA = ("wiki_title STRING, tournament_key BIGINT, tournament_name STRING, edition INT, event_start DATE, "
             "event_end DATE, round STRING, round_order INT, first_to INT, unit STRING, match_date DATE, "
             "player_a STRING, player_b STRING, score_a DOUBLE, score_b DOUBLE, avg_a DOUBLE, avg_b DOUBLE, played BOOLEAN, "
             "is_final BOOLEAN")
# plain Python values for Spark (numpy scalars and NaN are not accepted for typed columns)
wk_records = [{k: (None if v is None or (isinstance(v, float) and v != v) else v.item() if hasattr(v, "item") else v)
               for k, v in r.items()} for r in wk.astype(object).to_dict("records")]
spark.createDataFrame(wk_records, WK_SCHEMA).createOrReplaceTempView("wk_all")
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW wk AS
SELECT
  w.* EXCEPT (score_a, score_b), CAST(w.score_a AS INT) AS score_a, CAST(w.score_b AS INT) AS score_b,
  {WIKI_KEY_BASE} + pmod(xxhash64(wiki_title, round, player_a, player_b), {MC_KEY_BASE}) AS match_key,
  {WIKI_KEY_BASE} + pmod(xxhash64(wiki_title), {MC_KEY_BASE}) AS event_key,
  (w.score_a + w.score_b) * IF(unit = 'sets', {ESTIMATED_LEGS_PER_SET}, 1.0) AS legs,
  xa.player_key AS key_a, xb.player_key AS key_b
FROM wk_all w
JOIN xw xa ON xa.source = 'wikipedia' AND xa.source_id = w.player_a
JOIN xw xb ON xb.source = 'wikipedia' AND xb.source_id = w.player_b
""")
wk_side = lambda me, op: f"""
  SELECT match_key, key_{me} AS player_key, key_{op} AS opponent_key, player_{op} AS opponent_name,
    match_date, event_key, tournament_key, tournament_name, round, 'MJ' AS category, true AS is_major,
    score_{me} > score_{op} AS won, score_{me} AS score_for, score_{op} AS score_against,
    IF(avg_{me} BETWEEN 30 AND 140, avg_{me} / 3 * legs * {DARTS_PER_LEG_AT_AVG} / avg_{me}, NULL) AS points,
    IF(avg_{me} BETWEEN 30 AND 140, legs * {DARTS_PER_LEG_AT_AVG} / avg_{me}, NULL) AS darts
  FROM wk WHERE played"""
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW wk_player_matches AS
SELECT s.match_key, s.player_key, s.opponent_key, s.opponent_name, s.match_date, s.event_key, s.tournament_key,
       s.tournament_name, s.round, s.category, s.is_major, s.won, s.score_for, s.score_against,
       CAST(NULL AS DOUBLE) AS first9_points, CAST(NULL AS DOUBLE) AS first9_darts,
       CAST(NULL AS DOUBLE) AS one_eighties, s.points, s.darts,
       CAST(NULL AS DOUBLE) AS checkouts_hit, CAST(NULL AS DOUBLE) AS checkout_attempts,
       'wikipedia' AS source, true AS stats_estimated
FROM ({wk_side('a', 'b')} UNION ALL {wk_side('b', 'a')}) s
-- a match an older source already has (same day, same two players) comes from there
LEFT ANTI JOIN (SELECT match_date, player_key, opponent_key FROM o_player_matches
                UNION ALL SELECT match_date, player_key, opponent_key FROM mc_player_matches) o
  ON o.match_date = s.match_date AND o.player_key = s.player_key AND o.opponent_key = s.opponent_key
""")
spark.sql("""
CREATE OR REPLACE TEMP VIEW wk_matches AS
SELECT match_key, match_date, event_key, tournament_key, tournament_name, round, 'MJ' AS category, true AS is_major,
       IF(score_a > score_b, key_a, key_b) AS winner_key, IF(score_a > score_b, player_a, player_b) AS winner_name,
       IF(score_a > score_b, key_b, key_a) AS loser_key, IF(score_a > score_b, player_b, player_a) AS loser_name,
       greatest(score_a, score_b) AS winner_score, least(score_a, score_b) AS loser_score, 'wikipedia' AS source
FROM wk
WHERE played AND match_key IN (SELECT match_key FROM wk_player_matches)
""")

# COMMAND ----------

# MAGIC %md ## Unified matches, player_matches, events

# COMMAND ----------

spark.sql("""CREATE OR REPLACE TABLE darts_silver.matches AS
             SELECT * FROM o_matches UNION ALL SELECT * FROM mc_matches UNION ALL SELECT * FROM wk_matches""")

mc_events = f"""
  UNION ALL
  SELECT event_key, tournament_key, any_value(tournament) AS tournament_name, max(m_date) AS event_date,
         min(m_date) AS start_date, max(m_date) AS end_date, any_value(category) AS category,
         CAST(NULL AS STRING) AS currency_code, CAST(NULL AS BIGINT) AS prize_fund, CAST(NULL AS DOUBLE) AS event_avg,
         max_by(IF(score_a > score_b, avg_a, avg_b), round = 'Final') AS winner_avg,
         max_by(IF(score_a > score_b, key_a, key_b), round = 'Final') AS winner_key,
         max_by(IF(score_a > score_b, player_a_name, player_b_name), round = 'Final') AS winner_name,
         tournament_key IS NOT NULL AS is_major, 'mastercaller' AS source
  FROM mc GROUP BY event_key, tournament_key
  HAVING max(m_date) > DATE'{ORAKEL_LAST_DATE}'""" if has("mastercaller_results") else ""
wk_events = f"""
  UNION ALL
  SELECT event_key, tournament_key, any_value(tournament_name), max(match_date), min(event_start), max(event_end), 'MJ',
         CAST(NULL AS STRING), CAST(NULL AS BIGINT), CAST(NULL AS DOUBLE),
         max_by(IF(score_a > score_b, avg_a, avg_b), is_final), max_by(IF(score_a > score_b, key_a, key_b), is_final),
         max_by(IF(score_a > score_b, player_a, player_b), is_final), true, 'wikipedia'
  FROM wk WHERE played GROUP BY event_key, tournament_key
  HAVING max(CAST(is_final AS INT)) = 1"""
spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.events AS
SELECT DISTINCT
  event_key, tournament_key, {unescape('tournament_name')} AS tournament_name,
  to_date(event_date) AS event_date, to_date(start_date) AS start_date, to_date(end_date) AS end_date,
  category, currency_code, try_cast(regexp_replace(prize_fund, ',', '') AS BIGINT) AS prize_fund,
  event_avg, winner_avg, player_key AS winner_key, {unescape('winner_name')} AS winner_name,
  tournament_key IN {MAJOR_KEYS} AS is_major, 'orakel' AS source
FROM {dedup("orakel_events", "event_key")}
{mc_events}
{wk_events}
""")

# COMMAND ----------

# MAGIC %md ## Rankings (official PDC Order of Merit) and players

# COMMAND ----------

# Rows from parser 1 also contain the module's previous table, often with other spellings ("De Zwaan", "O’Connor"),
# so they are dropped as soon as parser-2 rows exist; one row per player and snapshot (not per spelling).
ranking_sources = [f"SELECT to_date(as_of) AS snapshot_date, rank, player_name, prize_money, _run_date, "
                   f"{'coalesce(parser, 1)' if 'parser' in spark.table(f'darts_bronze.{t}').columns else '1'} AS parser "
                   f"FROM darts_bronze.{t}"
                   for t in ("wiki_rankings_history", "wiki_rankings") if has(t)]
if ranking_sources:
    spark.sql(f"""
    CREATE OR REPLACE TABLE darts_silver.rankings AS
    SELECT r.snapshot_date, r.rank, x.player_key, r.player_name, r.prize_money AS prize_money_2y
    FROM ({' UNION ALL '.join(ranking_sources)}) r
    JOIN xw x ON x.source = 'wikipedia' AND x.source_id = r.player_name
    WHERE r.parser = (SELECT max(parser) FROM ({' UNION ALL '.join(ranking_sources)}))
    QUALIFY row_number() OVER (PARTITION BY r.snapshot_date, x.player_key ORDER BY r._run_date DESC, r.rank) = 1
    """)

orakel_profile = f"""
  SELECT player_key, country, to_date(dob) AS date_of_birth
  FROM {dedup("orakel_rankings", "player_key")}"""
spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.players AS
WITH current_rank AS (
  SELECT * FROM darts_silver.rankings WHERE snapshot_date = (SELECT max(snapshot_date) FROM darts_silver.rankings)
),
seen AS (
  SELECT winner_key AS player_key, winner_name AS player_name, match_date FROM darts_silver.matches
  UNION ALL SELECT loser_key, loser_name, match_date FROM darts_silver.matches
),
names AS (SELECT player_key, max_by(player_name, match_date) AS player_name FROM seen GROUP BY player_key),
wiki AS (
  SELECT coalesce(b.player_key, x.player_key) AS player_key, b.wikidata_id, b.enwiki_title, b.description, b.intro,
         get(b.nickname, 0) AS nickname, get(b.image, 0) AS image_file, get(b.citizenship, 0) AS citizenship_qid
  FROM darts_bronze.wiki_player_background b
  LEFT JOIN xw x ON x.source = 'wikipedia' AND x.source_id = b.name
  QUALIFY row_number() OVER (PARTITION BY coalesce(b.player_key, x.player_key) ORDER BY b._run_date DESC) = 1
)
SELECT
  coalesce(n.player_key, c.player_key) AS player_key,
  coalesce(c.player_name, n.player_name) AS player_name,
  o.country, o.date_of_birth,
  c.prize_money_2y, c.rank AS prize_money_rank,
  coalesce(c.rank <= {TRACKED_PLAYERS}, false) AS is_tracked,
  w.nickname, w.wikidata_id, w.enwiki_title, w.description, w.intro, w.image_file, w.citizenship_qid
FROM names n
FULL OUTER JOIN current_rank c ON c.player_key = n.player_key
LEFT JOIN ({orakel_profile}) o ON o.player_key = coalesce(n.player_key, c.player_key)
LEFT JOIN wiki w ON w.player_key = coalesce(n.player_key, c.player_key)
""")

# COMMAND ----------

# Player matches of all sources, with both names as in darts_silver.players (one spelling per player, whatever the
# source wrote). Built after players, which takes its names from the matches.
spark.sql("""
CREATE OR REPLACE TABLE darts_silver.player_matches AS
WITH pm AS (SELECT * FROM o_player_matches UNION ALL SELECT * FROM mc_player_matches UNION ALL SELECT * FROM wk_player_matches)
SELECT pm.match_key, pm.player_key, p.player_name, pm.opponent_key, coalesce(o.player_name, pm.opponent_name) AS opponent_name,
       pm.* EXCEPT (match_key, player_key, opponent_key, opponent_name)
FROM pm
LEFT JOIN darts_silver.players p ON p.player_key = pm.player_key
LEFT JOIN darts_silver.players o ON o.player_key = pm.opponent_key
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

# MAGIC %md ## Majors, upcoming matches, tournament pages

# COMMAND ----------

spark.createDataFrame(
    [(int(k), m["name"], m["wiki"], m.get("mastercaller")) for k, m in MAJORS.items()],
    "tournament_key BIGINT, tournament_name STRING, wiki_title_pattern STRING, mastercaller_series STRING",
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("darts_silver.majors")

# Upcoming matches: the open matches of the Wikipedia draws (both players known, no result yet) in events that are
# not over. Rebuilt every run, so a match disappears as soon as its result is in. Only matches with a tracked player.
spark.sql("""
CREATE OR REPLACE TABLE darts_silver.upcoming_matches AS
SELECT DISTINCT
  concat(edition, ' ', tournament_name) AS event_title, true AS is_major, round AS round_name,
  CAST(match_date AS TIMESTAMP) AS start_time,
  key_a AS player_a_key, player_a AS player_a_name, key_b AS player_b_key, player_b AS player_b_name,
  current_timestamp() AS fetched_on
FROM wk
WHERE NOT played AND event_end >= current_date()
  AND (key_a IN (SELECT player_key FROM darts_silver.players WHERE is_tracked)
       OR key_b IN (SELECT player_key FROM darts_silver.players WHERE is_tracked))
""")

spark.sql(f"""
CREATE OR REPLACE TABLE darts_silver.tournament_pages AS
SELECT title, revid, wikitext, error, to_date(left(_run_date, 10)) AS fetched_on
FROM {dedup("wiki_tournament_pages", "title")}
""")

for t in ["events", "player_matches", "matches", "players", "player_crosswalk", "majors", "rankings", "tournament_pages",
          "upcoming_matches"]:
    if spark.catalog.tableExists(f"darts_silver.{t}"):
        print(t, spark.table(f"darts_silver.{t}").count())
display(spark.sql("SELECT source, count(*) n, min(match_date), max(match_date) FROM darts_silver.matches GROUP BY source"))
