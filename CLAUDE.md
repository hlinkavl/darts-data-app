# Darts Performance Analyzer

- Everything in the repo (code, comments, docs, commit messages, UI text) is in **English**. The user chats in Czech; reply in Czech.
- Docs: `README.md` (short, for visitors: app link, what it answers, diagram `docs/architecture.svg`), `docs/MAINTENANCE.md` (for the owner: links, where things are in Databricks, runbook, tokens, data model, decisions: keep it current), `docs/METHODOLOGY.md` (PI and tournament predictions). No other docs files. Docs are for reading: short, plain language, no terminal commands (technical notes belong here in CLAUDE.md).
- Backend: Databricks Free Edition, CLI profile `darts`. Catalog `workspace`, schemas `darts_bronze` / `darts_silver` / `darts_gold`, Volume `/Volumes/workspace/darts_bronze/raw`.
- Free Edition: serverless only, one 2X-Small SQL warehouse, max 3 apps (auto-stop after 24 h), max 5 concurrent job tasks, restricted outbound internet.
- Deploy via the Asset Bundle: `databricks bundle validate|deploy|run -t dev`.
- Never commit secrets or `data/` contents. Auth is OAuth via `~/.databrickscfg`.

## Developer notes

- Tests: `.venv/bin/python -m pytest -q`. App locally: `cd app && streamlit run app.py` (public mode when `app/snapshot/` exists; fetch it with `DATABRICKS_CONFIG_PROFILE=darts python scripts/download_snapshot.py app/snapshot`; `DARTS_DATA=local` + `scripts/build_local_snapshot.py` for the old local snapshot).
- Save quota: run single job tasks (`databricks bundle run darts_refresh -t dev --profile darts --only <task>` or SDK `run_now(only=[...])`), avoid repeated full runs; refit with `--params refit=force` (`refit=approve` also activates changed predictors).
- The app has three modes (`app/data.py`): `databricks` (Databricks App, SQL warehouse), `public` (Streamlit Community Cloud, snapshot, no Genie, no refresh button), `local`. Every UI change must work in public mode and at phone width (~390 px; phone-only CSS in `ui.CSS`).
- Public app: a push to main touching `app/` runs `publish-app`, which force-pushes app + snapshot to branch `public-app`; no separate deploy. The snapshot is exported by the health task (`src/analytics/snapshot.py`).
- Databricks App deploy: smoke-test first (`DATABRICKS_CONFIG_PROFILE=darts DATABRICKS_WAREHOUSE_ID=c7c519d783971c09 python scripts/smoke_app.py databricks`), then `databricks bundle run darts_app -t dev --profile darts` (this starts the app: costs quota, stop it afterwards). Apps run Python 3.11 (no backslashes or quotes inside f-string expressions); `app/requirements.txt` pins `databricks-sdk` (the runtime ships an old one).
- GitHub token renewal: `databricks secrets put-secret darts github_token --profile darts`, then restart the app.
- Genie space: edit `config/genie/space.yml`, then `DATABRICKS_CONFIG_PROFILE=darts python scripts/genie_space.py`.
