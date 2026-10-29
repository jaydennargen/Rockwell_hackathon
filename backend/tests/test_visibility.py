from conftest import login

SPECIALIST_ONLY = {"confidence", "parts_to_prestage", "npf_risk", "bench_evidence", "trace_id"}


def test_requester_sees_only_own_orders(client):
    login(client, "requester")
    ids = {o["order_id"] for o in client.get("/api/orders").json()["items"]}
    assert "66339318-1000" not in ids  # belongs to another requester
    assert client.get("/api/orders/66339318-1000").status_code == 404


def test_requester_never_gets_specialist_fields(client):
    login(client, "requester")
    for o in client.get("/api/orders").json()["items"]:
        assert o.get("confidence_score") is None and o.get("top_reason") is None
        r = client.get(f"/api/orders/{o['order_id']}").json()
        assert not SPECIALIST_ONLY & r.keys(), (o["order_id"], SPECIALIST_ONLY & r.keys())


def test_requester_escalated_has_notice_not_predictions(client):
    login(client, "requester")
    r = client.get("/api/orders/67083053-1000").json()
    assert r["status"] == "NEEDS_REVIEW"
    assert "escalation" in r and r["escalation"]["reasons"]
    assert "predicted" not in r and "procedure" not in r


def test_specialist_sees_full_report(client):
    login(client, "specialist")
    r = client.get("/api/orders/67083053-1000").json()
    assert "confidence" in r and "predicted" in r and "escalation" not in r


def test_review_is_specialist_only(client):
    login(client, "requester")
    r = client.post("/api/orders/67083053-1000/review", json={"decision": "approve"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
