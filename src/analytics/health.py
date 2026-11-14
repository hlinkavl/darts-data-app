"""Health report: is the data fresh and complete, did every source work, is the model trustworthy?

Every check returns a status (green / yellow / red), what it measured, a message and a recommended action.
Red means the refresh produced something that must not be trusted: the job fails and an e-mail goes out.
Yellow means the app works, but something needs attention. Thresholds are constants below.
"""

from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

GREEN, YELLOW, RED = "green", "yellow", "red"
ORDER = {GREEN: 0, YELLOW: 1, RED: 2}

STALE_INGESTION_DAYS = 14          # on-demand refresh outside majors
STALE_INGESTION_DAYS_MAJOR = 2     # daily refresh while a major is running
# A match of a running major's draw that is still open this many days after its round's date means the results
# stopped arriving (the Wikipedia page changed or the parser broke): red, so the job fails and an e-mail goes out.
OVERDUE_DAYS = 2
NEW_PLAYERS_LIMIT = 5              # tracked players without any match history (likely a name mismatch)
DRAW_LOOKAHEAD_DAYS = 7

FIX_CODE = "Fix in the repo with Claude Code and deploy with the bundle."


@dataclass
class Check:
    area: str
    check: str
    status: str
    value: str
    message: str
    action: str = ""


def ingestion(manifest: pd.DataFrame, last_run: pd.Timestamp | None, today: date, major_running: bool) -> list[Check]:
    """manifest: rows of the latest ingestion run (source, dataset, rows, status, error)."""
    out = []
    if last_run is None:
        return [Check("ingestion", "last run", RED, "never", "No ingestion run found.", "Run `make ingest` or the refresh workflow.")]
    age = (pd.Timestamp(today) - pd.Timestamp(last_run).normalize()).days
    limit = STALE_INGESTION_DAYS_MAJOR if major_running else STALE_INGESTION_DAYS
    out.append(Check("ingestion", "last run", GREEN if age <= limit else YELLOW, f"{age} days ago",
                     f"Last ingestion {age} days ago (limit {limit} days{' during a major' if major_running else ''}).",
                     "" if age <= limit else "Press Refresh in the app or run the refresh workflow."))
    for r in manifest[manifest["status"] == "error"].itertuples():
        blocked = any(code in str(r.error) for code in ("401", "403", "418"))  # 418: a common anti-bot answer
        out.append(Check("ingestion", f"source {r.source}", RED, "error", f"{r.source} failed: {r.error}",
                         ("The source blocks our client. Don't work around it: find a replacement source. " + FIX_CODE)
                         if blocked else "Retry the refresh; if it keeps failing, the source changed. " + FIX_CODE))
    ok = manifest[manifest["status"] == "ok"]
    for source in sorted(set(manifest["source"])):
        if source in set(manifest.loc[manifest["status"] == "error", "source"]):
            continue
        out.append(Check("ingestion", f"source {source}", GREEN, f"{int(ok.loc[ok.source == source, 'rows'].sum())} rows",
                         f"{source} returned {', '.join(f'{d}: {n}' for d, n in ok.loc[ok.source == source, ['dataset', 'rows']].itertuples(index=False))}."))
    rankings = ok[ok["dataset"] == "rankings"]
    if "wikipedia" in set(ok["source"]) and (rankings.empty or rankings["rows"].sum() < 100):
        out.append(Check("ingestion", "order of merit", RED, f"{int(rankings['rows'].sum()) if not rankings.empty else 0} players",
                         "The PDC Order of Merit came back (almost) empty: the Wikipedia data module may have changed.",
                         "Check Module:DartsRankings/data/PDC Rankings. " + FIX_CODE))
    return out


def freshness(last_match: date | None) -> Check:
    """The newest result. Since Nov 2026 only majors' knockout matches arrive, so weeks without a result are normal;
    stuck results during a major are caught by overdue_matches."""
    if last_match is None:
        return Check("data", "latest result", RED, "none", "No match results at all.", "Run the refresh.")
    return Check("data", "latest result", GREEN, str(last_match), f"Newest result: {last_match}.")


def overdue_matches(open_matches: pd.DataFrame, today: date) -> Check:
    """open_matches: silver.upcoming_matches (event_title, round_name, start_time = the round's date)."""
    if open_matches is None or open_matches.empty:
        return Check("data", "overdue results", GREEN, "0", "No open draw match is overdue.")
    due = open_matches[pd.to_datetime(open_matches["start_time"]) < pd.Timestamp(today) - pd.Timedelta(days=OVERDUE_DAYS)]
    if due.empty:
        return Check("data", "overdue results", GREEN, "0", "No open draw match is overdue.")
    first = due.sort_values("start_time").iloc[0]
    return Check("data", "overdue results", RED, f"{len(due)} matches",
                 f"{len(due)} matches of {first['event_title']} (from the {first['round_name']}) have no result more "
                 f"than {OVERDUE_DAYS} days after their round: the results stopped arriving.",
                 "Check the event's Wikipedia page: if the results are there, the draw format changed. " + FIX_CODE)


def draws(calendar: pd.DataFrame, today: date) -> list[Check]:
    """calendar: gold.majors_calendar (tournament_name, wiki_title, start_date, end_date, status, has_draw)."""
    out = []
    t = pd.Timestamp(today)
    soon = calendar[(calendar["status"] == "in progress")
                    | ((calendar["status"] == "upcoming") & (pd.to_datetime(calendar["start_date"]) <= t + pd.Timedelta(days=DRAW_LOOKAHEAD_DAYS)))]
    for r in soon.itertuples():
        if r.has_draw:
            out.append(Check("tournaments", f"draw {r.tournament_name}", GREEN, "parsed", f"Draw of {r.wiki_title} parsed."))
        else:
            out.append(Check("tournaments", f"draw {r.tournament_name}", YELLOW, "missing",
                             f"{r.tournament_name} starts {pd.Timestamp(r.start_date).date() if pd.notna(r.start_date) else '(date unknown)'}"
                             f" but no draw could be read from Wikipedia ({r.wiki_title}).",
                             "If the draw is already on the Wikipedia page, its format is not supported yet: " + FIX_CODE))
    return out


def player_matching(tracked_without_history: list[str], without_stats: list[str] | None = None) -> list[Check]:
    """Tracked players (Order of Merit top 150) the data cannot describe well.

    tracked_without_history: no result at all under their name, so probably another spelling in a source (fix:
    an alias). without_stats: results (hence Elo) but no 3-dart averages, a known gap: Darts Orakel averages were
    fetched for the top 150 of October 2026 only, and Mastercaller fills the gap from then on. No action."""
    n = len(tracked_without_history)
    status = GREEN if n <= NEW_PLAYERS_LIMIT else YELLOW
    out = [Check("players", "name matching", status, f"{n} tracked players without results",
                 "Tracked players (Order of Merit top 150) with no result under their name"
                 + (f": {', '.join(tracked_without_history[:10])}." if n else "."),
                 "" if status == GREEN else "Probably a different spelling in another source: add the name to "
                 "config/player_aliases.yml (edit on GitHub).")]
    if without_stats:
        out.append(Check("players", "averages", GREEN, f"{len(without_stats)} tracked players without averages",
                         "Known gap, no action needed: these players have results (and so an Elo rating, used for "
                         "their strength in tournament simulations) but no 3-dart averages yet, because averages from "
                         "Darts Orakel cover the top 150 of October 2026 only. Mastercaller adds their averages from "
                         "their next matches: " + ", ".join(without_stats[:10]) + ".", ""))
    return out


def model(registry_latest: dict | None) -> Check:
    if not registry_latest:
        return Check("model", "promotion", RED, "no model", "No model version registered.", "Run the full refresh.")
    if registry_latest["status"] == "active":
        return Check("model", "promotion", GREEN, registry_latest["version"], f"Active model {registry_latest['version']}: {registry_latest['reason']}.")
    return Check("model", "promotion", YELLOW, f"{registry_latest['version']} not activated",
                 f"The new fit {registry_latest['version']} was not activated: {registry_latest['reason']}. The app keeps "
                 "using the previous model.",
                 "Review the selection log (darts_gold.pi_selection_log). If the change is wanted, activate it on purpose.")


def benchmark(bench: pd.DataFrame | None) -> list[Check]:
    """The key test: is the PI significantly better than the PDC Order of Merit (on majors and overall)?"""
    if bench is None or bench.empty:
        return [Check("model", "beats PDC ranking", YELLOW, "not computed", "The key test against the Order of Merit did not run.")]
    out = []
    for dataset, label in (("walk-forward majors", "on majors"), ("walk-forward all", "on all matches")):
        rows = bench[(bench["dataset"] == dataset) & (bench["model"] == "PI model")]
        if rows.empty:
            continue
        row = rows.iloc[0]
        ok = bool(row["model_significantly_better"])
        out.append(Check("model", f"beats PDC ranking {label}", GREEN if ok else YELLOW,
                         f"log-loss gain {row['log_loss_gain']:+.4f} [{row['gain_ci_low']:+.4f}, {row['gain_ci_high']:+.4f}]",
                         f"The model predicts winners {label} significantly better than the PDC Order of Merit." if ok else
                         f"The model is NOT significantly better than the PDC Order of Merit {label}.",
                         "" if ok else "Investigate before trusting the PI: compare predictors and data quality."))
    return out or [Check("model", "beats PDC ranking", YELLOW, "not computed", "No walk-forward result found.")]


def report(checks: list[Check]) -> pd.DataFrame:
    df = pd.DataFrame([asdict(c) for c in checks])
    df["severity"] = df["status"].map(ORDER)
    return df.sort_values(["severity", "area", "check"], ascending=[False, True, True]).drop(columns="severity")


def overall(df: pd.DataFrame) -> str:
    return max(df["status"], key=ORDER.get) if len(df) else GREEN
