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

## 7. Tokens and their renewal

Two tokens keep the app running without a Mac. Neither is ever stored in the repo.

| Token | Used by | Stored in | Expires |
|---|---|---|---|
| Databricks access token "github-actions" | GitHub Actions (`refresh`, `start-app`): upload data, run the job, start the app | GitHub secret `DATABRICKS_TOKEN` (with `DATABRICKS_HOST`) | **9 Nov 2027** |
| GitHub fine-grained token `darts-app-refresh` (repo `darts-data-app`, Actions: read and write) | The app's **Refresh data now** button | Databricks secret scope `darts`, key `github_token` | about one year from 9 Nov 2026; exact date at github.com/settings/personal-access-tokens |

A token that has expired shows up as a failed `refresh` run (failure e-mail from GitHub) or as an error after
pressing the Refresh button. Renew a week ahead.

**Databricks token**
1. Databricks → Settings → Developer → Access tokens → **Generate new token**: comment `github-actions`,
   lifetime 365 days.
2. GitHub → repo → Settings → Secrets and variables → Actions → `DATABRICKS_TOKEN` → **Update**, paste the token.
3. Revoke the old token in the Databricks list.
4. Check: Actions → **start-app** → Run workflow. It must log in and start the app or report "already running".

**GitHub token**
1. github.com/settings/personal-access-tokens → `darts-app-refresh` → **Regenerate token** (one year).
2. `databricks secrets put-secret darts github_token --profile darts`, paste the token.
3. Restart the app, it reads secrets at start: `databricks apps stop darts-performance-analyzer --profile darts`,
   then `databricks apps start darts-performance-analyzer --profile darts`.

**CLI login** (your Mac, profile `darts`) is OAuth and expires after some idle time: `databricks auth login --profile darts`.
