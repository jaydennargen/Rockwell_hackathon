"""Specialist chat tools: get_report, get_procedure, run_sql (read-only: one SELECT over the gold
tables, forced LIMIT 200). The requester path never calls any of these."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

MAX_ROWS = 200
CHAT_TABLES = {"gold_family_stats", "gold_part_freq", "gold_repeat_returns", "gold_depot_patterns"}
MANUAL = json.loads((Path(__file__).resolve().parents[1] / "triage" / "data" / "manual_sops.json").read_text())

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|GRANT|REVOKE|ATTACH|DETACH|"
    r"PRAGMA|COPY|CALL|EXEC|EXECUTE|SET|USE|OPTIMIZE|VACUUM|REFRESH|CACHE|LOAD|INTO)\b", re.I)
_TABLE_REF = re.compile(r"\b(?:FROM|JOIN)\s+([`\"\w.]+)", re.I)
_LIMIT = re.compile(r"\bLIMIT\s+(\d+)\s*$", re.I)


class SqlRejected(ValueError):
    pass


def validate_sql(query: str) -> tuple[str, list[str]]:
    """Return (safe SQL with a LIMIT, tables used) or raise SqlRejected."""
    q = (query or "").strip()
    if not q:
        raise SqlRejected("Empty query.")
    if ";" in q:
        raise SqlRejected("Only a single statement is allowed (no ';').")
    if "--" in q or "/*" in q:
        raise SqlRejected("Comments are not allowed.")
    if not re.match(r"SELECT\b", q, re.I):
        raise SqlRejected("Only SELECT queries are allowed.")
    if m := _FORBIDDEN.search(q):
        raise SqlRejected(f"'{m.group(1).upper()}' is not allowed; queries are read-only.")
    tables = [t.strip('`"').split(".")[-1].lower() for t in _TABLE_REF.findall(q)]
    if not tables:
        raise SqlRejected("Query must read from a gold table.")
    bad = [t for t in tables if t not in CHAT_TABLES]
    if bad:
        raise SqlRejected(f"Only these tables can be queried: {', '.join(sorted(CHAT_TABLES))}.")
    if m := _LIMIT.search(q):
        q = q[: m.start()] + f"LIMIT {min(int(m.group(1)), MAX_ROWS)}"
    else:
        q = f"{q} LIMIT {MAX_ROWS}"
    return q, sorted(set(tables))


def run_sql(query: str, stats) -> dict:
    """Validate, qualify table names for the backend (Delta needs catalog.schema), and execute."""
    try:
        safe, tables = validate_sql(query)
    except SqlRejected as e:
        return {"error": str(e)}
    qualified = _TABLE_REF.sub(lambda m: m.group(0).replace(m.group(1), stats.t(m.group(1).strip('`"')
                                                                                   .split(".")[-1])), safe)
    try:
        cols, rows = stats.query(qualified)
    except Exception as e:  # noqa: BLE001
        return {"sql": safe, "error": str(e).splitlines()[0]}
    return {"sql": safe, "tables": tables, "columns": cols, "rows": [list(r) for r in rows[:MAX_ROWS]]}


def get_report(order_id: str) -> dict:
    """Full report for any order (specialists can see every order)."""
    from app.repo import get_repo
    row = get_repo().get_order(order_id)
    if not row:
        return {"error": f"Order {order_id} not found."}
    r = copy.deepcopy(row["report"])
    (r.get("confidence") or {}).pop("signals", None)
    return r


def get_procedure(section: int | None) -> dict:
    for s in MANUAL["sections"]:
        if s["section"] == section:
            return {**s, "synthetic": True}
    return {**MANUAL["general"], "synthetic": True}


TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "get_report", "description": "Get the full triage report for an order id like 67083053-1000.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}}},
    {"type": "function", "function": {
        "name": "get_procedure", "description": "Get a section (1-8) of the synthetic troubleshooting manual.",
        "parameters": {"type": "object", "properties": {"section": {"type": "integer"}}, "required": ["section"]}}},
    {"type": "function", "function": {
        "name": "run_sql",
        "description": "Run ONE read-only SELECT over the gold tables (no ';', max 200 rows). Tables: "
                       "gold_family_stats(product_family, n_labeled, cause_dist, area_dist, top_cause, "
                       "top_cause_share, npf_rate, median_tat); gold_part_freq(product_family, cause_category, "
                       "part, count, freq); gold_repeat_returns(serial_number, order_id, prev_order_id, "
                       "days_since_prev, prev_cause_category); gold_depot_patterns(depot, product_family, "
                       "cause_category, month, count).",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
]
