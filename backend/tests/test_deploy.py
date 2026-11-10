"""Deployment behavior: Databricks Apps identity headers, .env loading, SDK-based auth wiring."""
import pytest

from app import config, dbx


@pytest.fixture
def dbx_auth(client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MODE", "databricks")
    monkeypatch.setattr(config, "SPECIALIST_EMAILS", {"lead@rockwell.com"})
    return client


def test_forwarded_identity_and_roles(dbx_auth):
    assert dbx_auth.get("/api/me").status_code == 401  # before touching the repo
    me = dbx_auth.get("/api/me", headers={"X-Forwarded-Email": "Tech@Plant.com",
                                          "X-Forwarded-Preferred-Username": "Pat Tech"}).json()
    assert me == {"email": "tech@plant.com", "name": "Pat Tech", "role": "requester", "org": "plant.com"}
    lead = dbx_auth.get("/api/me", headers={"X-Forwarded-Email": "lead@rockwell.com"}).json()
    assert lead["role"] == "specialist"
    # a known app_users row wins over the env list
    seeded = dbx_auth.get("/api/me", headers={"X-Forwarded-Email": "specialist@rockwell.demo"}).json()
    assert seeded["name"] == "Luis Ortega"
    assert dbx_auth.post("/api/auth/demo-login", json={"role": "specialist"}).status_code == 404


def test_device_token_off_behind_databricks_unless_set(dbx_auth, monkeypatch):
    monkeypatch.setattr(config, "DEVICE_TOKEN", "")
    r = dbx_auth.post("/api/orders/66650692-1000/evidence", headers={"X-Device-Token": ""},
                      json={"source": "bench", "measurements": [{"name": "fan_rpm", "value": 1, "unit": "rpm"}]})
    assert r.status_code == 401


def test_dotenv_loader(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("A_SET=1   # comment\nA_EMPTY=\nA_PLACEHOLDER=<YOUR_TOKEN>\n# x=y\nA_KEEP=from-file\n")
    monkeypatch.setenv("A_KEEP", "from-env")
    for k in ("A_SET", "A_EMPTY", "A_PLACEHOLDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("MATE_NO_DOTENV")
    config._load_dotenv(env)
    import os
    assert os.environ["A_SET"] == "1" and os.environ["A_KEEP"] == "from-env"
    assert "A_EMPTY" not in os.environ and "A_PLACEHOLDER" not in os.environ
    monkeypatch.delenv("A_SET")


def test_health_is_shallow_by_default(client):
    h = client.get("/api/health?deep=1").json()
    assert h["ok"] and "databricks" not in h  # all-local modes: nothing to check


def test_openai_client_uses_sdk_headers(monkeypatch):
    class FakeCfg:
        host = "https://example.cloud.databricks.com"
        def authenticate(self):
            return {"Authorization": "Bearer from-sdk"}
    monkeypatch.setattr(dbx, "cfg", lambda: FakeCfg())
    client = dbx.openai_client()
    assert str(client.base_url).startswith("https://example.cloud.databricks.com/serving-endpoints")
    import httpx
    req = httpx.Request("GET", "https://example.cloud.databricks.com/x")
    flow = client._client._auth.auth_flow(req)
    assert next(flow).headers["Authorization"] == "Bearer from-sdk"


def test_warehouse_http_path(monkeypatch):
    monkeypatch.setattr(config, "DATABRICKS_HTTP_PATH", "")
    monkeypatch.setattr(config, "DATABRICKS_WAREHOUSE_ID", "abc123")
    assert dbx.http_path() == "/sql/1.0/warehouses/abc123"
    monkeypatch.setattr(config, "DATABRICKS_WAREHOUSE_ID", "")
    with pytest.raises(dbx.DatabricksUnavailable):
        dbx.http_path()


def test_databricks_errors_become_503(dbx_auth, monkeypatch):
    from app import repo

    class Broken:
        def get_user(self, *_):
            raise dbx.DatabricksUnavailable("SQL warehouse error: warehouse is stopped")
    monkeypatch.setattr(repo, "_repo", Broken())
    r = dbx_auth.get("/api/me", headers={"X-Forwarded-Email": "tech@plant.com"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "databricks_unavailable"


def test_session_secret_derived_from_app_secret(monkeypatch):
    import importlib
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "sp-secret")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    try:
        cfg = importlib.reload(config)
        assert cfg.SESSION_SECRET not in ("", "dev-only-change-me", "sp-secret") and len(cfg.SESSION_SECRET) == 64
    finally:
        monkeypatch.delenv("DATABRICKS_CLIENT_SECRET")
        importlib.reload(config)


def test_databricks_repo_seeds_demo_users_only(monkeypatch):
    from app.repo import databricks as dbrepo
    store = {"users": {}, "orders": 0}

    def fake_rows(sql, params=None):
        if "FROM" in sql and "app_users" in sql and params and "e" in params:
            u = store["users"].get(params["e"])
            return [u] if u else []
        if sql.startswith("INSERT INTO") and "app_users" in sql:
            store["users"][params["email"]] = params
        if "app_orders" in sql and sql.startswith("INSERT"):
            store["orders"] += 1
        return []
    monkeypatch.setattr(dbrepo.dbx, "rows", fake_rows)
    monkeypatch.setattr(config, "AUTH_MODE", "demo")
    dbrepo.DatabricksRepo()
    assert {"requester@vanmeter.demo", "specialist@rockwell.demo"} <= store["users"].keys()
    assert store["orders"] == 0


def test_stats_repo_reads_every_driver_shape():
    import numpy as np
    from triage.stats_repo import _map, _obj
    pairs = [("wear_out", 0.84), ("contamination", 0.24)]
    assert _map(pairs) == {"wear_out": 0.84, "contamination": 0.24}        # connector + pyarrow
    assert _map('{"wear_out": 0.84}') == {"wear_out": 0.84}                 # JSON string
    assert _map({"wear_out": 0.84}) == {"wear_out": 0.84} and _map(None) == {}
    assert _obj(np.array(["component_failure"], dtype=object)) == ["component_failure"]
