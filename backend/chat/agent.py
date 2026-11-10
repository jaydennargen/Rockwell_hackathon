"""Chat agent (Agent 3). chat_reply(report, history, message, user) -> ChatMessage dict.

`report` is already role-filtered by the route, so the agent only sees what this user may see.
Requester: context = this report + its procedure section, NO tools.
Specialist: full report + tools (get_report, get_procedure, read-only run_sql); CHAT_MODE=genie sends
the question to the Genie space instead. See ARCHITECTURE.md §5.
"""
import json
import uuid
from datetime import datetime, timezone

from app import config
from chat import tools

MAX_TOOL_CALLS = 4

REQUESTER_PROMPT = """You help a field service technician with ONE repair order. Answer only from the
report below (including its troubleshooting procedure, which comes from a synthetic manual). Keep answers
short and practical. If the question is about anything else, or the report doesn't answer it, say a
repair specialist can help. Never claim cleaning or testing has been done. Never invent numbers.

REPORT:
{report}"""

SPECIALIST_PROMPT = """You help a repair specialist review repair orders. You have the current order's
full report below and tools: get_report, get_procedure, and run_sql (one read-only SELECT over the gold
tables). Use run_sql for any question about counts, rates, or history and base numbers only on its results.
Be concise. The troubleshooting manual is synthetic. Never claim cleaning or testing has been done.

CURRENT REPORT:
{report}"""


def _msg(content: str, **extra) -> dict:
    return {"id": uuid.uuid4().hex[:12], "role": "assistant", "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(), **extra}


def chat_reply(report: dict, history: list[dict], message: str, user: dict) -> dict:
    if report["status"] == "PROCESSING":
        return _msg("This order is still being triaged. Ask again in a few seconds.")
    if user["role"] != "specialist" and "predicted" not in report:
        return _msg("A repair specialist is reviewing this order, so there's no verified report to "
                    "discuss yet. You'll be able to ask about it here once it's released.")
    if config.CHAT_MODE == "fake":
        return _fake_reply(report, message, user)
    if user["role"] == "specialist" and config.CHAT_MODE == "genie":
        from chat.genie import ask_genie
        return _msg(**ask_genie(message, report["order_id"]))
    return _agent_reply(report, history, message, user)


def _source_procedure(report: dict) -> list[dict]:
    proc = report.get("procedure") or {}
    return [{"label": f"Procedure: {proc.get('title', 'General protocol')} (synthetic manual)",
             "ref": f"order:{report['order_id']}#procedure"}] if proc else []


def _client():
    from app import dbx
    return dbx.openai_client()


def _agent_reply(report: dict, history: list[dict], message: str, user: dict, client=None) -> dict:
    specialist = user["role"] == "specialist"
    client = client or _client()
    ctx = json.dumps({k: v for k, v in report.items() if k != "trace_id"}, default=str)
    system = (SPECIALIST_PROMPT if specialist else REQUESTER_PROMPT).format(report=ctx)
    msgs = [{"role": "system", "content": system}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history[-10:]]
    msgs.append({"role": "user", "content": message})
    kw = {"tools": tools.TOOL_SPECS} if specialist else {}   # requester: never any tools

    sql, sources = None, _source_procedure(report)
    for _ in range(MAX_TOOL_CALLS + 1):
        r = client.chat.completions.create(model=config.LLM_ENDPOINT, messages=msgs, temperature=0,
                                           max_tokens=700, **kw)
        choice = r.choices[0].message
        calls = getattr(choice, "tool_calls", None) or []
        if not specialist or not calls:
            return _msg(choice.content or "I couldn't produce an answer.", sql=sql, sources=sources or None)
        msgs.append({"role": "assistant", "content": choice.content or "",
                     "tool_calls": [c.model_dump() for c in calls]})
        for c in calls:
            result = _run_tool(c.function.name, json.loads(c.function.arguments or "{}"))
            if c.function.name == "run_sql" and result.get("sql"):
                sql = result["sql"]
                sources += [{"label": t, "ref": f"table:{t}"} for t in result.get("tables", [])]
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, default=str)[:12000]})
        if sum(1 for m in msgs if m["role"] == "tool") >= MAX_TOOL_CALLS:
            kw = {}  # out of tool budget: force a final answer
    return _msg("I hit the tool-call limit before finishing. Try a narrower question.", sql=sql)


def _run_tool(name: str, args: dict) -> dict:
    from triage.stats_repo import get_stats_repo
    if name == "run_sql":
        return tools.run_sql(args.get("query", ""), get_stats_repo())
    if name == "get_report":
        return tools.get_report(args.get("order_id", ""))
    if name == "get_procedure":
        return tools.get_procedure(args.get("section"))
    return {"error": f"Unknown tool {name}"}


def _fake_reply(report: dict, message: str, user: dict) -> dict:
    """CHAT_MODE=fake: deterministic answers from the report itself. No SQL is run."""
    proc = report.get("procedure") or {}
    steps = proc.get("steps") or []
    first = steps[0] if steps else "Follow the general troubleshooting protocol."
    causes = ", ".join(c.replace("_", " ") for c in (report.get("predicted") or {}).get("causes", []))
    text = f"The likely cause is {causes or 'not yet determined'}. A good first check: {first}"
    conf = report.get("confidence")
    if user["role"] == "specialist" and conf:
        weakest = min(conf.get("categories") or [{}], key=lambda c: c.get("score", 1), default={})
        why = "; ".join(conf["reasons"]) or "no escalation rules fired"
        text += f" Routing: {why}."
        if weakest:
            text += (f" Weakest prediction: {weakest['category'].replace('_', ' ')} "
                     f"({round(weakest['score'] * 100)}%). {weakest['reasons'][0]}")
    text += " (Placeholder reply: the live chat agent is off. Set CHAT_MODE=agent.)"
    return _msg(text, sources=_source_procedure(report) or None)
