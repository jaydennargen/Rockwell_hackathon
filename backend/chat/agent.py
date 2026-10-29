"""Chat agent (Agent 3). CHAT_MODE=fake is implemented here; WS5 adds agent + genie modes.

Requester: context = the role-filtered report only, no tools.
Specialist: full report + tools (get_report, get_procedure, read-only run_sql). See ARCHITECTURE.md §5.
"""
import uuid
from datetime import datetime, timezone

from app import config


def _msg(content: str, **extra) -> dict:
    return {"id": uuid.uuid4().hex[:12], "role": "assistant", "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(), **extra}


def chat_reply(report: dict, history: list[dict], message: str, user: dict) -> dict:
    if config.CHAT_MODE != "fake":
        raise NotImplementedError("WS5: implement agent/genie chat modes")
    return _fake_reply(report, message, user)


def _fake_reply(report: dict, message: str, user: dict) -> dict:
    oid = report["order_id"]
    if report["status"] == "PROCESSING":
        return _msg("This order is still being triaged. Ask again in a few seconds.")
    if user["role"] != "specialist" and "predicted" not in report:
        return _msg("A repair specialist is reviewing this order, so there's no verified report to "
                    "discuss yet. You'll be able to ask about it here once it's released.")
    proc = report.get("procedure") or {}
    steps = proc.get("steps") or []
    first = steps[0] if steps else "Follow the general troubleshooting protocol."
    causes = ", ".join(c.replace("_", " ") for c in (report.get("predicted") or {}).get("causes", []))
    text = (f"The likely cause is {causes or 'not yet determined'}. A good first check: {first} "
            "(This is a placeholder reply; the live chat agent is not connected yet.)")
    extra = {"sources": [{"label": f"Procedure: {proc.get('title', 'General protocol')}",
                          "ref": f"order:{oid}#procedure"}]}
    if user["role"] == "specialist":
        extra["sql"] = ("SELECT part, count, freq FROM gold_part_freq WHERE product_family = :family "
                        "AND cause_category = :cause ORDER BY count DESC LIMIT 3")
    return _msg(text, **extra)
