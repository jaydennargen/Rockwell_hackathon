"""PIPELINE=mock: deterministic, template-based triage reports.

Lets the frontend and API run without Databricks or an LLM, and shows both routing paths:
  - uninformative failure text  -> NEEDS_REVIEW
  - no manual section matches    -> NEEDS_REVIEW
  - otherwise                    -> AUTO_RELEASED

Part frequencies and NPF rates in the templates were computed from the provided SAP
extract (labeled orders per product family) but are NOT model output. WS4 replaces
this module's role with triage.pipeline.triage().
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

MANUAL = json.loads((Path(__file__).parent / "data" / "manual_sops.json").read_text())
THRESHOLD = 0.70

_NOISE = re.compile(
    r"\b(?:SERIAL(?: NUMBER)?|S/N|SN)\s*[:=#]\s*\S+"   # Serial Number: X, SN:X, S/N: X
    r"|\bSN\s+\d\S*"                                    # SN 31805783 (not SNAPPED)
    r"|SHIP/END CUSTOMER PO:?\s*\S+"
    r"|\bPO\s*(?:#|NO\.?)?\s*[:=#]\s*\S+|\bPO#\S+"       # PO#=123, PO: 123 (not POWER)
    r"|RAAMP BARCODE\s*=\s*\S+|STORES(?: CODE)?#?\s*=\s*\S+|CAT#\s*=\s*\S+",
    re.I,
)
_EMPTY = re.compile(
    r"NO (REASON|INFORMATION|INFO|SUFFICIENT)|NOT SPECIFIED|UNKNOWN|NOT REPORTED|NO PROVIDED|"
    r"DID NOT IDENTIFY|FAILURE NOT SPECIFIED|NO FAILURE",
    re.I,
)


def clean_text(raw: str) -> tuple[str, bool]:
    text = _NOISE.sub(" ", raw or "")
    text = re.sub(r"\s+", " ", text).strip(" -/:.'\"")
    informative = len(text) >= 8 and not _EMPTY.search(text)
    return text, informative


def _sop(area: str, cause: str) -> dict | None:
    for s in MANUAL["sections"]:
        if s["area_category"] == area and s["cause_category"] == cause:
            return s
    return None


# (match on catalog/description, template)
TEMPLATES = [
    (re.compile(r"1394|AXIS MOD|MOD AXIS", re.I), {
        "areas": [("fan_cooling", "Component - Fan Assembly"), ("pcba_circuitry", "Component - Bus Capacitor")],
        "causes": ["wear_out"], "lookup": ("fan_cooling", "wear_out"),
        "rationale": "1394 axis modules most often come back with worn bus capacitors and cooling fans; "
                     "wear-out is the leading cause for this family.",
        "parts": [("21509-589-01-CAP,AL ELT-220uF,450V,20%,SNAP,35x30", 0.52, 231),
                  ("74102-021-02-AXIS SLIDER", 0.48, 231),
                  ("9101-1520-FAN,AXL,12VDC,40X15MM,8CFM", 0.28, 231)],
        "npf": 0.138, "score": 0.81,
    }),
    (re.compile(r"^R?MP|SERVO MOTOR", re.I), {
        "areas": [("motor_mechanical", "Motors - Bearings"), ("motor_mechanical", "Motors - Encoder / Resolver")],
        "causes": ["wear_out"], "lookup": ("motor_mechanical", "wear_out"),
        "rationale": "MP-Series servo motor returns are dominated by bearing and encoder wear.",
        "parts": [("PN-57548-S/A,HARNESS,STEGMANN,MPF,460V", 0.67, 305),
                  ("PN-67485- MP-SER,ENCODER,STEG,SINGLE-TURN,GII", 0.50, 305),
                  ("6203-2RS-BEARING SEALED RACE 2 X SEALS", 0.38, 305)],
        "npf": 0.006, "score": 0.86,
    }),
    (re.compile(r"2711|PANELVIEW", re.I), {
        "areas": [("hmi_display", "Touchscreen"), ("hmi_display", "Component - Bezel Assembly")],
        "causes": ["component_failure"], "lookup": ("hmi_display", "component_failure"),
        "rationale": "PanelView terminals most often need touch bezel overlays; the manual has no "
                     "procedure for HMI component failure.",
        "parts": [("PN-140697-PVP1250 Touch Bezel Overlay", 0.16, 556),
                  ("PN-140454-PVP1000 Touch Bezel Overlay", 0.10, 556),
                  ("PN-621795-2711P, BEZEL,15 IN TOUCH, SUB-ASSY", 0.10, 556)],
        "npf": 0.028, "score": 0.74,
    }),
]
DEFAULT = {
    "areas": [("pcba_circuitry", "PCBA - Other")], "causes": ["component_failure"],
    "lookup": ("pcba_circuitry", "component_failure"),
    "rationale": "Component failure on a circuit board is the most common outcome across all product families.",
    "parts": [], "npf": 0.076, "score": 0.62,
}

REASON_TEXT = {
    "uninformative": "The failure description didn't include usable details.",
    "low_score": "This product family's repair history doesn't point clearly to one cause.",
    "no_sop": "No troubleshooting procedure covers this type of failure yet.",
    "repeat": "This unit was repaired recently and came back.",
}


def mock_triage(order: dict, now: datetime | None = None) -> dict:
    """Build a FULL (unfiltered) report dict matching schemas.TriageReport."""
    now = now or datetime.now(timezone.utc)
    key = f"{order.get('catalog','')} {order.get('part_description','')}"
    tpl = next((t for rx, t in TEMPLATES if rx.search(key)), DEFAULT)
    text, informative = clean_text(order.get("failure_details", ""))
    sop = _sop(*tpl["lookup"])

    score = tpl["score"] - (0.25 if not informative else 0.0)
    reasons = []
    if not informative:
        reasons.append(REASON_TEXT["uninformative"])
    if tpl["score"] < THRESHOLD:  # weak history on its own, not just weak text
        reasons.append(REASON_TEXT["low_score"])
    if sop is None:
        reasons.append(REASON_TEXT["no_sop"])
    status = "NEEDS_REVIEW" if reasons else "AUTO_RELEASED"

    proc = sop or MANUAL["general"]
    areas = [{"category": c, "detail": d} for c, d in tpl["areas"]]
    order_id = f"{order['order_number']}-{order.get('line_number', 1000)}"
    summary = (
        f"Likely {tpl['causes'][0].replace('_', ' ')} in "
        f"{', '.join(a['detail'] for a in areas)}. "
        + ("Start with the troubleshooting steps below and confirm before replacing parts."
           if sop else "No matching procedure; use the general protocol.")
    )
    return {
        "order_id": order_id,
        "status": status,
        "status_label": status,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "header": {
            "order_number": str(order["order_number"]),
            "item": int(order.get("line_number", 1000)),
            "part_number": order.get("part_number", "") or "",
            "catalog": order["catalog"],
            "serial": order.get("serial_number"),
            "description": order.get("part_description", "") or "",
            "depot": order.get("depot"),
            "received_date": order.get("received_date"),
        },
        "customer_input": {"text": text or "No description provided", "informative": informative},
        "summary": summary,
        "predicted": {"areas": areas, "causes": tpl["causes"], "rationale": tpl["rationale"]},
        "procedure": {
            "section": proc["section"], "title": proc["title"], "synthetic": True,
            "loto_required": True, "steps": proc["steps"],
        },
        "unit_history": [],
        "review": None,
        "confidence": {"score": round(max(score, 0.05), 2), "threshold": THRESHOLD, "reasons": reasons},
        "parts_to_prestage": [{"part": p, "freq": f, "n": n} for p, f, n in tpl["parts"]],
        "npf_risk": {"family_rate": tpl["npf"], "flag": tpl["npf"] >= 0.10},
        "bench_evidence": [],
        "trace_id": f"mock-{order_id}",
        "error": None,
        "pending_sections": ["cleaning", "testing"],
    }
