"""Rotas de sistema: versão/atualização, acesso pelo celular, chave do YouTube e busca de virais.

Ficam fora de main.py para cada arquivo continuar pequeno (a proteção do código no instalador tem limite
de tamanho por arquivo na versão gratuita).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel

from .. import system, updater
from ..auth import is_local, require_auth
from ..config import get_settings

sys_api = APIRouter(dependencies=[Depends(require_auth)])


# ---------- sistema: versão, atualização, acesso pelo celular
def _local_only(request: Request) -> None:
    if not is_local(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "só pode ser alterado no computador onde o EzTractor está instalado")


@sys_api.get("/system/info")
def system_info(request: Request):
    s = get_settings()
    return {"version": s.app_version, "can_update": updater.can_install(), "can_restart": system.can_restart(),
            "is_local": is_local(request), "lan": system.lan_info()}


@sys_api.get("/system/update")
def check_update(force: bool = False):
    return {**updater.state(), **updater.latest(force=force)}


@sys_api.post("/system/update/install")
def install_update(request: Request):
    _local_only(request)
    try:
        return updater.install()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None


@sys_api.get("/system/update/progress")
def update_progress():
    return updater.state()


class LanIn(BaseModel):
    enabled: bool
    password: str | None = None


@sys_api.post("/system/lan")
def set_lan(body: LanIn, request: Request):
    _local_only(request)
    s = get_settings()
    values = {"EZT_LAN_ACCESS": "1" if body.enabled else "0"}
    new_password = False
    if body.password:
        if len(body.password) < 6:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a senha precisa ter pelo menos 6 caracteres")
        values["EZT_APP_PASSWORD"] = body.password
        new_password = body.password != s.app_password
    elif body.enabled and not s.app_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "defina uma senha para o acesso pelo celular")
    try:
        system.apply_config(values)
        if new_password or not body.enabled:  # quem entrou com a senha antiga (ou com o acesso ligado) sai
            system.end_sessions()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return {"saved": True, "restart_required": system.lan_info()["restart_required"]}


@sys_api.delete("/system/lan/password")
def delete_lan_password(request: Request):
    """Apaga a senha. Sem senha o celular não pode entrar, então o acesso pela rede também é desligado."""
    _local_only(request)
    try:
        system.apply_config({"EZT_APP_PASSWORD": "", "EZT_LAN_ACCESS": "0"})
        system.end_sessions()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return system.lan_info()


@sys_api.post("/system/lan/disconnect")
def disconnect_devices(request: Request):
    """Encerra a conexão de todos os aparelhos (eles precisam entrar de novo com a senha)."""
    _local_only(request)
    try:
        system.end_sessions()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return system.lan_info()


# ---------- descobrir virais no YouTube
@sys_api.get("/viral/search")
def viral_search(q: str, period: str = "week", kind: str = "shorts", sort: str = "trending",
                 region: str | None = "BR", limit: int = 25):
    from .. import viral

    try:
        return viral.search(q, period=period, kind=kind, sort=sort, region=region or None, limit=limit)
    except viral.ViralError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None


@sys_api.get("/system/youtube")
def youtube_key_status():
    s = get_settings()
    return {"configured": bool(s.youtube_api_key.strip()), "configurable": bool(s.config_file)}


class YoutubeKeyIn(BaseModel):
    key: str


@sys_api.post("/system/youtube")
def set_youtube_key(body: YoutubeKeyIn, request: Request):
    """Testa a chave (1 unidade da cota) e guarda no config.env do app."""
    from .. import viral

    _local_only(request)
    key = body.key.strip()
    if not key or len(key) < 20 or " " in key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "isso não parece uma chave de API do Google")
    try:
        viral.check_key(key)
    except viral.ViralError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    try:
        system.apply_config({"EZT_YOUTUBE_API_KEY": key})
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    viral._cache.clear()
    return {"configured": True}


@sys_api.delete("/system/youtube")
def delete_youtube_key(request: Request):
    from .. import viral

    _local_only(request)
    try:
        system.apply_config({"EZT_YOUTUBE_API_KEY": ""})
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    viral._cache.clear()
    return {"configured": False}


@sys_api.post("/system/restart")
def restart_app(request: Request):
    _local_only(request)
    try:
        system.restart()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return {"restarting": True}


@sys_api.get("/system/qr.svg")
def qr(data: str):
    if len(data) > 300:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "texto longo demais")
    return Response(system.qr_svg(data), media_type="image/svg+xml")
