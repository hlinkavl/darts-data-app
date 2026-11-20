"""Snapshot of the tables the app reads, for the public copy of the app (Streamlit Community Cloud).

The health task writes them as parquet to the Volume (APP_SNAPSHOT_DIR); the publish-app workflow downloads them
and pushes them with the app code to the `public-app` branch, which Streamlit Community Cloud serves. The public app
needs no Databricks compute and keeps working when the workspace is stopped or out of quota.
"""

from datetime import date
from decimal import Decimal

import pandas as pd

# table -> schema; everything the app's data.table() / data.versioned() reads
APP_TABLES = {
    "players": "darts_silver",
    **{name: "darts_gold" for name in [
        "health_report", "majors_calendar", "performance_index", "pi_benchmark", "pi_calibration",
        "pi_coefficients", "pi_model_registry", "pi_selection_log", "player_narratives", "player_news",
        "player_recent_matches", "player_titles", "tournament_backtest_summary", "tournament_draw_matches",
        "tournament_predictions", "upcoming_matches"]},
}
APP_SNAPSHOT_DIR = "/Volumes/{catalog}/darts_bronze/raw/app_snapshot"


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Types as the app gets them from the SQL warehouse: timestamps without a time zone (UTC), decimals as
    floats, dates as datetime64. Clears df.attrs: Spark Connect puts its plan metrics there, which to_parquet
    cannot serialise."""
    df = df.copy()
    df.attrs = {}
    for col in df.columns:
        if isinstance(df[col].dtype, pd.DatetimeTZDtype):
            df[col] = df[col].dt.tz_convert("UTC").dt.tz_localize(None)
        elif df[col].dtype == object:
            sample = df[col].dropna()
            if not len(sample):
                continue
            if isinstance(sample.iloc[0], Decimal):
                df[col] = df[col].astype(float)
            elif isinstance(sample.iloc[0], date):
                df[col] = pd.to_datetime(df[col])
    return df
