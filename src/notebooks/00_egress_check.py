# Databricks notebook source
# MAGIC %md
# MAGIC # Egress check
# MAGIC Free Edition serverless compute can only reach a whitelist of domains.
# MAGIC This notebook tests every candidate data source and decides whether scraping
# MAGIC can run inside Databricks or has to move to GitHub Actions (see docs/PLAN.md, step 1.3).

# COMMAND ----------

import requests

SOURCES = {
    "pdc": "https://www.pdc.tv/order-merit/pdc-order-merit",
    "darts_orakel": "https://dartsorakel.com/",
    "dartsdatabase": "https://www.dartsdatabase.co.uk/",
    "wikipedia": "https://en.wikipedia.org/wiki/2027_PDC_World_Darts_Championship",
    "mastercaller": "https://mastercaller.com/",
    "pypi": "https://pypi.org/simple/requests/",
}

HEADERS = {"User-Agent": "darts-data-app egress check"}

results = []
for name, url in SOURCES.items():
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        results.append((name, url, r.status_code, None))
    except Exception as e:  # DNS / proxy blocks surface as connection errors
        results.append((name, url, None, f"{type(e).__name__}: {e}"[:300]))

df = spark.createDataFrame(results, "source string, url string, status int, error string")
display(df)
