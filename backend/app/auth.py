from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Cookie, HTTPException, Response, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings

settings = get_settings()

COOKIE_NAME = "trind_session"
security = HTTPBearer(auto_error=False)


def verify_credentials(username: str, password: str) -> bool:
    return username.strip() == settings.app_username and password == settings.app_password


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
