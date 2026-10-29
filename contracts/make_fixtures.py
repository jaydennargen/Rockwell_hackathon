"""Regenerate contracts/fixtures/*.json from the mock pipeline + visibility rules.

    python contracts/make_fixtures.py

The seed orders use real order numbers, catalogs, and failure text from the
provided SAP extract. Reports are produced by triage/mock.py (template-based, not model output).
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.visibility import filter_report, filter_summary  # noqa: E402
from triage.mock import mock_triage  # noqa: E402

OUT = ROOT / "contracts" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
T0 = datetime(2026, 10, 27, 14, 0, tzinfo=timezone.utc)

REQ = "requester@vanmeter.demo"
OTHER = "orders@midwestcontrols.demo"

SEED = [
    (REQ, {"order_number": "67083053", "line_number": 1000, "catalog": "R1394CAM75IH/C",
           "part_number": "PN-C74863", "part_description": "MOD AXIS INTL HTSNK 15KW 35.0A CONT",
           "serial_number": "1JAP5JK8", "depot": "P1100",
           "failure_details": "'No reason given - FQA Serial Number: 1JAP5JK8 Ship/End Customer PO: 140827129",
           "received_date": "2026-08-13"}, None),
    (REQ, {"order_number": "66650692", "line_number": 1000, "catalog": "RMPLB330PMK74AA/A",
           "part_number": "", "part_description": "MP-Series MPL 480V AC Rotary Servo Motor",
           "serial_number": "326193834", "depot": "P4080",
           "failure_details": "UNIT VISUALLY INSPECTED, NOTED ROTOR SEEMED TO SPIN VERY EASILY ALTHOUGH IT HAD A BRAKE. "
                              "ON INVESTIGATION, NOTICED THE ROTOR WAS SNAPPED.",
           "received_date": "2026-10-20"}, None),
    (REQ, {"order_number": "66417530", "line_number": 1000, "catalog": "R2711PK7C4D2/A",
           "part_number": "", "part_description": "PanelView Plus Terminal",
           "serial_number": "AW0CR7XO", "depot": "P4080",
           "failure_details": "LOGIC BOARDS IS FAULTY. SERIES IN A OUT A F/W REV IN 3.20.04",
           "received_date": "2026-10-22"}, None),
    (REQ, {"order_number": "66433026", "line_number": 1000, "catalog": "R1794ASB/E",
           "part_number": "", "part_description": "Flex Remote I/O Adaptor",
           "serial_number": "SD1ZU6LD", "depot": "P1190",
           "failure_details": "***FAULTED - NO INPUTS*** Serial Number: SD1ZU6LD Ship/End Customer PO: 4506251226",
           "received_date": "2026-10-18"},
     {"decision": "approve", "notes": "Confirmed: input circuit failure on the adaptor board. Proceed per Section 1.",
      "reviewer": "specialist@rockwell.demo"}),
    (OTHER, {"order_number": "66339318", "line_number": 1000, "catalog": "R2711PT6C21D8S/B",
             "part_number": "", "part_description": "PanelView Plus 7 Standard 600",
             "serial_number": "DE0AI4JH", "depot": "P1190",
             "failure_details": "UNKNOWN FAILURE Serial Number: DE0AI4JH Ship/End Customer PO: 33469",
             "received_date": "2026-10-24"}, None),
]


def dump(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, default=str) + "\n")


def main():
    seed = []
    for i, (who, order, review) in enumerate(SEED):
        t = T0 + timedelta(hours=5 * i)
        full = mock_triage(order, now=t)
        if review:
            full["status"] = "APPROVED"
            full["review"] = {**review, "reviewed_at": (t + timedelta(hours=2)).isoformat()}
            full["updated_at"] = full["review"]["reviewed_at"]
        seed.append({"submitted_by": who, "order": order, "report": full})
    dump("seed_orders.json", seed)

    def summary(s):
        r = s["report"]
        return {"order_id": r["order_id"], "catalog": r["header"]["catalog"],
                "part_description": r["header"]["description"], "serial_number": r["header"]["serial"],
                "status": r["status"], "status_label": r["status"], "submitted_by": s["submitted_by"],
                "created_at": r["created_at"], "confidence_score": r["confidence"]["score"],
                "top_reason": (r["confidence"]["reasons"] or [None])[0]}

    released = next(s["report"] for s in seed if s["report"]["status"] == "AUTO_RELEASED")
    escalated = next(s["report"] for s in seed if s["report"]["status"] == "NEEDS_REVIEW")

    dump("me_requester.json", {"email": REQ, "name": "Dana Whitfield", "role": "requester", "org": "Van Meter Inc"})
    dump("me_specialist.json", {"email": "specialist@rockwell.demo", "name": "Luis Ortega",
                                "role": "specialist", "org": "Rockwell Automation Lifecycle Services"})
    dump("order_in.json", SEED[1][1])
    mine = [filter_summary(summary(s), "requester") for s in seed if s["submitted_by"] == REQ]
    dump("orders_list_requester.json", {"items": mine, "total": len(mine)})
    allv = [filter_summary(summary(s), "specialist") for s in seed]
    dump("orders_list_specialist.json", {"items": allv, "total": len(allv)})
    dump("report_full_auto_released.json", filter_report(released, "specialist"))
    dump("report_full_needs_review.json", filter_report(escalated, "specialist"))
    dump("report_requester_released.json", filter_report(released, "requester"))
    dump("report_requester_escalated.json", filter_report(escalated, "requester"))
    oid = released["order_id"]
    dump("chat_history.json", {"messages": [
        {"id": "m1", "role": "user", "content": "What should the technician check first?",
         "created_at": "2026-10-27T19:05:00+00:00"},
        {"id": "m2", "role": "assistant",
         "content": "Start by listening for bearing noise and checking vibration before disassembly "
                    "(step 1 of the motor wear-out procedure). The reported snapped rotor points to "
                    "mechanical damage, so inspect the brake and rotor shaft before ordering parts.",
         "sources": [{"label": "Procedure: Motors - Worn / End of Life", "ref": f"order:{oid}#procedure"}],
         "created_at": "2026-10-27T19:05:04+00:00"},
    ]})
    dump("chat_reply.json", {"reply": {
        "id": "m4", "role": "assistant",
        "content": "Across all MP-Series motors in the data, 305 labeled returns were wear-out; the most "
                   "replaced part was the Stegmann encoder harness.",
        "sql": "SELECT part, count, freq FROM gold_part_freq WHERE product_family = 'MP' "
               "AND cause_category = 'wear_out' ORDER BY count DESC LIMIT 3",
        "sources": [{"label": "gold_part_freq", "ref": "table:gold_part_freq"}],
        "created_at": "2026-10-27T19:07:00+00:00"}})
    print(f"wrote fixtures to {OUT}")


if __name__ == "__main__":
    main()
