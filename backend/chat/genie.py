"""Genie Conversation API client for CHAT_MODE=genie (specialist data questions).

Endpoints per the Databricks Genie Conversation API: start-conversation, then poll the message until
COMPLETED and read its text / query attachments. Not yet run against a workspace: verify the paths and
response fields against the current docs when GENIE_SPACE_ID is set.
"""
import time

import httpx

from app import config

POLL_SECONDS, TIMEOUT_SECONDS = 1.5, 60


def ask_genie(question: str, order_id: str) -> dict:
    """Returns kwargs for a ChatMessage: content, sql?, sources?"""
    base = f"{config.DATABRICKS_HOST.rstrip('/')}/api/2.0/genie/spaces/{config.GENIE_SPACE_ID}"
    headers = {"Authorization": f"Bearer {config.DATABRICKS_TOKEN}"}
    with httpx.Client(headers=headers, timeout=30) as http:
        start = http.post(f"{base}/start-conversation",
                          json={"content": f"{question} (context: repair order {order_id})"}).raise_for_status().json()
        cid, mid = start["conversation_id"], start["message_id"]
        deadline = time.time() + TIMEOUT_SECONDS
        while True:
            msg = http.get(f"{base}/conversations/{cid}/messages/{mid}").raise_for_status().json()
            if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED") or time.time() > deadline:
                break
            time.sleep(POLL_SECONDS)
    if msg.get("status") != "COMPLETED":
        return {"content": "The data assistant didn't finish answering. Try again or rephrase."}
    text, sql = [], None
    for a in msg.get("attachments") or []:
        if a.get("text"):
            text.append(a["text"].get("content", ""))
        if a.get("query"):
            sql = a["query"].get("query")
            if a["query"].get("description"):
                text.append(a["query"]["description"])
    return {"content": "\n\n".join(t for t in text if t) or "No answer.", "sql": sql,
            "sources": [{"label": "Genie space", "ref": f"genie:{config.GENIE_SPACE_ID}"}]}
