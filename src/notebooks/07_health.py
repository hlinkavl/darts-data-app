# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Health report
# MAGIC Is the data fresh and complete, did every source work, is the model trustworthy? One row per check with
# MAGIC status (green / yellow / red), what was measured, a message and the recommended action
# MAGIC (`darts_gold.health_report`, history in `darts_gold.health_history`). A red check fails this task, so the
# MAGIC job fails and the failure e-mail goes out. Checks: src/analytics/health.py.

# COMMAND ----------

import os
import sys
from datetime import date

import pandas as pd
import yaml

sys.path.append(os.path.abspath(".."))
from analytics import health

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")
today = date.today()

def table(name: str) -> pd.DataFrame | None:
    return spark.table(name).toPandas() if spark.catalog.tableExists(name) else None

# COMMAND ----------

calendar = table("darts_gold.majors_calendar")
major_running = bool(calendar is not None and (calendar["status"] == "in progress").any())

manifest_all = table("darts_bronze.ingestion_manifest")
if manifest_all is not None and len(manifest_all):
    last = manifest_all["run_id"].max()
    manifest = manifest_all[manifest_all["run_id"] == last]
    last_run = pd.to_datetime(last[:10])
else:
    manifest, last_run = pd.DataFrame(columns=["source", "dataset", "rows", "status", "error"]), None

last_match = spark.sql("SELECT max(match_date) FROM darts_silver.matches").first()[0]

tracked_without_history = spark.sql("""
    SELECT p.player_name FROM darts_silver.players p
    WHERE p.is_tracked AND NOT EXISTS (SELECT 1 FROM darts_silver.player_matches m WHERE m.player_key = p.player_key)
""").toPandas()["player_name"].tolist()

with open("../../config/majors.yml") as f:
    majors = yaml.safe_load(f)["majors"]
with open("../../config/mastercaller_series.yml") as f:
    groups = yaml.safe_load(f)
known = {m["mastercaller"] for m in majors.values() if m.get("mastercaller")} | {s for g in groups.values() for s in g}
recent_series = set()
if spark.catalog.tableExists("darts_bronze.mastercaller_results"):
    recent_series = set(spark.sql("""
        SELECT DISTINCT series FROM darts_bronze.mastercaller_results
        WHERE to_date(match_date) >= date_sub(current_date(), 30) AND series NOT LIKE 'pdc-%'
    """).toPandas()["series"])

registry_latest = None
if spark.catalog.tableExists("darts_gold.pi_model_registry"):
    rows = spark.sql("SELECT * FROM darts_gold.pi_model_registry ORDER BY decided_at DESC LIMIT 1").collect()
    registry_latest = rows[0].asDict() if rows else None

bench = None
if registry_latest and spark.catalog.tableExists("darts_gold.pi_benchmark"):
    active = spark.sql("SELECT version FROM darts_gold.pi_model_registry WHERE status = 'active' "
                       "ORDER BY decided_at DESC LIMIT 1").collect()
    if active:
        bench = spark.sql(f"SELECT * FROM darts_gold.pi_benchmark WHERE version = '{active[0][0]}'").toPandas()

n_upcoming = spark.table("darts_gold.upcoming_matches").count() if spark.catalog.tableExists("darts_gold.upcoming_matches") else 0

# COMMAND ----------

checks = (
    health.ingestion(manifest, last_run, today, major_running)
    + [health.freshness(last_match, today, major_running)]
    + (health.draws(calendar, today) if calendar is not None else [])
    + [health.player_matching(tracked_without_history)]
    + health.new_series(recent_series, known)
    + [health.model(registry_latest), health.benchmark(bench), health.upcoming(major_running, n_upcoming)]
)
report = health.report(checks).assign(checked_at=pd.Timestamp.now(tz="UTC"))
overall = health.overall(report)

spark.createDataFrame(report).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("darts_gold.health_report")
spark.createDataFrame(report.assign(overall=overall)).write.mode("append").option("mergeSchema", "true") \
    .saveAsTable("darts_gold.health_history")
display(report)

if overall == health.RED:
    reds = report[report["status"] == health.RED]
    raise RuntimeError("Health report is RED: " + " | ".join(f"{r.check}: {r.message}" for r in reds.itertuples()))
print("overall:", overall)
