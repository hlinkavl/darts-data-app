# Common tasks. Profile and catalog can be overridden: make refresh PROFILE=darts CATALOG=workspace
PROFILE ?= darts
CATALOG ?= workspace
PY := .venv/bin/python

.PHONY: setup ingest pipeline refresh deploy

setup:  ## create the local venv
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

ingest:  ## incremental: new results (Mastercaller) + rankings and pages (Wikipedia) + upload to the Volume
	$(PY) -m ingestion.run --upload --profile $(PROFILE) --catalog $(CATALOG)

pipeline:  ## run bronze -> silver -> quality in Databricks
	databricks bundle run darts_refresh -t dev -p $(PROFILE)

refresh: ingest pipeline  ## full on-demand refresh

deploy:  ## validate and deploy the bundle (job + app)
	databricks bundle validate -t dev -p $(PROFILE) && databricks bundle deploy -t dev -p $(PROFILE)
