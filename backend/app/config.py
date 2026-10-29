"""Runtime switches. See ARCHITECTURE.md §1."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


AUTH_MODE = _env("AUTH_MODE", "demo")            # demo | databricks
DATA_BACKEND = _env("DATA_BACKEND", "memory")    # memory (WS0) | local (WS3, SQLite) | databricks
PIPELINE = _env("PIPELINE", "mock")              # mock | live
LLM_MODE = _env("LLM_MODE", "fake")              # fake | databricks
CHAT_MODE = _env("CHAT_MODE", "fake")            # fake | agent | genie
CONFIDENCE_THRESHOLD = float(_env("CONFIDENCE_THRESHOLD", "0.70"))
MOCK_DELAY_SECONDS = float(_env("MOCK_DELAY_SECONDS", "2.5"))
SESSION_SECRET = _env("SESSION_SECRET", "dev-only-change-me")
DEVICE_TOKEN = _env("DEVICE_TOKEN", "dev-device-token")
FIXTURES = ROOT / "contracts" / "fixtures"
FRONTEND_DIST = ROOT / "frontend" / "dist"
