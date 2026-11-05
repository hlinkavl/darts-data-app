# Databricks notebook source
# MAGIC %md
# MAGIC # AI form summaries
# MAGIC 1. **News per player**: PDC news articles matched to tracked players → `darts_gold.player_news`.
# MAGIC 2. **Summaries**: a short form summary per player with `ai_query`, written only from the player's numbers,
# MAGIC    last matches and news (`analytics/narratives.py`) → `darts_gold.player_narratives`. A summary is generated
# MAGIC    again only when its inputs change (cost). The model is set in `config/ai.yml`.
# MAGIC
# MAGIC Model comparison: run with `compare_models=<m1>,<m2>` to write summaries of 20 players from each model to
# MAGIC `darts_gold.player_narrative_trials` (nothing else changes).

# COMMAND ----------

import os
import sys

import pandas as pd
import yaml

sys.path.append(os.path.abspath(".."))
from analytics import narratives, news

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("compare_models", "")
catalog = dbutils.widgets.get("catalog")
compare_models = [m.strip() for m in dbutils.widgets.get("compare_models").split(",") if m.strip()]
spark.sql(f"USE CATALOG {catalog}")
with open("../../config/ai.yml") as f:
    MODEL = (yaml.safe_load(f) or {}).get("model") or ""
today = pd.Timestamp.now().normalize()

# COMMAND ----------

# MAGIC %md ## News per player

# COMMAND ----------

articles = (spark.sql("SELECT link, title, published, text FROM darts_bronze.pdc_news").toPandas()
            if spark.catalog.tableExists("darts_bronze.pdc_news") else pd.DataFrame(columns=["link", "title", "published", "text"]))
tracked = spark.sql("SELECT player_key, player_name, prize_money_rank AS oom FROM darts_silver.players WHERE is_tracked").toPandas()
mentions = news.player_mentions(articles, tracked)
out = mentions.assign(published=mentions["published"].dt.tz_localize(None))
spark.createDataFrame(out if len(out) else out.astype("string")).write.mode("overwrite").option("overwriteSchema", "true") \
    .saveAsTable("darts_gold.player_news")
print(f"{len(articles.drop_duplicates('link'))} articles, {len(mentions)} mentions, {int(mentions['relevant'].sum())} relevant")

# COMMAND ----------

# MAGIC %md ## Summaries

# COMMAND ----------

current = spark.sql("""
    SELECT player_key, player_name, rank, pi, avg_l30, form, effective_average
    FROM darts_gold.performance_index WHERE is_current
""").toPandas().merge(tracked[["player_key", "oom"]], on="player_key", how="left")
recent = spark.sql("SELECT * FROM darts_gold.player_recent_matches WHERE recency <= 5").toPandas()
prompts = narratives.build_prompts(current, recent, mentions, today)


def generate(todo: pd.DataFrame, model: str) -> pd.DataFrame:
    """ai_query for every prompt; errors are kept per row instead of failing the job."""
    spark.createDataFrame(todo[["player_key", "prompt"]]).createOrReplaceTempView("narrative_todo")
    res = spark.sql(f"""
        SELECT player_key,
               ai_query('{model}', prompt, failOnError => false,
                        modelParameters => named_struct('max_tokens', 220, 'temperature', 0.2)) AS r
        FROM narrative_todo
    """).selectExpr("player_key", "r.response AS narrative", "r.errorMessage AS error").toPandas()
    return todo.merge(res, on="player_key").assign(model=model, generated_at=pd.Timestamp.now(tz="UTC"))


if compare_models:
    trials = pd.concat([generate(prompts.head(20), m) for m in compare_models], ignore_index=True)
    spark.createDataFrame(trials.drop(columns=["news_links"])).write.mode("overwrite").option("overwriteSchema", "true") \
        .saveAsTable("darts_gold.player_narrative_trials")
    display(trials.pivot(index="player_name", columns="model", values="narrative"))
    dbutils.notebook.exit(f"compared {len(compare_models)} models on {min(20, len(prompts))} players")

TABLE = "darts_gold.player_narratives"
if not MODEL:
    if not spark.catalog.tableExists(TABLE):  # the app reads it; an empty table means "no summaries yet"
        spark.sql(f"""CREATE TABLE {TABLE} (player_key BIGINT, player_name STRING, prompt STRING, input_hash STRING,
                      news_links ARRAY<STRING>, narrative STRING, error STRING, model STRING, generated_at TIMESTAMP)""")
    dbutils.notebook.exit("no AI model set in config/ai.yml: summaries skipped")

existing = spark.table(TABLE).toPandas() if spark.catalog.tableExists(TABLE) else None
todo = narratives.to_generate(prompts, existing, MODEL)
print(f"{len(prompts)} candidates, {len(todo)} to generate with {MODEL}")
if len(todo):
    fresh = generate(todo, MODEL)
    keep = existing[~existing["player_key"].isin(fresh["player_key"])] if existing is not None else None
    result = pd.concat([keep, fresh[keep.columns if keep is not None else fresh.columns]], ignore_index=True) \
        if keep is not None else fresh
    spark.createDataFrame(result).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE)
    failed = fresh[fresh["narrative"].isna()]
    print(f"generated {len(fresh) - len(failed)}, failed {len(failed)}")
    if len(failed):
        display(failed[["player_name", "error"]])
display(spark.table(TABLE).orderBy("player_name")) if spark.catalog.tableExists(TABLE) else None
