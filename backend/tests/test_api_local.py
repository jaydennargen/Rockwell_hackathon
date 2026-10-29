"""The API on the SQLite repo (DATA_BACKEND=local)."""
import pytest
from fastapi.testclient import TestClient

from conftest import login


@pytest.fixture
def local_client(tmp_path, monkeypatch):
    from app import config, repo
    from app.repo.local import LocalRepo
    monkeypatch.setattr(config, "DATA_BACKEND", "local")
    repo.reset_repo()
    repo._repo = LocalRepo(tmp_path / "app.db")
    from app.main import app
    yield TestClient(app)
    repo.reset_repo()


def test_local_repo_seeds_and_isolates(local_client):
    login(local_client, "requester")
    ids = {o["order_id"] for o in local_client.get("/api/orders").json()["items"]}
    assert "67083053-1000" in ids and "66339318-1000" not in ids
    assert local_client.get("/api/orders/66339318-1000").status_code == 404


def test_local_repo_full_flow(local_client):
    login(local_client, "requester")
    body = {"order_number": "99990003", "catalog": "R1394CAM75IH/C",
            "part_description": "MOD AXIS INTL HTSNK 15KW 35.0A CONT", "failure_details": "FAN NOISY, OVERTEMP"}
    assert local_client.post("/api/orders", json=body).status_code == 201
    assert local_client.post("/api/orders", json=body).status_code == 409
    assert local_client.post("/api/orders/99990003-1000/chat", json={"message": "first check?"}).status_code == 200
    assert len(local_client.get("/api/orders/99990003-1000/chat").json()["messages"]) == 2

    login(local_client, "specialist")
    rep = local_client.get("/api/orders/99990003-1000").json()
    assert rep["confidence"]["categories"] and "signals" not in rep["confidence"]
    rep = local_client.post("/api/orders/99990003-1000/review", json={"decision": "approve"}).json()
    assert rep["status"] == "APPROVED"
    listed = local_client.get("/api/orders?filter=released").json()["items"]
    assert any(o["order_id"] == "99990003-1000" for o in listed)
