"""Ask the data: natural-language questions through the Databricks Genie space (config/genie/space.yml).

The space id comes from the app's genie-space resource (GENIE_SPACE_ID); the app's service principal asks the
questions, so it needs CAN RUN on the space and SELECT on its tables.
"""

import os

import pandas as pd
import streamlit as st

SPACE_ID = os.getenv("GENIE_SPACE_ID")
SAMPLES = ["Who are the top 10 players by Performance Index right now?",
           "Who had the highest 3-dart average in a major match in 2026?",
           "How many majors has Luke Littler won since 2021?",
           "Which players improved their PI the most in the last 3 months?"]


@st.cache_resource
def _client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _ask(question: str) -> dict:
    """One question to Genie (follow-ups stay in the same conversation): text, SQL and the result table."""
    w = _client()
    conv = st.session_state.get("genie_conversation")
    msg = (w.genie.create_message_and_wait(SPACE_ID, conv, question) if conv
           else w.genie.start_conversation_and_wait(SPACE_ID, question))
    st.session_state["genie_conversation"] = msg.conversation_id
    answer = {"question": question, "text": None, "sql": None, "table": None}
    for att in msg.attachments or []:
        if att.text and att.text.content:
            answer["text"] = att.text.content
        if att.query:
            answer["sql"] = att.query.query
            answer["text"] = answer["text"] or att.query.description
            res = w.genie.get_message_attachment_query_result(SPACE_ID, msg.conversation_id, msg.message_id or msg.id,
                                                              att.attachment_id)
            sr = res.statement_response
            if sr and sr.manifest and sr.result:
                cols = [c.name for c in sr.manifest.schema.columns]
                answer["table"] = pd.DataFrame(sr.result.data_array or [], columns=cols)
    return answer


def _show(a: dict) -> None:
    with st.chat_message("user"):
        st.markdown(a["question"])
    with st.chat_message("assistant"):
        if a.get("error"):
            st.error(a["error"])
            return
        if a["text"]:
            st.markdown(a["text"])
        if a["table"] is not None:
            st.dataframe(a["table"], hide_index=True, width="stretch")
        if a["sql"]:
            with st.expander("SQL behind the answer"):
                st.code(a["sql"], language="sql")


def render() -> None:
    st.title("🔎 Ask the data")
    if not SPACE_ID:
        st.info("Ask questions in plain English (\"Who had the highest average in a major match this year?\") and get "
                "the answer with the SQL behind it, powered by a Databricks Genie space over the gold tables. "
                "Available in the deployed app.")
        return
    st.caption("Answers come from Databricks Genie, which writes SQL over this app's tables. Check the SQL for "
               "anything important. Follow-up questions keep the context.")
    history = st.session_state.setdefault("genie_history", [])
    if not history:
        cols = st.columns(2)
        for i, q in enumerate(SAMPLES):
            if cols[i % 2].button(q, key=f"sample_{i}", width="stretch"):
                st.session_state["genie_pending"] = q
    question = st.chat_input("Ask about players, averages, titles or majors…") or st.session_state.pop("genie_pending", None)
    if question:
        with st.spinner("Genie is writing the SQL…"):
            try:
                history.append(_ask(question))
            except Exception as exc:  # Genie unavailable (e.g. compute quota): show it, keep the page alive
                history.append({"question": question, "error": f"Genie could not answer: {str(exc)[:300]}"})
    for a in history:
        _show(a)
    if history and st.button("New conversation"):
        st.session_state.pop("genie_conversation", None)
        st.session_state["genie_history"] = []
        st.rerun()
