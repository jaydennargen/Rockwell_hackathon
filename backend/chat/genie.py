"""Genie Conversation API for CHAT_MODE=genie (specialist data questions), through the Databricks SDK
(auth from app/dbx.py). The app's service principal needs CAN RUN on the space (the genie-space resource)
and SELECT on the tables behind it.
"""
from datetime import timedelta

from app import config, dbx


def ask_genie(question: str, order_id: str) -> dict:
    """Returns kwargs for a ChatMessage: content, sql?, sources?"""
    if not config.GENIE_SPACE_ID:
        raise dbx.DatabricksUnavailable("GENIE_SPACE_ID isn't set (the app's genie-space resource).")
    msg = dbx.workspace().genie.start_conversation_and_wait(
        config.GENIE_SPACE_ID, f"{question} (context: repair order {order_id})", timeout=timedelta(seconds=90))
    status = getattr(msg.status, "value", msg.status)
    if status != "COMPLETED":
        return {"content": "The data assistant didn't finish answering. Try again or rephrase."}
    text, sql = [], None
    for a in msg.attachments or []:
        if a.text and a.text.content:
            text.append(a.text.content)
        if a.query:
            sql = a.query.query
            if a.query.description:
                text.append(a.query.description)
    return {"content": "\n\n".join(text) or "No answer.", "sql": sql,
            "sources": [{"label": "Genie space", "ref": f"genie:{config.GENIE_SPACE_ID}"}]}
