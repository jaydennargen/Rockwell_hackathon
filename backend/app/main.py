from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import logging

from app import config
from app.dbx import DatabricksUnavailable
from app.routes import auth, chat, orders

log = logging.getLogger(__name__)

app = FastAPI(title="Failure Analysis Triage API")
app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(chat.router)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    d = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
    return JSONResponse({"error": d}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:])
    msg = f"{field}: {first.get('msg', 'invalid')}" if field else "Invalid request."
    return JSONResponse({"error": {"code": "invalid", "message": msg}}, status_code=422)


@app.exception_handler(DatabricksUnavailable)
async def databricks_error(_: Request, exc: DatabricksUnavailable):
    log.error("databricks unavailable: %s", exc)
    return JSONResponse({"error": {"code": "databricks_unavailable", "message": str(exc)}}, status_code=503)


@app.exception_handler(Exception)
async def server_error(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"error": {"code": "server_error", "message": "Something went wrong on the server."}},
                        status_code=500)


@app.get("/api/health")
def health(deep: bool = False):
    """Liveness + which modes are on. ?deep=1 also checks Databricks auth and the SQL warehouse."""
    out = {"ok": True, "auth": config.AUTH_MODE, "data": config.DATA_BACKEND, "pipeline": config.PIPELINE,
           "llm": config.LLM_MODE, "chat": config.CHAT_MODE, "in_databricks_app": config.IN_DATABRICKS_APP}
    if deep and "databricks" in (config.DATA_BACKEND, config.LLM_MODE, config.AUTH_MODE):
        from app import dbx
        out["databricks"] = dbx.check()
        out["ok"] = out["databricks"].get("warehouse", False) or config.DATA_BACKEND != "databricks"
    return out


# Production: serve the built React app; unknown non-API paths fall back to index.html.
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": {"code": "not_found", "message": "Not found."}}, status_code=404)
        f = config.FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else config.FRONTEND_DIST / "index.html")
