# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze: load raw files from the Volume
# MAGIC Every `raw/<source>/<run_date>/<dataset>.jsonl` file is loaded 1:1, plus lineage columns.
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
    "wiki_tournament_pages": ("wikipedia/*/tournament_pages.jsonl", "revid BIGINT, error STRING"),
    "wiki_player_background": ("wikipedia/*/player_background.jsonl", "player_key BIGINT"),
}

# COMMAND ----------

for table, (pattern, hints) in TABLES.items():
    try:
        spark.read.format("json").load(f"{raw}/{pattern}").limit(1).count()
    except Exception:  # no file for this dataset yet (e.g. a dataset added after earlier runs)
        print(f"{table}: no files yet, skipped")
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
