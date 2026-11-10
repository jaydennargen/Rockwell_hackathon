import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["MATE_NO_DOTENV"] = "1"  # tests never read a developer's .env
os.environ.setdefault("MOCK_DELAY_SECONDS", "0")
os.environ.setdefault("DATA_BACKEND", "memory")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    from app.repo import reset_repo
    reset_repo()
    from app.main import app
    return TestClient(app)


def login(client, role):
    r = client.post("/api/auth/demo-login", json={"role": role})
    assert r.status_code == 200
    return client
