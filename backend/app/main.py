from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.routes import auth, chat, orders

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


@app.get("/api/health")
def health():
    return {"ok": True, "auth": config.AUTH_MODE, "data": config.DATA_BACKEND, "pipeline": config.PIPELINE}


# Production: serve the built React app; unknown non-API paths fall back to index.html.
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": {"code": "not_found", "message": "Not found."}}, status_code=404)
        f = config.FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else config.FRONTEND_DIST / "index.html")
