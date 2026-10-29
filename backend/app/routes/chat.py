import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.auth import current_user
from app.repo import get_repo
from app.routes.orders import _visible_row
from app.schemas import ChatHistory, ChatIn, ChatReply
from app.visibility import filter_report
from chat.agent import chat_reply

router = APIRouter(prefix="/api/orders")


@router.get("/{order_id}/chat", response_model=ChatHistory, response_model_exclude_none=True)
def history(order_id: str, user: dict = Depends(current_user)):
    _visible_row(order_id, user)
    return {"messages": get_repo().chat_history(order_id, user["email"])}


@router.post("/{order_id}/chat", response_model=ChatReply, response_model_exclude_none=True)
def send(order_id: str, body: ChatIn, user: dict = Depends(current_user)):
    row = _visible_row(order_id, user)
    repo = get_repo()
    hist = repo.chat_history(order_id, user["email"])
    msg = {"id": uuid.uuid4().hex[:12], "role": "user", "content": body.message,
           "created_at": datetime.now(timezone.utc).isoformat()}
    repo.add_chat(order_id, user["email"], msg)
    # The agent only ever sees what this user is allowed to see.
    visible = filter_report(row["report"], user["role"])
    reply = chat_reply(visible, hist, body.message, user)
    repo.add_chat(order_id, user["email"], reply)
    return {"reply": reply}
