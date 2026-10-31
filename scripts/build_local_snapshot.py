"""Build a local snapshot of the gold tables for developing the app without Databricks.

    python scripts/build_local_snapshot.py          # writes data/app_snapshot/<table>.parquet

Runs the same analytics code as the Databricks job (src/analytics) on the raw files in data/raw: Darts Orakel
results (until 28 Oct 2026), the Wikipedia Order of Merit, major pages and player background. Mastercaller
results are not merged here (the unification lives in the silver notebook), so the snapshot ends on
28 Oct 2026. Start the app on it with DARTS_DATA=local.
"""

import glob
import html
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from analytics import elo, health, overview, pipeline  # noqa: E402

RAW = REPO / "data" / "raw"
OUT = REPO / "data" / "app_snapshot"
TODAY = date.today()


def norm(name: str) -> str:
    return re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip()


def jsonl(pattern: str, latest_only: bool = False) -> list[dict]:
    files = sorted(glob.glob(str(RAW / pattern)))
    files = files[-1:] if latest_only else files
    return [json.loads(line) for f in files for line in open(f) if line.strip()]


def load_orakel() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for run_dir in sorted((RAW / "orakel").iterdir()):
        for stat in ("average", "first9_average", "checkout_pct", "180s"):
            f = run_dir / f"matches_{stat}.jsonl"
            if not f.exists():
                continue
            for line in open(f):
                r = json.loads(line)
                if not r["is_bye"]:
                    rows.append({**{k: r[k] for k in ("match_key", "player_key", "match_date", "tournament_key", "tournament_name",
                                                      "round", "category", "winner_key", "loser_key", "winner_name", "loser_name",
                                                      "winner_score", "loser_score")},
                                 "stat": stat, "s1": r["stat1"], "s2": r.get("stat2"), "run": run_dir.name})
    df = pd.DataFrame(rows).sort_values("run").drop_duplicates(["match_key", "player_key", "stat"], keep="last")
    for c in ("tournament_name", "winner_name", "loser_name"):
        df[c] = df[c].map(html.unescape)
    base = df.drop_duplicates(["match_key", "player_key"]).drop(columns=["stat", "s1", "s2", "run"])
    wide = df.pivot_table(index=["match_key", "player_key"], columns="stat", values=["s1", "s2"], aggfunc="max")
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    pm = base.merge(wide.reset_index(), on=["match_key", "player_key"]).rename(columns={
        "s1_average": "points", "s2_average": "darts", "s1_first9_average": "first9_points",
        "s2_first9_average": "first9_darts", "s1_checkout_pct": "checkouts_hit", "s2_checkout_pct": "checkout_attempts",
        "s1_180s": "one_eighties"})
    majors = yaml.safe_load((REPO / "config/majors.yml").read_text())["majors"]
    pm["match_date"] = pd.to_datetime(pm["match_date"].str[:10])
    pm["won"] = pm.player_key == pm.winner_key
    pm["opponent_key"] = np.where(pm.won, pm.loser_key, pm.winner_key)
    pm["opponent_name"] = np.where(pm.won, pm.loser_name, pm.winner_name)
    pm["score_for"] = np.where(pm.won, pm.winner_score, pm.loser_score)
    pm["score_against"] = np.where(pm.won, pm.loser_score, pm.winner_score)
    pm["is_major"] = pm.tournament_key.isin(majors)
    pm.loc[~(3 * pm.points / pm.darts).between(30, 140), ["points", "darts"]] = np.nan
    pm.loc[pm.checkouts_hit > pm.checkout_attempts, ["checkouts_hit", "checkout_attempts"]] = np.nan
    matches = pm.drop_duplicates("match_key")[["match_key", "match_date", "round", "winner_key", "loser_key", "is_major",
                                              "winner_name", "loser_name", "tournament_name"]]
    return pm, matches


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    majors = yaml.safe_load((REPO / "config/majors.yml").read_text())["majors"]
    pm, matches = load_orakel()

    # Player identity: Orakel keys, names from results; Order of Merit names matched by normalised name.
    names = {}
    for r in matches.itertuples():
        names.setdefault(norm(r.winner_name), r.winner_key)
        names.setdefault(norm(r.loser_name), r.loser_key)
    display = dict(zip(pm.player_key, pm.winner_name.where(pm.won, pm.loser_name)))
    display |= dict(zip(matches.winner_key, matches.winner_name)) | dict(zip(matches.loser_key, matches.loser_name))
    hist = pd.DataFrame(jsonl("wikipedia/*/rankings_history.jsonl")).drop_duplicates(["as_of", "player_name"])
    cur = pd.DataFrame(jsonl("wikipedia/*/rankings.jsonl", latest_only=True))
    for df in (hist, cur):
        df["player_key"] = df["player_name"].map(lambda n: names.get(norm(n)))
    rankings = (pd.concat([hist, cur]).dropna(subset=["player_key"]).rename(columns={"as_of": "snapshot_date"})
                [["snapshot_date", "player_key", "rank"]].astype({"player_key": "int64"}))

    run = pipeline.fit(pm, matches, f"v{TODAY.isoformat()}-local", rankings=rankings)
    version = run.version
    coef = run.coefficients

    tracked = cur.dropna(subset=["player_key"]).query("rank <= 150").astype({"player_key": "int64"})
    last = pm["match_date"].max() + pd.Timedelta(days=1)
    as_of = list(pd.date_range("2024-01-01", last, freq="MS")) + [last]
    index = pipeline.score(pm, run.elo_history, coef, tracked["player_key"].tolist(), as_of, rankings=rankings)
    index["player_name"] = index["player_key"].map(display)
    index["is_current"] = index["as_of_date"] == last.normalize()
    index["model_version"] = version

    # players
    orakel_rank = pd.DataFrame(jsonl("orakel/*/rankings.jsonl")).drop_duplicates("player_key", keep="last")
    background = pd.DataFrame(jsonl("wikipedia/*/player_background.jsonl"))
    background["key"] = background.get("player_key").fillna(background["name"].map(lambda n: names.get(norm(n))))
    background = background.dropna(subset=["key"]).drop_duplicates("key", keep="last").astype({"key": "int64"})
    players = pd.DataFrame({"player_key": list(display), "player_name": list(display.values())})
    players = players.merge(cur[["player_key", "rank", "prize_money"]].dropna().astype({"player_key": "int64"})
                            .rename(columns={"rank": "prize_money_rank", "prize_money": "prize_money_2y"}), on="player_key", how="left")
    players["is_tracked"] = players["prize_money_rank"].le(150).fillna(False)
    players = players.merge(orakel_rank[["player_key", "country", "dob"]].rename(columns={"dob": "date_of_birth"}), on="player_key", how="left")
    bg = background.drop(columns=["player_key"], errors="ignore").rename(columns={"key": "player_key"})
    for col in ("nickname", "image", "citizenship"):
        bg[col] = bg[col].map(lambda v: v[0] if isinstance(v, list) and v else None)
    players = players.merge(bg[["player_key", "nickname", "wikidata_id", "enwiki_title", "description", "intro", "image"]]
                            .rename(columns={"image": "image_file"}), on="player_key", how="left")

    # recent matches (player profiles)
    recent = pm[pm.player_key.isin(tracked.player_key)].copy()
    recent["average"] = (3 * recent.points / recent.darts).round(2)
    recent["first9_average"] = (3 * recent.first9_points / recent.first9_darts).round(2)
    recent["checkout_pct"] = (100 * recent.checkouts_hit / recent.checkout_attempts).round(2)
    recent = recent.sort_values(["player_key", "match_date", "match_key"], ascending=[True, False, False])
    recent["recency"] = recent.groupby("player_key").cumcount() + 1
    recent["result"] = np.where(recent.won, "W", "L")
    recent["score"] = recent.score_for.astype(str) + "-" + recent.score_against.astype(str)
    recent["player_name"] = recent.player_key.map(display)
    recent = recent[recent.recency <= 30][["player_key", "player_name", "recency", "match_date", "tournament_name", "round",
                                           "is_major", "opponent_key", "opponent_name", "result", "score", "average",
                                           "first9_average", "checkout_pct", "one_eighties"]]

    # tournaments
    pages = pd.DataFrame([p for p in jsonl("wikipedia/*/tournament_pages.jsonl", latest_only=True) if not p.get("error")])
    events = pd.DataFrame(jsonl("orakel/*/events.jsonl")).drop_duplicates("event_key", keep="last")
    events = events[events.tournament_key.isin(majors)][["tournament_key", "event_date", "winner_name", "winner_avg"]]
    events["event_date"] = pd.to_datetime(events["event_date"].str[:10])
    cal, draws = overview.season_calendar(pages[["title", "wikitext"]], events, majors, TODAY)
    current = index[index.is_current][["player_key", "strength_major", "pi", "pi_major", "effective_average", "avg_l30", "form"]] \
        .rename(columns={"strength_major": "strength"})
    elo_latest = run.elo_history.sort_values(["match_date", "match_key"]).groupby("player_key")["elo_post"].last().rename("elo").reset_index()
    outputs = overview.draw_outputs(
        cal, draws, players[["player_key", "player_name"]], current, elo_latest,
        strength_history=lambda: pipeline.StrengthHistory(pm, matches, coef["predictor"].tolist(), run.elo_params, rankings=rankings),
        today=TODAY)

    registry = pd.DataFrame([{"version": version, "status": "active", "reason": "local snapshot (development)",
                              "predictors": ", ".join(coef["predictor"]), "decided_at": pd.Timestamp.now(tz="UTC")}])
    test_ll = float(run.metrics.query("model == 'selected' and dataset == 'test'")["log_loss"].iloc[0])
    registry["test_log_loss"] = test_ll

    manifest = pd.DataFrame(jsonl("ingestion/*/manifest.jsonl", latest_only=True))
    last_run = pd.Timestamp(manifest["run_id"].iloc[0][:10]) if len(manifest) else None
    checks = (health.ingestion(manifest, last_run, TODAY, False) + [health.freshness(pm.match_date.max().date(), TODAY, False)]
              + health.draws(cal, TODAY) + [health.model(registry.iloc[0].to_dict())] + health.benchmark(run.benchmark)
              + [health.upcoming(False, 0)])
    health_report = health.report(checks).assign(checked_at=pd.Timestamp.now(tz="UTC"))

    tables = {
        "performance_index": index, "players": players, "player_recent_matches": recent,
        "pi_coefficients": coef.assign(version=version), "pi_selection_log": run.selection_log.reset_index(names="step_order").assign(version=version),
        "pi_metrics": run.metrics.assign(version=version), "pi_benchmark": run.benchmark.assign(version=version),
        "pi_calibration": run.calibration.assign(version=version), "pi_training_data": run.data_summary.assign(version=version),
        "pi_model_registry": registry, "majors_calendar": cal, "health_report": health_report,
        "upcoming_matches": overview.upcoming_cards(pd.DataFrame(), current, elo_latest, matches),
        "snapshot_info": pd.DataFrame([{"built_at": pd.Timestamp.now(tz="UTC"), "data_until": pm.match_date.max(),
                                        "model_version": version}]),
    } | outputs
    for name, df in tables.items():
        df = df.copy()
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].map(lambda v: v if v is None or isinstance(v, (str, bool, int, float)) else str(v))
        df.to_parquet(OUT / f"{name}.parquet", index=False)
        print(f"{name}: {len(df)} rows")


if __name__ == "__main__":
    main()
