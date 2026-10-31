"""Ask the data: natural-language questions through a Databricks Genie space (connected in the next step)."""

import streamlit as st


def render() -> None:
    st.title("🔎 Ask the data")
    st.info("Coming soon: ask questions in plain English (\"Who has the best average on majors this year?\") and get the "
            "answer with the SQL behind it, powered by a Databricks Genie space over the gold tables.")
