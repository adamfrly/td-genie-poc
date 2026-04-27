"""TD Rahona — Ask Genie.

A minimal Streamlit chat UI that forwards prompts to a Databricks Genie Space
via the Conversation API. Designed to run on Databricks Apps (OBO auth) and
locally via `streamlit run app.py` with a .env file.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient
from dotenv import load_dotenv

load_dotenv()

SPACE_ID = os.environ.get("GENIE_SPACE_ID", "").strip()
POLL_INTERVAL_SECONDS = 2
POLL_TIMEOUT_SECONDS = 120

TD_GREEN = "#2FBF00"
TD_DARK_GREEN = "#038203"
TD_FOREST = "#1A5336"
TD_BLACK = "#1C1C1C"
TD_BUBBLE_BG = "#F2F2F2"

ASSET_DIR = Path(__file__).parent / "assets"


@st.cache_resource
def get_client() -> WorkspaceClient:
    return WorkspaceClient()


SPACE_BASE = f"/api/2.0/genie/spaces/{SPACE_ID}"


def _message_path(conversation_id: str, message_id: str | None = None, suffix: str = "") -> str:
    path = f"{SPACE_BASE}/conversations/{conversation_id}/messages"
    if message_id is None:
        return path
    return f"{path}/{message_id}{suffix}"


def start_or_continue(prompt: str, conversation_id: str | None) -> tuple[str, str]:
    w = get_client()
    if conversation_id is None:
        resp = w.api_client.do("POST", f"{SPACE_BASE}/start-conversation", body={"content": prompt})
        return resp["conversation_id"], resp["message_id"]
    resp = w.api_client.do("POST", _message_path(conversation_id), body={"content": prompt})
    return conversation_id, resp["message_id"]


def poll(conversation_id: str, message_id: str) -> dict:
    w = get_client()
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        msg = w.api_client.do("GET", _message_path(conversation_id, message_id))
        status = msg.get("status")
        if status == "COMPLETED":
            return msg
        if status in ("FAILED", "CANCELLED"):
            err = (msg.get("error") or {}).get("message") or status
            raise RuntimeError(err)
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Genie took longer than {POLL_TIMEOUT_SECONDS}s to respond.")


def fetch_query_result(conversation_id: str, message_id: str, attachment_id: str) -> pd.DataFrame | None:
    w = get_client()
    path = _message_path(conversation_id, message_id, f"/attachments/{attachment_id}/query-result")
    resp = w.api_client.do("GET", path)
    statement = (resp or {}).get("statement_response") or {}
    manifest = statement.get("manifest") or {}
    result = statement.get("result") or {}
    columns = [c["name"] for c in (manifest.get("schema") or {}).get("columns", [])]
    rows = result.get("data_array") or []
    if not columns or not rows:
        return None
    return pd.DataFrame(rows, columns=columns)


def _extract_text_and_query_attachment(msg: dict) -> tuple[str, str | None]:
    """Return (assistant text, id of first attachment with a SQL query, if any)."""
    text_parts: list[str] = []
    query_attachment_id: str | None = None
    for att in msg.get("attachments") or []:
        text_att = att.get("text") or {}
        if text_att.get("content"):
            text_parts.append(text_att["content"])
        if att.get("query") and query_attachment_id is None:
            query_attachment_id = att.get("attachment_id")
    if not text_parts and msg.get("content"):
        text_parts.append(msg["content"])
    return "\n\n".join(text_parts).strip() or "(no text response)", query_attachment_id


def ask_genie(prompt: str) -> dict:
    try:
        conversation_id, message_id = start_or_continue(prompt, st.session_state.conversation_id)
        st.session_state.conversation_id = conversation_id
        msg = poll(conversation_id, message_id)
        text, query_attachment_id = _extract_text_and_query_attachment(msg)
        dataframe = (
            fetch_query_result(conversation_id, message_id, query_attachment_id)
            if query_attachment_id
            else None
        )
        return {"text": text, "dataframe": dataframe}
    except Exception as exc:
        return {"text": f":red[**Error:** {exc}]", "dataframe": None, "error": True}


# --- UI -----------------------------------------------------------------------

st.set_page_config(page_title="TD Rahona — Ask Genie", page_icon=str(ASSET_DIR / "td-logo.png"), layout="centered")

st.markdown(
    f"""
    <style>
      .td-header {{
        background-color: {TD_GREEN};
        padding: 14px 20px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 18px;
      }}
      .td-header h1 {{
        color: white;
        font-size: 1.4rem;
        margin: 0;
        font-weight: 600;
      }}
      [data-testid="stChatMessage"][aria-label="user"] {{
        background-color: {TD_GREEN};
      }}
      [data-testid="stChatMessage"][aria-label="user"] * {{
        color: white !important;
      }}
      [data-testid="stChatMessage"][aria-label="assistant"] {{
        background-color: {TD_BUBBLE_BG};
      }}
      a {{ color: {TD_DARK_GREEN}; }}
      h1, h2, h3 {{ color: {TD_FOREST}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

header_col1, header_col2 = st.columns([1, 8], gap="small")
with header_col1:
    st.image(str(ASSET_DIR / "td-logo.png"), width=56)
with header_col2:
    st.markdown("### TD Rahona — Ask Genie")
    st.caption("Ask questions about TD Rahona data. Powered by Databricks Genie.")

if not SPACE_ID:
    st.error(
        "`GENIE_SPACE_ID` is not set. In Databricks Apps, set it in `app.yaml`. "
        "Locally, add it to your `.env` file. See the README."
    )
    st.stop()

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["text"])
        if m.get("dataframe") is not None:
            st.dataframe(m["dataframe"], use_container_width=True)

prompt = st.chat_input("Ask about TD Rahona data…")
if prompt:
    st.session_state.messages.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.status("Thinking…", expanded=False):
            result = ask_genie(prompt)
        st.markdown(result["text"])
        if result.get("dataframe") is not None:
            st.dataframe(result["dataframe"], use_container_width=True)
    st.session_state.messages.append(
        {"role": "assistant", "text": result["text"], "dataframe": result.get("dataframe")}
    )
