# Darts Performance Analyzer

- Everything in the repo (code, comments, docs, commit messages, UI text) is in **English**. The user chats in Czech; reply in Czech.
- Plan: `docs/PLAN.md` (keep checkboxes up to date). Design, data model, PI methodology: `docs/DESIGN.md`.
- Backend: Databricks Free Edition, CLI profile `darts`. Catalog `workspace`, schemas `darts_bronze` / `darts_silver` / `darts_gold`, Volume `/Volumes/workspace/darts_bronze/raw`.
- Free Edition: serverless only, one 2X-Small SQL warehouse, max 3 apps (auto-stop after 24 h), max 5 concurrent job tasks, restricted outbound internet.
- Deploy via the Asset Bundle: `databricks bundle validate|deploy|run -t dev`.
- Never commit secrets or `data/` contents. Auth is OAuth via `~/.databrickscfg`.
