# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Performance Index model (steps 1 and 2)
# MAGIC Tunes the Opponent-Weighted Elo, selects predictors (correlation filter, significance + out-of-sample check,
# MAGIC bootstrap stability) and fits the weights. Every decision is written to gold tables under a model version,
# MAGIC so the app's Methodology page always shows the current model. Methodology: docs/PERFORMANCE_INDEX.md.
# MAGIC Also runs the key test against the PDC Order of Merit and applies the promotion policy: the new fit is a
# MAGIC candidate and only becomes the active model if analytics.registry allows it.

# COMMAND ----------

# MAGIC %pip install -q statsmodels==0.15.0 scikit-learn

# COMMAND ----------

import os
import sys
from datetime import date

import pandas as pd

sys.path.append(os.path.abspath(".."))  # src/, for the shared analytics package
from analytics import pipeline, registry

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")
version = f"v{date.today().isoformat()}"

# COMMAND ----------

player_matches = spark.sql("""
    SELECT match_key, player_key, opponent_key, match_date, round, tournament_key, is_major, won, category, tournament_name,
           points, darts, first9_points, first9_darts, checkouts_hit, checkout_attempts, one_eighties
    FROM darts_silver.player_matches
""").toPandas()
matches = spark.sql("SELECT match_key, match_date, round, winner_key, loser_key, is_major FROM darts_silver.matches").toPandas()
rankings = spark.sql("SELECT snapshot_date, player_key, rank FROM darts_silver.rankings").toPandas()

run = pipeline.fit(player_matches, matches, version, rankings=rankings)
print(f"model {version}: {run.n_pairs} matches between tracked players, Elo {run.elo_params}")
display(run.selection_log)
display(run.coefficients)
display(run.data_summary)
display(run.metrics)
display(run.benchmark)

# COMMAND ----------

def save_versioned(df: pd.DataFrame, table: str) -> None:
    """Append under the current version (replacing an earlier run of the same version)."""
    full = f"darts_gold.{table}"
    if spark.catalog.tableExists(full):
        spark.sql(f"DELETE FROM {full} WHERE version = '{version}'")
    out = df.assign(version=version, fitted_at=pd.Timestamp.now(tz="UTC"))
    spark.createDataFrame(out).write.mode("append").option("mergeSchema", "true").saveAsTable(full)

corr = (run.correlations.rename_axis("predictor_a").reset_index()
        .melt(id_vars="predictor_a", var_name="predictor_b", value_name="r"))

save_versioned(run.coefficients, "pi_coefficients")
save_versioned(run.selection_log.reset_index(names="step_order"), "pi_selection_log")
save_versioned(run.metrics, "pi_metrics")
save_versioned(run.calibration, "pi_calibration")
save_versioned(run.data_summary, "pi_training_data")
save_versioned(run.elo_tuning, "pi_elo_tuning")
save_versioned(corr, "pi_correlations")
if run.benchmark is not None:
    save_versioned(run.benchmark, "pi_benchmark")

# COMMAND ----------

# MAGIC %md ## Promotion: candidate -> active (analytics/registry.py)

# COMMAND ----------

REGISTRY = "darts_gold.pi_model_registry"
test_ll = float(run.metrics.query("model == 'selected' and dataset == 'test'")["log_loss"].iloc[0])
active = None
if spark.catalog.tableExists(REGISTRY):
    spark.sql(f"DELETE FROM {REGISTRY} WHERE version = '{version}'")
    rows = spark.sql(f"SELECT * FROM {REGISTRY} WHERE status = 'active' ORDER BY decided_at DESC LIMIT 1").collect()
    active = rows[0].asDict() if rows else None
active_coefs = (spark.sql(f"SELECT predictor, weight_pct FROM darts_gold.pi_coefficients WHERE version = '{active['version']}'").toPandas()
                if active else None)
decision = registry.decide(run.coefficients, test_ll, active_coefs, active["test_log_loss"] if active else None)
print("promote" if decision.promote else "keep active", "-", decision.reason)

if decision.promote and active:
    spark.sql(f"UPDATE {REGISTRY} SET status = 'retired' WHERE status = 'active'")
entry = pd.DataFrame([{
    "version": version, "status": "active" if decision.promote else "rejected", "reason": decision.reason,
    "predictors": ", ".join(run.coefficients["predictor"]), "test_log_loss": test_ll,
    "elo_k": run.elo_params.k, "elo_major_multiplier": run.elo_params.major_multiplier,
    "decided_at": pd.Timestamp.now(tz="UTC"),
}])
spark.createDataFrame(entry).write.mode("append").option("mergeSchema", "true").saveAsTable(REGISTRY)

# Elo history per version: keep the active model's and this candidate's.
history = run.elo_history.assign(match_date=pd.to_datetime(run.elo_history["match_date"]).dt.date, version=version)
keep = {version} | ({active["version"]} if active and not decision.promote else set())
if spark.catalog.tableExists("darts_gold.elo_history") and "version" in spark.table("darts_gold.elo_history").columns:
    spark.sql(f"DELETE FROM darts_gold.elo_history WHERE version NOT IN ({', '.join(repr(v) for v in keep)})")
    spark.createDataFrame(history).write.mode("append").saveAsTable("darts_gold.elo_history")
else:
    spark.createDataFrame(history).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("darts_gold.elo_history")
display(spark.table(REGISTRY).orderBy("decided_at"))
