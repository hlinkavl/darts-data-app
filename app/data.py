"""Data access: gold tables from the Databricks SQL warehouse, or a local snapshot for development.

DARTS_DATA=databricks (default inside a Databricks App): SQL warehouse via the app's service principal
(DATABRICKS_WAREHOUSE_ID from the app resource). DARTS_DATA=local: data/app_snapshot/*.parquet built by
scripts/build_local_snapshot.py.
"""

import os
from pathlib import Path

import pandas as pd
import streamlit as st

MODE = os.getenv("DARTS_DATA", "databricks" if os.getenv("DATABRICKS_APP_NAME") else "local")
CATALOG = os.getenv("DARTS_CATALOG", "workspace")
SNAPSHOT = Path(os.getenv("DARTS_SNAPSHOT", Path(__file__).resolve().parent.parent / "data" / "app_snapshot"))

SCHEMA = {"players": "darts_silver"}  # everything else lives in darts_gold


@st.cache_resource(ttl=300)
def _connection():
    from databricks import sql
    from databricks.sdk.core import Config

    cfg = Config()
    return sql.connect(server_hostname=cfg.host,
                       http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
                       credentials_provider=lambda: cfg.authenticate)


@st.cache_data(ttl=600, show_spinner=False)
def table(name: str, where: str | None = None) -> pd.DataFrame:
    """A whole gold table (or silver.players), optionally filtered with a SQL condition."""
    if MODE == "local":
        path = SNAPSHOT / f"{name}.parquet"
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_parquet(path)
        return df.query(_pandas_condition(where)) if where else df
    query = f"SELECT * FROM {CATALOG}.{SCHEMA.get(name, 'darts_gold')}.{name}" + (f" WHERE {where}" if where else "")
    try:
        with _connection().cursor() as cur:
            cur.execute(query)
            return cur.fetchall_arrow().to_pandas()
    except Exception as exc:  # a table that doesn't exist yet (e.g. no draw parsed) must not break a page
        st.session_state.setdefault("data_errors", {})[name] = str(exc)[:300]
        return pd.DataFrame()


def _pandas_condition(where: str) -> str:
    """The few SQL conditions the app uses, translated for DataFrame.query."""
    return where.replace(" = ", " == ").replace(" AND ", " and ").replace(" OR ", " or ")


# ------------------------------------------------------------------------------------------------ helpers

def active_version() -> str | None:
    reg = table("pi_model_registry")
    if reg.empty:
        return None
    active = reg[reg["status"] == "active"].sort_values("decided_at")
    return active["version"].iloc[-1] if len(active) else None


def versioned(name: str) -> pd.DataFrame:
    """Rows of the active model version of a versioned table (pi_coefficients, pi_benchmark, ...)."""
    df = table(name)
    v = active_version()
    return df[df["version"] == v] if v and "version" in df.columns else df


def current_pi() -> pd.DataFrame:
    df = table("performance_index")
    return df[df["is_current"]].sort_values("rank") if len(df) else df


def players() -> pd.DataFrame:
    return table("players")


def data_status() -> dict:
    """When the data was last refreshed and how healthy it is (for the sidebar)."""
    report = table("health_report")
    status = "green"
    if len(report):
        order = {"green": 0, "yellow": 1, "red": 2}
        status = max(report["status"], key=order.get)
    info = table("snapshot_info") if MODE == "local" else pd.DataFrame()
    pi = current_pi()
    return {
        "mode": MODE,
        "status": status,
        "checked_at": report["checked_at"].max() if len(report) else None,
        "data_until": (info["data_until"].iloc[0] if len(info) else
                       (pd.to_datetime(pi["as_of_date"]).max() - pd.Timedelta(days=1) if len(pi) else None)),
        "model_version": active_version(),
    }
