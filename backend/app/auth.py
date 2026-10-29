"""Who is calling. demo: signed cookie set by /api/auth/demo-login.
databricks: identity header forwarded by Databricks Apps (verify the header name in the Apps docs)."""
import hashlib
import hmac

from fastapi import Depends, Request

from app import config
from app.errors import ApiError
from app.repo import get_repo

COOKIE = "session"


def sign(email: str) -> str:
    mac = hmac.new(config.SESSION_SECRET.encode(), email.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{email}|{mac}"


def unsign(value: str):
    email, _, mac = value.rpartition("|")
    return email if email and hmac.compare_digest(sign(email), value) else None


def current_user(request: Request) -> dict:
    repo = get_repo()
    if config.AUTH_MODE == "databricks":
        email = request.headers.get("X-Forwarded-Email")
        if not email:
            raise ApiError(401, "unauthenticated", "Sign in through Databricks to use this app.")
        return repo.get_user(email) or {"email": email, "name": email.split("@")[0],
                                         "role": "requester", "org": ""}
    email = unsign(request.cookies.get(COOKIE, ""))
    user = repo.get_user(email) if email else None
    if not user:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    return user


def require_specialist(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "specialist":
        raise ApiError(403, "forbidden", "Only repair specialists can do this.")
    return user
