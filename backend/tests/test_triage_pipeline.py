"""Live pipeline on synthetic SAP-shaped rows (not real data): mapping, routing, schema, per-category confidence."""
from datetime import date, timedelta

import pandas as pd
import pytest

from app.schemas import TriageReport
from triage import confidence
from triage.gold import build_gold, map_area, map_cause, memory_stats, to_silver
from triage.llm import FakeLLM
from triage.pipeline import triage
from triage.tools import product_family


def _raw(n=40, catalog="R1394CAM75IH/C", cause="Worn / End of Life", area="Component - Fan Assembly"):
    d0 = date(2025, 1, 1)
    return pd.DataFrame([{
        "Order Number": 60000000 + i, "Line Number": 1000, "Catalog": catalog,
        "Part Description": "MOD AXIS INTL HTSNK 15KW 35.0A CONT", "Serial Number": f"SN{i:05d}",
        "Depot": "P1100", "SAP Status": "Order Complete", "Received Date": d0 + timedelta(days=i),
        "Failure Details": "FAN NOISY", "Probable Cause Code": cause, "Affected Areas": area,
        "Parts Replaced": "306445-FAN,AXL,60X25MM / Reference Designator : B1^~21509-CAP,450V",
    } for i in range(n)])


def _stats(raw):
    silver = to_silver(raw)
    return memory_stats(silver, build_gold(silver))


ORDER = {"order_number": "99990001", "line_number": 1000, "catalog": "R1394CAM75IH/C",
         "part_description": "MOD AXIS INTL HTSNK 15KW 35.0A CONT", "serial_number": "NEW001",
         "failure_details": "FAN NOISY, OVERTEMP FAULT AFTER 20 MIN Serial Number: NEW001",
         "received_date": "2026-10-01"}


@pytest.mark.parametrize("raw,cat", [
    ("Worn / End of Life", "wear_out"), ("Tampering / Improper Repair or Modificat", "physical_damage"),
    ("Improper Voltage or Current", "external_electrical"), ("No Problem Found", "no_problem_found"),
    ("Software / Firmware Error", "configuration_error"), ("Update - Firmware", "update_notice"),
    ("Corrosion / Environmental", "contamination"), ("Component Failure", "component_failure"),
])
def test_cause_mapping(raw, cat):
    assert map_cause(raw) == cat


@pytest.mark.parametrize("raw,cat", [
    ("Component - Fan Assembly", "fan_cooling"), ("Motors - Connector", "motor_mechanical"),
    ("PCBA - Display Board", "hmi_display"), ("PCBA - Main Control", "pcba_circuitry"),
    ("Component - Bus Capacitor", "pcba_circuitry"), ("Component - Cable", "enclosure_wiring"),
    ("Something New", "other"),
])
def test_area_mapping(raw, cat):
    assert map_area(raw) == cat


def test_product_family():
    assert product_family("R2094BM01S/D") == "2094"
    assert product_family("R1734IB8S/B") == "1734"
    assert product_family("AB-CNSB-PROXY") == "AB"


def test_silver_parts_split():
    silver = to_silver(_raw(2))
    assert silver["parts"][0] == ["306445-FAN,AXL,60X25MM", "21509-CAP,450V"]
    assert silver["cause_category"][0] == ["wear_out"] and silver["is_labeled"].all()


def test_confident_order_auto_releases_with_per_category_confidence():
    rep = triage(ORDER, stats=_stats(_raw()), llm=FakeLLM())
    TriageReport.model_validate(rep)
    assert rep["status"] == "AUTO_RELEASED", rep["confidence"]
    cats = {(c["kind"], c["category"]): c for c in rep["confidence"]["categories"]}
    assert ("cause", "wear_out") in cats and ("area", "fan_cooling") in cats
    wear = cats[("cause", "wear_out")]
    assert any('"noisy"' in r for r in wear["reasons"])
    assert any("100% of 40 past 1394 repairs" in r for r in wear["reasons"])
    assert rep["parts_to_prestage"][0]["n"] == 40
    assert rep["procedure"]["synthetic"] is True and rep["pending_sections"] == ["cleaning", "testing"]


def test_uninformative_text_with_thin_history_escalates():
    rep = triage({**ORDER, "failure_details": "NO INFORMATION GIVEN"}, stats=_stats(_raw(10)), llm=FakeLLM())
    TriageReport.model_validate(rep)
    assert rep["status"] == "NEEDS_REVIEW"
    assert confidence.REASON_NO_TEXT in rep["confidence"]["reasons"]
    assert confidence.REASON_THIN_HISTORY in rep["confidence"]["reasons"]
    for c in rep["confidence"]["categories"]:
        assert any("repair history only" in r for r in c["reasons"])


def test_repeat_return_escalates():
    raw = _raw()
    raw.loc[0, "Serial Number"] = "NEW001"
    raw.loc[0, "Received Date"] = date(2026, 8, 1)
    rep = triage(ORDER, stats=_stats(raw), llm=FakeLLM())
    assert rep["status"] == "NEEDS_REVIEW"
    assert any("61 days ago" in r for r in rep["confidence"]["reasons"])
    assert rep["unit_history"][0]["order_id"] == "60000000-1000"


def test_no_history_no_sop_escalates():
    order = {**ORDER, "catalog": "R9999X", "part_description": "Widget", "failure_details": "SCREEN CRACKED"}
    rep = triage(order, stats=_stats(_raw()), llm=FakeLLM())
    TriageReport.model_validate(rep)
    assert rep["status"] == "NEEDS_REVIEW"
    assert confidence.REASON_NO_SOP in rep["confidence"]["reasons"]
    assert rep["procedure"]["section"] is None


def test_bench_evidence_rescore_only_before_review():
    rep = triage(ORDER, stats=_stats(_raw()), llm=FakeLLM())
    before = rep["confidence"]["score"]
    rep["bench_evidence"] = [{"name": "fan_rpm", "value": 3100, "unit": "rpm", "spec_min": 4200, "pass": False}]
    up = confidence.rescore_with_evidence(rep)
    assert up["confidence"]["score"] > before
    assert "Bench measurements support it." in up["confidence"]["categories"][0]["reasons"]
    reviewed = {**rep, "status": "APPROVED", "review": {"decision": "approve"}}
    reviewed["bench_evidence"] = [{"name": "fan_rpm", "value": 5000, "unit": "rpm", "spec_min": 4200, "pass": True}]
    assert confidence.rescore_with_evidence(reviewed)["status"] == "APPROVED"
