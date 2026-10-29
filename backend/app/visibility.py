"""Server-side, role-based filtering of every report and list item.

The frontend never receives a field the role can't see. Covered by tests/test_visibility.py.
"""
from __future__ import annotations

import copy

BASE = {"order_id", "status", "status_label", "created_at", "updated_at",
        "header", "customer_input", "pending_sections"}

# Fields a requester may see once a report is released.
REQUESTER_RELEASED = BASE | {"summary", "predicted", "procedure", "unit_history", "review"}

# Never sent to requesters, whatever the status.
SPECIALIST_ONLY = {"confidence", "parts_to_prestage", "npf_risk", "bench_evidence", "trace_id", "error"}

RELEASED = {"AUTO_RELEASED", "APPROVED", "EDITED"}

STATUS_LABELS = {
    "requester": {
        "PROCESSING": "Processing",
        "AUTO_RELEASED": "Report ready",
        "NEEDS_REVIEW": "With a specialist",
        "APPROVED": "Verified by specialist",
        "EDITED": "Verified by specialist",
        "REJECTED": "Closed, see specialist notes",
        "FAILED": "Couldn't process, try again",
    },
    "specialist": {
        "PROCESSING": "Processing",
        "AUTO_RELEASED": "Auto-released",
        "NEEDS_REVIEW": "Needs review",
        "APPROVED": "Approved",
        "EDITED": "Edited",
        "REJECTED": "Rejected",
        "FAILED": "Failed",
    },
}

ESCALATION_MESSAGE = (
    "A repair specialist is reviewing this order before a report is released. "
    "You'll see the report here once it's verified."
)


def status_label(status: str, role: str) -> str:
    return STATUS_LABELS[role][status]


def filter_report(full: dict, role: str) -> dict:
    """Return the copy of a full (unfiltered) report that `role` may see."""
    r = copy.deepcopy(full)
    r["status_label"] = status_label(r["status"], role)
    if role == "specialist":
        r.pop("escalation", None)
        return r

    status = r["status"]
    if status in RELEASED:
        allowed = REQUESTER_RELEASED
    elif status == "NEEDS_REVIEW":
        allowed = BASE | {"escalation"}
        reasons = (full.get("confidence") or {}).get("reasons", [])
        r["escalation"] = {"message": ESCALATION_MESSAGE, "reasons": reasons}
    elif status == "REJECTED":
        allowed = BASE | {"review"}
    else:  # PROCESSING, FAILED
        allowed = BASE
    return {k: v for k, v in r.items() if k in allowed and k not in SPECIALIST_ONLY}


def filter_summary(summary: dict, role: str) -> dict:
    s = dict(summary)
    s["status_label"] = status_label(s["status"], role)
    if role != "specialist":
        s["confidence_score"] = None
        s["top_reason"] = None
    return s
