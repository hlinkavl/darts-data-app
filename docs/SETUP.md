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

## 8. When something breaks

The refresh is built to fail loudly and never to show wrong numbers:

- **Each source on its own.** Mastercaller, Wikipedia and PDC news are fetched separately; one failing does not stop
  the others. The run's manifest records rows and errors per source.
- **Quality gate before the gold tables.** Hard checks (duplicates, impossible averages, empty tables) stop the job
  before any model or prediction is computed, so the app keeps the last good data.
- **Model promotion gate.** A refit only becomes active if it passes the test; otherwise the previous model stays.
- **Health report** (app → Data & Health): every problem with a "What to do". **Red fails the job**, which sends two
  e-mails (Databricks job + GitHub workflow). Red means: a source failed or blocks us, the Order of Merit came back
  empty, no model, or **no new result for more than 4 days while a major is running** (a source answers "ok" but
  delivers nothing new, typically after a page change).
- **Yellow** shows only in the app: e.g. a draw format we don't parse (the 2026 Grand Slam groups), a new series to
  add to the config, a refit that was not activated.
- During a major the app is started even when the job failed, so it shows the last good data.

What to do when the e-mail arrives:

1. Open the failed run (link in the e-mail) and Data & Health in the app: the red check says what broke.
2. A one-off error (timeout, Databricks quota): press Refresh in the app or "Run workflow" on GitHub.
3. A source changed its page, or a new tournament format: open Claude Code in the repo, paste the error and the health
   message, fix, run the tests, `databricks bundle deploy -t dev --profile darts`, then Refresh.
4. A source blocks us (HTTP 401/403): don't work around it; find a replacement source.
5. An expired token: section 7.

Expect a few such fixes a year, mostly when a season starts or a format changes.
