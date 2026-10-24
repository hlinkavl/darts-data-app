# Setup

## 1. Tools (macOS)

```bash
brew tap databricks/tap && brew trust databricks/tap && brew install databricks
databricks --version          # verified: v1.22.1
python3 --version             # 3.11+ (3.13 locally)
```

Project Python environment:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
```

## 2. Databricks Free Edition

1. Sign up at https://www.databricks.com/learn/free-edition, then click **Get Free Edition** (no credit card).
2. In the workspace, click **Home** and copy the URL from the address bar **before** `/browse…`, e.g. `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`. The workspace ID is the `?o=…` number in the URL. The CLI doesn't need it, only the host.
3. (recommended) Click **Verify identity** in the top bar and verify via LinkedIn to raise some limits.

## 3. Connect the CLI (OAuth, no token in the repo)

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile darts
databricks current-user me -p darts      # verify
export DATABRICKS_CONFIG_PROFILE=darts  # optional, add to ~/.zshrc
```

## 4. Databricks skills for Claude Code (as in the video)

```bash
databricks aitools install --agents claude-code --scope global
```

Then restart Claude Code so it picks up the new plugin.

## 5. Bootstrap the workspace

```bash
./scripts/bootstrap_databricks.sh        # creates the darts_bronze/silver/gold schemas + the raw Volume
databricks bundle validate -t dev        # validates databricks.yml
```

## 6. Run a refresh on demand

```bash
databricks bundle deploy -t dev
databricks bundle run darts_refresh -t dev
```
