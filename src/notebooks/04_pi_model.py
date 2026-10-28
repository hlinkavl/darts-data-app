# Databricks notebook source
# MAGIC %md
# MAGIC # Gold: Performance Index model (steps 1 and 2)
# MAGIC Tunes the Opponent-Weighted Elo, selects predictors (correlation filter, significance + out-of-sample check,
# MAGIC bootstrap stability) and fits the weights. Every decision is written to gold tables under a model version,
# MAGIC so the app's Methodology page always shows the current model. Methodology: docs/PERFORMANCE_INDEX.md.

# COMMAND ----------

# MAGIC %pip install -q statsmodels==0.15.0 scikit-learn

# COMMAND ----------

import os
import sys
from datetime import date

import pandas as pd

sys.path.append(os.path.abspath(".."))  # src/, for the shared analytics package
from analytics import pipeline

dbutils.widgets.text("catalog", "workspace")
catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")
version = f"v{date.today().isoformat()}"

# COMMAND ----------

player_matches = spark.sql("""
    SELECT match_key, player_key, opponent_key, match_date, tournament_key, is_major, won, category, tournament_name,
           points, darts, first9_points, first9_darts, checkouts_hit, checkout_attempts, one_eighties
    FROM darts_silver.player_matches
""").toPandas()
matches = spark.sql("SELECT match_key, match_date, winner_key, loser_key, is_major FROM darts_silver.matches").toPandas()

run = pipeline.fit(player_matches, matches, version)
print(f"model {version}: {run.n_pairs} matches between tracked players, Elo {run.elo_params}")
display(run.selection_log)
display(run.coefficients)
display(run.data_summary)
display(run.metrics)

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

history = run.elo_history.assign(match_date=pd.to_datetime(run.elo_history["match_date"]).dt.date, version=version)
spark.createDataFrame(history).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("darts_gold.elo_history")
print("saved model", version)
