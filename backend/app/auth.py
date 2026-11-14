import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import jwt
from fastapi import Cookie, HTTPException, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings

settings = get_settings()

COOKIE_NAME = "trind_session"
security = HTTPBearer(auto_error=False)


def verify_credentials(username: str, password: str) -> bool:
    ok_user = hmac.compare_digest(username.strip().encode(), settings.app_username.encode())
    ok_pass = hmac.compare_digest(password.encode(), settings.app_password.encode())
    return ok_user and ok_pass


# حد بسيط لمحاولات الدخول الفاشلة (في الذاكرة): 5 محاولات كل 5 دقائق لكل عنوان
_FAILS: Dict[str, List[float]] = {}
_WINDOW, _MAX_FAILS = 300.0, 5


def login_blocked(key: str) -> bool:
    now = time.time()
    recent = [t for t in _FAILS.get(key, []) if now - t < _WINDOW]
    _FAILS[key] = recent
    return len(recent) >= _MAX_FAILS


def register_login_failure(key: str) -> None:
    _FAILS.setdefault(key, []).append(time.time())


def clear_login_failures(key: str) -> None:
    _FAILS.pop(key, None)


def create_session_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def decode_session_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


async def get_current_user(
    trind_session: Optional[str] = Cookie(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> str:
    token = None
    if trind_session:
        token = trind_session
    elif credentials and credentials.credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(status_code=401, detail="غير مسجل الدخول")

    username = decode_session_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="جلسة العمل منتهية أو غير صالحة")
    return username
