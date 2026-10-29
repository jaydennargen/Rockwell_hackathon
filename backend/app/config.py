"""Runtime switches. See ARCHITECTURE.md §1."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


AUTH_MODE = _env("AUTH_MODE", "demo")            # demo | databricks
DATA_BACKEND = _env("DATA_BACKEND", "local")     # memory (fixtures) | local (SQLite) | databricks
PIPELINE = _env("PIPELINE", "mock")              # mock | live
LLM_MODE = _env("LLM_MODE", "fake")              # fake | databricks
CHAT_MODE = _env("CHAT_MODE", "fake")            # fake | agent | genie
CONFIDENCE_THRESHOLD = float(_env("CONFIDENCE_THRESHOLD", "0.70"))
MOCK_DELAY_SECONDS = float(_env("MOCK_DELAY_SECONDS", "2.5"))
SESSION_SECRET = _env("SESSION_SECRET", "dev-only-change-me")
DEVICE_TOKEN = _env("DEVICE_TOKEN", "dev-device-token")
FIXTURES = ROOT / "contracts" / "fixtures"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DATA_DIR = Path(_env("DATA_DIR", str(ROOT / "backend" / ".data")))
APP_DB = DATA_DIR / "app.db"
GOLD_DB = DATA_DIR / "gold.db"

# databricks modes only
DATABRICKS_HOST = _env("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = _env("DATABRICKS_TOKEN", "")
DATABRICKS_HTTP_PATH = _env("DATABRICKS_HTTP_PATH", "")
UC_CATALOG = _env("UC_CATALOG", "hackathon")
UC_SCHEMA = _env("UC_SCHEMA", "triage")
LLM_ENDPOINT = _env("LLM_ENDPOINT", "")
GENIE_SPACE_ID = _env("GENIE_SPACE_ID", "")
