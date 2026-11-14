import hmac
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .config import settings

COOKIE = "tl_session"
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Very small brute-force guard (single-user app): 10 failed logins / 15 minutes.
_failures: deque = deque()
_WINDOW = 15 * 60
_MAX_FAILS = 10


def _too_many_failures() -> bool:
    now = time.time()
    while _failures and now - _failures[0] > _WINDOW:
        _failures.popleft()
    return len(_failures) >= _MAX_FAILS


def _make_token() -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    return jwt.encode(
        {"sub": settings.app_username, "exp": exp}, settings.secret_key, algorithm="HS256"
    )


def require_user(request: Request) -> str:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="غير مسجّل الدخول")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="انتهت الجلسة")
    return str(payload.get("sub", ""))


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, response: Response):
    if not settings.app_password:
        raise HTTPException(status_code=503, detail="لم يتم ضبط APP_PASSWORD على الخادم")
    if _too_many_failures():
        raise HTTPException(status_code=429, detail="محاولات كثيرة، حاول بعد قليل")

    ok_user = hmac.compare_digest(body.username.encode(), settings.app_username.encode())
    ok_pass = hmac.compare_digest(body.password.encode(), settings.app_password.encode())
    if not (ok_user and ok_pass):
        _failures.append(time.time())
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")

    response.set_cookie(
        COOKIE,
        _make_token(),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    return {"username": require_user(request)}
