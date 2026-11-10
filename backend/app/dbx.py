"""Databricks access through the SDK's unified authentication. No credentials are read here directly.

Credential resolution (databricks.sdk Config), in order of what is set:
  - Databricks Apps: DATABRICKS_HOST + DATABRICKS_CLIENT_ID/SECRET are injected for the app's service
    principal -> OAuth machine-to-machine. Nothing to configure.
  - Local dev: DATABRICKS_CONFIG_PROFILE=<profile> from `databricks auth login` (OAuth, user-to-machine),
    or DATABRICKS_HOST + DATABRICKS_TOKEN as a fallback.
The same code runs in both places; tokens stay on the server.
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache

from app import config

log = logging.getLogger(__name__)


class DatabricksUnavailable(RuntimeError):
    """Databricks couldn't be reached or refused the request (auth, permissions, warehouse stopped)."""


@lru_cache(maxsize=1)
def cfg():
    from databricks.sdk.core import Config
    try:
        return Config(host=config.DATABRICKS_HOST or None, profile=config.DATABRICKS_CONFIG_PROFILE or None)
    except Exception as e:  # noqa: BLE001
        msg = str(e).split(". Config:")[0][:300]  # SDK message names variables, never values
        raise DatabricksUnavailable(f"Databricks authentication isn't configured: {msg}") from e


def workspace():
    from databricks.sdk import WorkspaceClient
    return WorkspaceClient(config=cfg())


def http_path() -> str:
    if config.DATABRICKS_HTTP_PATH:
        return config.DATABRICKS_HTTP_PATH
    if config.DATABRICKS_WAREHOUSE_ID:
        return f"/sql/1.0/warehouses/{config.DATABRICKS_WAREHOUSE_ID}"
    raise DatabricksUnavailable("No SQL warehouse configured: set DATABRICKS_WAREHOUSE_ID "
                                "(the app's sql-warehouse resource) or DATABRICKS_HTTP_PATH.")


# ---------- SQL warehouse ----------
_lock = threading.Lock()
_conn = None


def _connect():
    from databricks import sql
    c = cfg()
    host = c.host.replace("https://", "").replace("http://", "").rstrip("/")
    return sql.connect(server_hostname=host, http_path=http_path(), credentials_provider=lambda: c.authenticate)


def query(statement: str, params: dict | None = None) -> tuple[list[str], list[tuple]]:
    """Run one statement on the warehouse; one shared connection, reconnect once on failure."""
    global _conn
    with _lock:
        for attempt in (1, 2):
            try:
                if _conn is None:
                    _conn = _connect()
                with _conn.cursor() as cur:
                    cur.execute(statement, params or None)
                    if not cur.description:
                        return [], []
                    return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]
            except DatabricksUnavailable:
                raise
            except Exception as e:  # noqa: BLE001
                try:
                    _conn and _conn.close()
                except Exception:  # noqa: BLE001
                    pass
                _conn = None
                if attempt == 2 or not _retryable(e):
                    raise DatabricksUnavailable(f"SQL warehouse error: {str(e).splitlines()[0][:300]}") from e
                log.warning("warehouse query failed, reconnecting: %s", e)


def _retryable(e: Exception) -> bool:
    """SQL errors (bad table, no permission) won't fix themselves; connection errors might."""
    name = type(e).__name__
    return name not in ("ServerOperationError", "ProgrammingError")


def rows(statement: str, params: dict | None = None) -> list[dict]:
    cols, data = query(statement, params)
    return [dict(zip(cols, r)) for r in data]


# ---------- Model serving (OpenAI-compatible) ----------
def openai_client():
    """OpenAI client for {host}/serving-endpoints. Each request gets fresh SDK auth headers, so the
    service principal's OAuth token refreshes on its own."""
    import httpx
    from openai import OpenAI

    class _Auth(httpx.Auth):
        def auth_flow(self, request):
            request.headers.update(cfg().authenticate())
            yield request

    return OpenAI(base_url=f"{cfg().host.rstrip('/')}/serving-endpoints", api_key="databricks-sdk",
                  http_client=httpx.Client(auth=_Auth(), timeout=60))


def check() -> dict:
    """Deep health check: auth + warehouse. Never returns credentials."""
    out = {"host": None, "auth_type": None, "warehouse": False}
    try:
        c = cfg()
        out["host"], out["auth_type"] = c.host, c.auth_type
        query("SELECT 1")
        out["warehouse"] = True
    except DatabricksUnavailable as e:
        out["error"] = str(e)
    return out
