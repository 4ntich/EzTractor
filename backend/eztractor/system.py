"""Acesso pelo celular (rede local), reinício do app e informações do sistema."""

import os
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path

from .config import get_settings


def lan_ips() -> list[str]:
    ips: set[str] = set()
    try:  # IP da interface de saída (não envia pacotes)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    private = re.compile(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")
    return sorted(ip for ip in ips if private.match(ip))


def lan_info() -> dict:
    s = get_settings()
    port = int(os.environ.get("EZT_PORT", "8765"))
    return {
        "enabled": s.lan_access,
        "configurable": bool(s.config_file),
        "password_set": bool(s.app_password),
        "urls": [f"http://{ip}:{port}/app/" for ip in lan_ips()] if s.lan_access else [],
    }


def write_config(values: dict[str, str]) -> None:
    """Atualiza chaves no config.env do app (mantém comentários e o resto do arquivo)."""
    path = Path(get_settings().config_file or "")
    if not path.name:
        raise RuntimeError("configuração só pode ser alterada no app instalado")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values and not line.lstrip().startswith("#"):
            lines[i] = f"{key}={values[key]}"
            seen.add(key)
    lines += [f"{k}={v}" for k, v in values.items() if k not in seen]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def can_restart() -> bool:
    return bool(getattr(sys, "frozen", False))


def restart() -> None:
    """Reabre o app (o novo processo espera este terminar) e encerra este."""
    if not can_restart():
        raise RuntimeError("reinício automático só no app instalado; feche e abra de novo")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    subprocess.Popen([sys.executable, "--wait-pid", str(os.getpid())], creationflags=flags, close_fds=True)
    threading.Timer(1.0, lambda: os._exit(0)).start()


def qr_svg(data: str) -> str:
    import segno

    import io

    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=6, border=2, dark="#04313B", light="#FFFFFF",
                                     xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")
