"""The live triage pipeline: a fixed sequence of steps, 2 LLM agents. See ARCHITECTURE.md §5 and
docs/databricks_backend_spec.md §4-§6.

    clean_text -> triage_extractor (LLM) -> history_lookup -> repeat_return_check
    -> procedure_lookup -> parts_predictor -> confidence.score -> confidence.route
    -> report_writer (LLM) -> full report dict (validates against app.schemas.TriageReport)
"""
from __future__ import annotations

from datetime import datetime, timezone

from app import config
from app.schemas import Area
from triage import confidence, tools
from triage.agents import report_writer, triage_extractor
from triage.llm import get_llm
from triage.stats_repo import get_stats_repo
from triage.tracing import current_trace_id, trace


@trace
def triage(order: dict, stats=None, llm=None, evidence: list[dict] | None = None) -> dict:
    stats = stats or get_stats_repo()
    llm = llm or get_llm()
    now = datetime.now(timezone.utc).isoformat()
    order_id = f"{order['order_number']}-{order.get('line_number', 1000)}"

    text, informative = tools.clean_text(order.get("failure_details", ""))
    ext = triage_extractor(llm, text, informative, order["catalog"], order.get("part_description", ""))
    hist = tools.history_lookup(stats, order["catalog"])
    if not ext.causes and hist["top_cause"]:
        ext.causes = [hist["top_cause"]]  # no cause in the text: fall back to the family's history
    if not ext.areas and hist["area_dist"]:
        top_area = max(hist["area_dist"], key=hist["area_dist"].get)
        ext.areas = [Area(category=top_area, detail="From product history")]
    repeat = tools.repeat_return_check(stats, order.get("serial_number"), order.get("received_date"))
    sop, sop_match = tools.procedure_lookup([a.category for a in ext.areas], ext.causes)
    parts = tools.parts_predictor(stats, order["catalog"], ext.causes)

    bench = confidence.bench_support(evidence or [])
    value, categories = confidence.score(ext, hist, sop_match, bench)
    signals = {"informative": ext.text_informative, "n_labeled": hist["n_labeled"],
               "repeat_days": repeat["days"], "sop_match": sop_match, "bench": bench}
    status, reasons = confidence.route(value, config.CONFIDENCE_THRESHOLD, signals)

    areas = [a.model_dump() for a in ext.areas]
    npf_flag = hist["npf_rate"] >= 0.10 or "no_problem_found" in ext.causes
    summary = report_writer(llm, {
        "unit": order.get("part_description") or order["catalog"], "failure_text": text or None,
        "causes": ext.causes, "areas": areas, "sop_match": sop_match, "procedure": sop["title"],
        "repeat_days": repeat["days"], "npf_rate": hist["npf_rate"]})

    return {
        "order_id": order_id, "status": status, "status_label": status,
        "created_at": now, "updated_at": now,
        "header": {
            "order_number": str(order["order_number"]), "item": int(order.get("line_number", 1000)),
            "part_number": order.get("part_number") or "", "catalog": order["catalog"],
            "serial": order.get("serial_number"), "description": order.get("part_description") or "",
            "depot": order.get("depot"), "received_date": order.get("received_date"),
        },
        "customer_input": {"text": text or "No description provided", "informative": ext.text_informative},
        "summary": summary,
        "predicted": {"areas": areas, "causes": ext.causes, "rationale": ext.rationale},
        "procedure": {"section": sop.get("section"), "title": sop["title"], "synthetic": True,
                      "loto_required": tools.loto_rule(order.get("part_description", ""),
                                                       [a["category"] for a in areas]),
                      "steps": sop["steps"]},
        "unit_history": [{k: h[k] for k in ("order_id", "date", "causes")} for h in repeat["history"]],
        "review": None,
        "confidence": {"score": value, "threshold": config.CONFIDENCE_THRESHOLD, "reasons": reasons,
                       "categories": categories, "signals": signals},
        "parts_to_prestage": parts,
        "npf_risk": {"family_rate": round(hist["npf_rate"], 3), "flag": npf_flag},
        "bench_evidence": evidence or [],
        "trace_id": current_trace_id(),
        "error": None,
        "pending_sections": ["cleaning", "testing"],
    }
