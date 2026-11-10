"""Repair report in the reference SAP layout: sections, provenance tags, PDF route, visibility."""
from app.report_pdf import report_sections
from conftest import login

ORDER = ["Distributor Input", "As Received", "Cleaning", "Updates", "Affected Areas", "Parts Replaced",
         "Testing", "Probable Cause Code"]
POST_REPAIR = {"As Received", "Cleaning", "Updates", "Parts Replaced", "Testing"}


def _sections(client, oid):
    return {s["title"]: s for s in report_sections(client.get(f"/api/orders/{oid}").json())}


def test_sections_follow_reference_order_and_never_claim_repair_work(client):
    login(client, "specialist")
    rep = client.get("/api/orders/67083053-1000").json()
    secs = report_sections(rep)
    assert [s["title"] for s in secs][:8] == ORDER
    for s in secs:
        if s["title"] in POST_REPAIR:
            assert s["tag"] == "PENDING" and not any("PASSED" in ln or "cleaned" in ln for ln in s["lines"])
    by = {s["title"]: s for s in secs}
    assert by["Affected Areas"]["tag"] == "PREDICTION"
    assert "* Worn / End of Life" in by["Probable Cause Code"]["lines"]
    assert by["Distributor Input"]["lines"][:3] == ["Comments:", "'No reason given - FQA", "Serial Number: 1JAP5JK8"]


def test_requester_escalated_report_has_no_predictions(client):
    login(client, "requester")
    by = _sections(client, "67083053-1000")
    assert by["Affected Areas"]["tag"] == "PENDING" and by["Probable Cause Code"]["tag"] == "PENDING"
    assert not any(ln.startswith("* ") for ln in by["Probable Cause Code"]["lines"])


def test_reviewed_report_is_marked_verified(client):
    login(client, "requester")
    by = _sections(client, "66433026-1000")
    assert by["Probable Cause Code"]["tag"] == "VERIFIED" and by["Specialist Notes"]["lines"][1].startswith("Confirmed")


def test_report_fields_from_order(client):
    login(client, "requester")
    body = {"order_number": "99990010", "catalog": "R1394CAM75IH/C", "failure_details": "FAN NOISY",
            "purchase_order": "P002226696"}
    client.post("/api/orders", json=body)
    rep = client.get("/api/orders/99990010-1000").json()
    assert rep["header"]["purchase_order"] == "P002226696" and rep["header"]["sold_to"] == "Van Meter Inc"
    assert rep["customer_input"]["raw"] == "FAN NOISY"


def test_pdf_download_and_visibility(client):
    login(client, "requester")
    r = client.get("/api/orders/67083053-1000/report.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]
    assert client.get("/api/orders/66339318-1000/report.pdf").status_code == 404  # another requester's
