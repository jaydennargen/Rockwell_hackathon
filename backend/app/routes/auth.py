from fastapi import APIRouter, Depends, Response

from app import config
from app.auth import COOKIE, current_user, sign
from app.errors import ApiError
from app.repo import get_repo
from app.schemas import DemoLoginIn, User

router = APIRouter(prefix="/api")


@router.post("/auth/demo-login", response_model=User)
def demo_login(body: DemoLoginIn, response: Response):
    if config.AUTH_MODE != "demo":
        raise ApiError(404, "not_found", "Demo login is disabled.")
    user = get_repo().user_for_role(body.role)
    response.set_cookie(COOKIE, sign(user["email"]), httponly=True, samesite="lax")
    return user


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {}


@router.get("/me", response_model=User)
def me(user: dict = Depends(current_user)):
    return user
