"""Verifica e instala atualizações (app Windows). A fonte é a API de Releases (EZT_UPDATE_URL)."""

import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .config import get_settings

log = logging.getLogger(__name__)

_cache: dict = {"at": 0.0, "data": None}
_state: dict = {"status": "idle", "progress": 0, "error": None}  # idle|downloading|installing|error
_lock = threading.Lock()
CACHE_S = 3600


def parse_version(v: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", v.split("-")[0])[:3]]
    return tuple(nums + [0] * (3 - len(nums))) + ((0,) if "-" in v else (1,))  # pré-release < final


def latest(force: bool = False) -> dict:
    """{current, latest, available, notes, asset_url, size, sha256, page}."""
    import httpx

    s = get_settings()
    current = s.app_version
    if not force and _cache["data"] and time.monotonic() - _cache["at"] < CACHE_S:
        return {**_cache["data"], "current": current}
    try:
        r = httpx.get(s.update_url, timeout=8, headers={"Accept": "application/vnd.github+json"},
                      follow_redirects=True)
        r.raise_for_status()
        rel = r.json()
    except (httpx.HTTPError, ValueError) as e:
        return {"current": current, "available": False, "error": f"não foi possível verificar: {e}"}
    tag = str(rel.get("tag_name", "")).lstrip("v")
    asset = next((a for a in rel.get("assets", []) if str(a.get("name", "")).lower().endswith(".exe")), None)
    digest = str((asset or {}).get("digest") or "")
    data = {
        "latest": tag,
        "available": bool(tag) and current != "dev" and parse_version(tag) > parse_version(current),
        "notes": rel.get("body") or "",
        "page": rel.get("html_url"),
        "asset_url": (asset or {}).get("browser_download_url"),
        "size": (asset or {}).get("size"),
        "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None,
    }
    _cache.update(at=time.monotonic(), data=data)
    return {**data, "current": current}


def state() -> dict:
    return {**_state, "can_install": can_install()}


def can_install() -> bool:
    return get_settings().updater and sys.platform == "win32"


def _download_and_run(info: dict) -> None:
    import httpx

    try:
        dst = Path(tempfile.gettempdir()) / f"EzTractor-Setup-{info['latest']}.exe"
        h = hashlib.sha256()
        with httpx.stream("GET", info["asset_url"], follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or info.get("size") or 0)
            done = 0
            with dst.open("wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if total:
                        _state["progress"] = int(done * 100 / total)
        if info.get("sha256") and h.hexdigest() != info["sha256"]:
            raise RuntimeError("o arquivo baixado está corrompido (hash diferente); tente de novo")
        _state.update(status="installing", progress=100)
        # instala em silêncio; o instalador fecha o app, substitui os arquivos e reabre (/RELAUNCH)
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        subprocess.Popen([str(dst), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          "/RELAUNCH"], creationflags=flags, close_fds=True)
        threading.Timer(1.5, lambda: os._exit(0)).start()
    except Exception as e:  # rede, disco cheio, hash…
        log.exception("falha na atualização")
        _state.update(status="error", error=str(e))


def install() -> dict:
    if not can_install():
        raise RuntimeError("atualização automática só no app Windows instalado")
    with _lock:
        if _state["status"] in ("downloading", "installing"):
            return state()
        info = latest(force=True)
        if not info.get("available") or not info.get("asset_url"):
            raise RuntimeError("não há atualização disponível")
        _state.update(status="downloading", progress=0, error=None)
        threading.Thread(target=_download_and_run, args=(info,), daemon=True).start()
    return state()
