"""Acesso de usuário único.

- Sem EZT_APP_PASSWORD: o app fica aberto (ideal para rodar só na sua máquina).
- Com EZT_APP_PASSWORD: é preciso fazer login com essa senha; a API devolve um token JWT.
"""

import hmac
import threading
import time
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
    # "g" = geração das sessões: "Encerrar conexões" ou trocar a senha aumenta o número e derruba os logins antigos
    payload = {"sub": "owner", "g": s.session_gen, "exp": datetime.now(timezone.utc) + timedelta(hours=s.jwt_ttl_hours)}
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
    if payload.get("g", 0) != get_settings().session_gen:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Conexão encerrada no computador. Entre de novo.")
    if not is_local(request):
        _mark_seen(request)


# ---------------------------------------------------------------- aparelhos conectados (celular)
ACTIVE_WINDOW_S = 120  # visto nos últimos 2 min = conectado agora
_seen: dict[str, dict] = {}
_seen_lock = threading.Lock()


def _device_name(agent: str) -> str:
    a = agent.lower()
    for key, name in (("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"), ("windows", "Windows"),
                      ("macintosh", "Mac"), ("linux", "Linux")):
        if key in a:
            return name
    return "Navegador"


def _mark_seen(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    with _seen_lock:
        _seen[ip] = {"ip": ip, "device": _device_name(request.headers.get("user-agent", "")), "at": time.time()}


def active_devices() -> list[dict]:
    now = time.time()
    with _seen_lock:
        for ip in [ip for ip, d in _seen.items() if now - d["at"] > ACTIVE_WINDOW_S]:
            del _seen[ip]
        return [{"ip": d["ip"], "device": d["device"], "seconds_ago": int(now - d["at"])}
                for d in sorted(_seen.values(), key=lambda d: -d["at"])]


def forget_devices() -> None:
    with _seen_lock:
        _seen.clear()
