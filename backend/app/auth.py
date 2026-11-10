"""Who is calling. demo: signed cookie set by /api/auth/demo-login.
databricks: the user identity Databricks Apps forwards (X-Forwarded-Email, X-Forwarded-Preferred-Username).
Only trust these headers behind the Databricks Apps proxy; locally use AUTH_MODE=demo.
Role: app_users row if present, else specialist if listed in SPECIALIST_EMAILS, else requester."""
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
    if config.AUTH_MODE == "databricks":
        email = (request.headers.get("X-Forwarded-Email") or "").strip().lower()
        if not email:
            raise ApiError(401, "unauthenticated", "Open this app through Databricks to sign in.")
        user = get_repo().get_user(email)
        if user:
            return user
        name = request.headers.get("X-Forwarded-Preferred-Username") or email.split("@")[0]
        role = "specialist" if email in config.SPECIALIST_EMAILS else "requester"
        return {"email": email, "name": name, "role": role, "org": email.split("@")[-1]}
    email = unsign(request.cookies.get(COOKIE, ""))
    user = get_repo().get_user(email) if email else None
    if not user:
        raise ApiError(401, "unauthenticated", "Sign in to continue.")
    return user


def require_specialist(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "specialist":
        raise ApiError(403, "forbidden", "Only repair specialists can do this.")
    return user
