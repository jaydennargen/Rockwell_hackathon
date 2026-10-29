from conftest import login


def test_unauthenticated(client):
    assert client.get("/api/me").status_code == 401


def test_submit_triage_review_flow(client):
    login(client, "requester")
    body = {"order_number": "99990001", "catalog": "R1394CAM75IH/C",
            "part_description": "MOD AXIS INTL HTSNK 15KW 35.0A CONT",
            "failure_details": "FAN NOISY, OVERTEMP FAULT AFTER 20 MIN"}
    r = client.post("/api/orders", json=body)
    assert r.status_code == 201 and r.json()["order_id"] == "99990001-1000"
    # TestClient runs background tasks before returning
    rep = client.get("/api/orders/99990001-1000").json()
    assert rep["status"] == "AUTO_RELEASED" and rep["status_label"] == "Report ready"
    assert client.post("/api/orders", json=body).status_code == 409

    login(client, "specialist")
    rep = client.post("/api/orders/99990001-1000/review",
                      json={"decision": "edit", "corrections": {"causes": ["component_failure"]},
                            "notes": "Fan seized, not worn."}).json()
    assert rep["status"] == "EDITED" and rep["predicted"]["causes"] == ["component_failure"]

    login(client, "requester")
    rep = client.get("/api/orders/99990001-1000").json()
    assert rep["status_label"] == "Verified by specialist" and rep["review"]["notes"]


def test_uninformative_text_escalates(client):
    login(client, "requester")
    client.post("/api/orders", json={"order_number": "99990002", "catalog": "R1394CAM75IH/C",
                                     "failure_details": "NO INFORMATION GIVEN Serial Number: X1"})
    rep = client.get("/api/orders/99990002-1000").json()
    assert rep["status"] == "NEEDS_REVIEW" and "escalation" in rep


def test_chat(client):
    login(client, "requester")
    r = client.post("/api/orders/66650692-1000/chat", json={"message": "What do I check first?"})
    assert r.status_code == 200 and r.json()["reply"]["role"] == "assistant"
    assert "sql" not in r.json()["reply"]
    msgs = client.get("/api/orders/66650692-1000/chat").json()["messages"]
    assert msgs[-1]["role"] == "assistant"


def test_evidence_requires_device_token(client):
    r = client.post("/api/orders/66650692-1000/evidence",
                    json={"source": "bench-01", "measurements": [{"name": "fan_rpm", "value": 3100, "unit": "rpm"}]})
    assert r.status_code == 401
    r = client.post("/api/orders/66650692-1000/evidence", headers={"X-Device-Token": "dev-device-token"},
                    json={"source": "bench-01", "measurements": [
                        {"name": "fan_rpm", "value": 3100, "unit": "rpm", "spec_min": 4200}]})
    assert r.status_code == 200 and r.json()["bench_evidence"][0]["pass"] is False
