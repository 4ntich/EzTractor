"""Acesso de usuário único.

- Sem EZT_APP_PASSWORD: o app fica aberto (ideal para rodar só na sua máquina).
- Com EZT_APP_PASSWORD: é preciso fazer login com essa senha; a API devolve um token JWT.
"""

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings


def password_required() -> bool:
    return bool(get_settings().app_password)


def check_password(password: str) -> bool:
    return hmac.compare_digest(password.encode(), get_settings().app_password.encode())


def create_token() -> str:
    s = get_settings()
    payload = {"sub": "owner", "exp": datetime.now(timezone.utc) + timedelta(hours=s.jwt_ttl_hours)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


def is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost")


def require_auth(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if not password_required():
        return
    if get_settings().trust_localhost and is_local(request):
        return
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada, entre de novo") from None
    if payload.get("sub") != "owner":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")
