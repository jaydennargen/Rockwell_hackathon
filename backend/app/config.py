"""Runtime switches. See ARCHITECTURE.md §1."""
import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IN_DATABRICKS_APP = bool(os.environ.get("DATABRICKS_APP_NAME"))  # set by the Databricks Apps runtime


def _load_dotenv(path: Path) -> None:
    """Local dev only: KEY=VALUE lines from the repo-root .env. Real environment variables win; empty
    values and <PLACEHOLDERS> are skipped. Never used inside Databricks Apps (.env isn't deployed)."""
    if IN_DATABRICKS_APP or os.environ.get("MATE_NO_DOTENV") or not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.split(" #", 1)[0].strip().strip('"').strip("'")
        if val and not val.startswith("<"):
            os.environ.setdefault(key.strip(), val)


_load_dotenv(ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default  # empty counts as unset


PRODUCT_NAME = _env("PRODUCT_NAME", "MATE")      # working name; shown in reports
AUTH_MODE = _env("AUTH_MODE", "demo")            # demo | databricks
DATA_BACKEND = _env("DATA_BACKEND", "local")     # memory (fixtures) | local (SQLite) | databricks
PIPELINE = _env("PIPELINE", "mock")              # mock | live
LLM_MODE = _env("LLM_MODE", "fake")              # fake | databricks
CHAT_MODE = _env("CHAT_MODE", "fake")            # fake | agent | genie
CONFIDENCE_THRESHOLD = float(_env("CONFIDENCE_THRESHOLD", "0.70"))
MOCK_DELAY_SECONDS = float(_env("MOCK_DELAY_SECONDS", "2.5"))
# Dev defaults only in demo auth; behind Databricks the device endpoint is off unless DEVICE_TOKEN is set.
# In Databricks Apps the cookie key is derived from the app's injected OAuth secret: unique per app,
# never stored anywhere, no setup.
SESSION_SECRET = _env("SESSION_SECRET", "") or (
    hashlib.sha256(b"mate-session:" + os.environ["DATABRICKS_CLIENT_SECRET"].encode()).hexdigest()
    if os.environ.get("DATABRICKS_CLIENT_SECRET") else "dev-only-change-me")
DEVICE_TOKEN = _env("DEVICE_TOKEN", "dev-device-token" if AUTH_MODE == "demo" else "")
SPECIALIST_EMAILS = {e.strip().lower() for e in _env("SPECIALIST_EMAILS", "").split(",") if e.strip()}
FIXTURES = ROOT / "contracts" / "fixtures"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DATA_DIR = Path(_env("DATA_DIR", str(ROOT / "backend" / ".data")))
APP_DB = DATA_DIR / "app.db"
GOLD_DB = DATA_DIR / "gold.db"

# databricks modes only. Credentials are resolved by the Databricks SDK (app/dbx.py), never read here.
DATABRICKS_HOST = _env("DATABRICKS_HOST", "")
DATABRICKS_CONFIG_PROFILE = _env("DATABRICKS_CONFIG_PROFILE", "")
DATABRICKS_WAREHOUSE_ID = _env("DATABRICKS_WAREHOUSE_ID", "")  # from the app's sql-warehouse resource
DATABRICKS_HTTP_PATH = _env("DATABRICKS_HTTP_PATH", "")        # alternative to the warehouse id
UC_CATALOG = _env("UC_CATALOG", "hackathon")
UC_SCHEMA = _env("UC_SCHEMA", "triage")            # gold stats + silver (read by the pipeline)
APP_SCHEMA = _env("APP_SCHEMA", UC_SCHEMA)          # MATE's own app tables (orders, reports, chat...)
LLM_ENDPOINT = _env("LLM_ENDPOINT", "")
GENIE_SPACE_ID = _env("GENIE_SPACE_ID", "")
