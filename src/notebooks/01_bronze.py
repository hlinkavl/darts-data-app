# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze: load raw files from the Volume
# MAGIC Every `raw/<source>/<run_date>/<dataset>.jsonl` file is loaded 1:1, plus lineage columns.
# MAGIC Sources: `orakel` (until 28 Oct 2026, blocked since), `mastercaller` (results since Oct 2026), `wikipedia`.
# MAGIC Tables are rebuilt from all files, so every historical run stays queryable via `_run_date`
# MAGIC (folder name: YYYY-MM-DD or YYYY-MM-DDTHHMMSS, both sort chronologically as strings).

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
raw = f"/Volumes/{catalog}/darts_bronze/raw"

# Schema hints keep columns stable across datasets (e.g. "stat" is a number for 180s, a string elsewhere).
TABLES = {
    "orakel_rankings": ("orakel/*/rankings.jsonl", "sum_prize_money STRING, dob STRING"),
    "orakel_events": ("orakel/*/events.jsonl", "prize_fund STRING, organisation STRING, category STRING"),
    "orakel_matches": ("orakel/*/matches_*.jsonl", "stat STRING, stat1 DOUBLE, stat2 DOUBLE, organisation STRING"),
    "orakel_upcoming": ("orakel/*/upcoming_matches.jsonl", "venue STRING, legs_format STRING, match_date STRING"),
    "mastercaller_results": ("mastercaller/*/results.jsonl",
                             "avg_a DOUBLE, avg_b DOUBLE, score_a INT, score_b INT, start_time STRING, round STRING"),
    "mastercaller_upcoming": ("mastercaller/*/upcoming_matches.jsonl", "start_time STRING, round STRING, tournament STRING"),
    "wiki_rankings": ("wikipedia/*/rankings.jsonl", "prize_money BIGINT, revision_id BIGINT"),
    "wiki_rankings_history": ("wikipedia/*/rankings_history.jsonl", "prize_money BIGINT, revision_id BIGINT"),
    "ingestion_manifest": ("ingestion/*/manifest.jsonl", "rows BIGINT, error STRING, dataset STRING"),
    "wiki_tournament_pages": ("wikipedia/*/tournament_pages.jsonl", "revid BIGINT, error STRING"),
    "wiki_player_background": ("wikipedia/*/player_background.jsonl", "player_key BIGINT"),
}

# COMMAND ----------

for table, (pattern, hints) in TABLES.items():
    try:
        has_rows = bool(spark.read.format("json").load(f"{raw}/{pattern}").columns)
    except Exception:  # no file for this dataset yet (e.g. a dataset added after earlier runs)
        has_rows = False
    if not has_rows:  # missing or only empty files (e.g. no upcoming matches scheduled)
        print(f"{table}: no data yet, skipped")
        continue
    spark.sql(f"""
        CREATE OR REPLACE TABLE {catalog}.darts_bronze.{table} AS
        SELECT
          * EXCEPT (_rescued_data),
          regexp_extract(_metadata.file_path, '/raw/[^/]+/([^/]+)/', 1) AS _run_date,
          _metadata.file_path AS _source_file,
          current_timestamp() AS _ingested_at
        FROM read_files('{raw}/{pattern}', format => 'json', schemaHints => '{hints}')
    """)
    count = spark.table(f"{catalog}.darts_bronze.{table}").count()
    print(f"{table}: {count} rows")
