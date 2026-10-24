#!/usr/bin/env bash
# Creates the Unity Catalog schemas and the raw Volume. Safe to re-run.
set -euo pipefail

PROFILE="${DATABRICKS_CONFIG_PROFILE:-darts}"
CATALOG="${DARTS_CATALOG:-workspace}"

databricks current-user me -p "$PROFILE" >/dev/null

for layer in bronze silver gold; do
  schema="darts_${layer}"
  if databricks schemas get "${CATALOG}.${schema}" -p "$PROFILE" >/dev/null 2>&1; then
    echo "schema ${CATALOG}.${schema} exists"
  else
    databricks schemas create "$schema" "$CATALOG" -p "$PROFILE" --comment "Darts ${layer} layer" >/dev/null
    echo "created schema ${CATALOG}.${schema}"
  fi
done

if databricks volumes read "${CATALOG}.darts_bronze.raw" -p "$PROFILE" >/dev/null 2>&1; then
  echo "volume ${CATALOG}.darts_bronze.raw exists"
else
  databricks volumes create "$CATALOG" darts_bronze raw MANAGED -p "$PROFILE" >/dev/null
  echo "created volume ${CATALOG}.darts_bronze.raw"
fi
