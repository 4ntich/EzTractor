"""EzTractor para Windows: inicia o servidor local, abre o navegador e mostra uma janelinha de controle.

Empacotado com PyInstaller (eztractor.spec). Estrutura instalada:
    EzTractor.exe
    _internal/            (Python + bibliotecas)
    _internal/ffmpeg/     (ffmpeg.exe, ffprobe.exe)
    _internal/web/        (site estático + fontes)

Dados do usuário (vídeos, banco, modelos do Whisper, configurações) ficam em %LOCALAPPDATA%\\EzTractor.

Modos:
    EzTractor.exe              -> app normal
    EzTractor.exe --selftest   -> processa um vídeo de teste de ponta a ponta e sai (código 0 = ok)
"""

import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "EzTractor"
PORT_RANGE = range(8765, 8785)


# ---------------------------------------------------------------- caminhos
def bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]  # rodando do código-fonte (desenvolvimento)


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


DEFAULT_CONFIG = """# Configurações do EzTractor. Depois de mudar, feche e abra o EzTractor de novo.
# Linhas começando com # são ignoradas.

# Método padrão de análise: heuristic (grátis) | ollama (IA local, grátis) | claude (pago)
EZT_RANKER=heuristic

# IA local: instale o Ollama (https://ollama.com) e rode: ollama pull qwen2.5:7b
EZT_OLLAMA_MODEL=qwen2.5:7b

# Chave da Anthropic (opcional, só para o método claude)
ANTHROPIC_API_KEY=

# Transcrição: faster_whisper | none.  Modelos: tiny, base, small, medium, large-v3
EZT_TRANSCRIBER=faster_whisper
EZT_WHISPER_MODEL=small

# 1920 = 1080x1920 | 1280 = 720x1280 (renderiza mais rápido)
EZT_RENDER_HEIGHT=1920
"""


def load_user_config(d: Path) -> Path:
    cfg = d / "config.env"
    if not cfg.exists():
        cfg.write_text(DEFAULT_CONFIG, encoding="utf-8")
    for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key, value)
    return cfg


def configure_env(selftest: bool = False) -> Path:
    b = bundle_dir()
    d = data_dir() / ("selftest" if selftest else "")
    d.mkdir(parents=True, exist_ok=True)
    if not selftest:
        load_user_config(data_dir())
    ffmpeg_dir = b / "ffmpeg"
    if ffmpeg_dir.is_dir():
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
    web = b / "web"
    os.environ.update({
        "EZT_WEB_DIR": str(web),
        "EZT_FONTS_DIR": str(web / "fonts"),
        "EZT_STORAGE_DIR": str(d / "media"),
        "EZT_DATABASE_URL": "sqlite:///" + (d / "eztractor.db").as_posix(),
        "EZT_QUEUE_MODE": "inline",
        "EZT_CORS_ORIGINS": "http://127.0.0.1",
        "HF_HOME": str(data_dir() / "models"),
    })
    if not os.environ.get("EZT_JWT_SECRET"):
        secret = data_dir() / ".secret"
        if not secret.exists():
            import secrets as _s

            secret.write_text(_s.token_urlsafe(48), encoding="utf-8")
        os.environ["EZT_JWT_SECRET"] = secret.read_text(encoding="utf-8").strip()
    if selftest:
        os.environ.update({"EZT_RANKER": "heuristic", "EZT_TRANSCRIBER": "none", "EZT_RENDER_HEIGHT": "640"})
    return d


# ---------------------------------------------------------------- servidor
def already_running() -> int | None:
    for port in PORT_RANGE:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as r:
                if r.status == 200:
                    return port
        except OSError:
            continue
    return None


def free_port() -> int:
    for port in PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("nenhuma porta livre entre 8765 e 8784")


def start_server(port: int, log_file: Path):
    import logging

    import uvicorn

    logging.basicConfig(filename=str(log_file), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from eztractor.api.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None, loop="asyncio",
                            http="h11", ws="none", lifespan="on")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(300):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5):
                return server
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("o servidor não respondeu")


# ---------------------------------------------------------------- janela
def run_gui() -> None:
    port = already_running()
    if port:  # já aberto: só mostra no navegador
        webbrowser.open(f"http://127.0.0.1:{port}/app/")
        return

    d = configure_env()
    log_file = data_dir() / "eztractor.log"
    import tkinter as tk
    from tkinter import messagebox

    port = free_port()
    try:
        server = start_server(port, log_file)
    except Exception:
        log_file.write_text(traceback.format_exc(), encoding="utf-8")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, f"Não foi possível iniciar o EzTractor.\n\nDetalhes em:\n{log_file}")
        return
    url = f"http://127.0.0.1:{port}/app/"
    webbrowser.open(url)

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("380x230")
    root.resizable(False, False)
    root.configure(bg="#04313B")
    ico = bundle_dir() / "eztractor.ico"
    if ico.exists():
        try:
            root.iconbitmap(str(ico))
        except tk.TclError:
            pass

    tk.Label(root, text="EzTractor está rodando", fg="#ffffff", bg="#04313B",
             font=("Segoe UI", 13, "bold")).pack(pady=(18, 2))
    tk.Label(root, text=url, fg="#7DD3FC", bg="#04313B", font=("Segoe UI", 9)).pack()
    tk.Label(root, text="Feche esta janela para desligar.", fg="#9CC9D1", bg="#04313B",
             font=("Segoe UI", 9)).pack(pady=(2, 12))

    row = tk.Frame(root, bg="#04313B")
    row.pack()

    def btn(text, cmd, primary=False):
        tk.Button(row, text=text, command=cmd, width=15, relief="flat", cursor="hand2",
                  bg="#1684FF" if primary else "#0B4A57", fg="#ffffff", activebackground="#006CE6",
                  activeforeground="#ffffff", font=("Segoe UI", 9, "bold" if primary else "normal")
                  ).pack(side="left", padx=4, pady=4)

    btn("Abrir EzTractor", lambda: webbrowser.open(url), primary=True)
    btn("Pasta dos vídeos", lambda: os.startfile(str(d / "media")) if hasattr(os, "startfile") else None)

    row2 = tk.Frame(root, bg="#04313B")
    row2.pack()
    tk.Button(row2, text="Configurações", width=15, relief="flat", bg="#0B4A57", fg="#ffffff", cursor="hand2",
              command=lambda: os.startfile(str(data_dir() / "config.env")) if hasattr(os, "startfile") else None
              ).pack(side="left", padx=4, pady=4)
    tk.Button(row2, text="Sair", width=15, relief="flat", bg="#0B4A57", fg="#fca5a5", cursor="hand2",
              command=root.destroy).pack(side="left", padx=4, pady=4)

    (d / "media").mkdir(parents=True, exist_ok=True)
    root.mainloop()
    server.should_exit = True
    time.sleep(0.5)


# ---------------------------------------------------------------- autoteste
def selftest() -> int:
    """Testa o pacote de ponta a ponta: servidor, ffmpeg, pipeline, templates, site e bibliotecas."""
    import json
    import shutil
    import subprocess
    import uuid

    d = configure_env(selftest=True)
    shutil.rmtree(d / "media", ignore_errors=True)
    (d / "eztractor.db").unlink(missing_ok=True)
    log = data_dir() / "selftest.log"
    lines: list[str] = []

    def say(msg: str) -> None:
        lines.append(msg)
        log.write_text("\n".join(lines), encoding="utf-8")
        print(msg, flush=True)

    def req(method: str, path: str, body: bytes | None = None, ctype: str | None = None):
        r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method)
        if ctype:
            r.add_header("Content-Type", ctype)
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, resp.read()

    try:
        say(f"bundle: {bundle_dir()}")
        say("ffmpeg: " + str(shutil.which("ffmpeg")))
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        ver = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True, **flags).stdout
        assert " ass " in ver, "ffmpeg sem o filtro ass (libass)"

        import ctranslate2  # noqa: F401  (transcrição disponível no pacote)
        import faster_whisper  # noqa: F401
        import yt_dlp  # noqa: F401
        say("bibliotecas: faster-whisper, ctranslate2, yt-dlp ok")

        port = free_port()
        start_server(port, data_dir() / "selftest-server.log")
        say(f"servidor ok na porta {port}")

        status, html = req("GET", "/app/")
        assert status == 200 and b"EzTractor" in html, "site não carregou"
        status, _ = req("GET", "/fonts/Anton-Regular.ttf")
        assert status == 200
        say("site e fontes ok")

        video = d / "teste.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=40",
            "-f", "lavfi", "-i", "aevalsrc='0.02*sin(2*PI*440*t)+if(between(t,20,24),0.8*sin(2*PI*880*t),0)':s=44100:d=40",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(video),
        ], check=True, **flags)

        presets = json.loads(req("GET", "/template-presets")[1])
        _, tpl = req("POST", "/templates", json.dumps(
            {"name": "Autoteste", "config": presets[0]["config"], "is_default": True}).encode(), "application/json")
        say(f"template criado: {json.loads(tpl)['name']}")
        status, jpg = req("POST", "/templates/preview", json.dumps({"config": presets[5]["config"]}).encode(),
                          "application/json")
        assert status == 200 and jpg[:2] == b"\xff\xd8", "prévia do template falhou"
        say("prévia do template ok")

        boundary = uuid.uuid4().hex
        settings = json.dumps({"max_clips": 2, "clip_min_s": 6, "clip_max_s": 10, "game": "Teste"})
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"settings\"\r\n\r\n{settings}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"teste.mp4\"\r\n"
            f"Content-Type: video/mp4\r\n\r\n"
        ).encode() + video.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        _, created = req("POST", "/projects/upload", body, f"multipart/form-data; boundary={boundary}")
        pid = json.loads(created)["id"]

        project = {}
        for _ in range(240):
            project = json.loads(req("GET", f"/projects/{pid}")[1])
            if project["status"] in ("ready", "failed"):
                break
            time.sleep(0.5)
        assert project.get("status") == "ready", f"processamento falhou: {project.get('error')}"
        clips = project["clips"]
        assert clips and all(c["render_status"] == "ready" for c in clips), "clipes não renderizados"
        top = clips[0]
        assert top["start_s"] <= 22 <= top["end_s"], f"clipe errado: {top['start_s']}–{top['end_s']}"
        status, mp4 = req("GET", top["video_url"])
        assert status == 200 and len(mp4) > 10_000, "vídeo do clipe vazio"
        say(f"pipeline ok: {len(clips)} clipes, melhor em {top['start_s']}–{top['end_s']}s, {len(mp4)} bytes")

        if os.environ.get("EZT_SELFTEST_WHISPER") == "1":  # baixa o modelo tiny (~75 MB) e transcreve
            os.environ["EZT_TRANSCRIBER"] = "faster_whisper"
            os.environ["EZT_WHISPER_MODEL"] = "tiny"
            from eztractor import config as _cfg
            from eztractor.pipeline.media import extract_audio
            from eztractor.pipeline.transcribe import transcribe

            _cfg.get_settings.cache_clear()
            wav = extract_audio(video, d / "teste.wav")
            words, lang = transcribe(wav)
            say(f"whisper ok: modelo carregado e executado ({len(words)} palavras, idioma {lang})")
        say("SELFTEST OK")
        return 0
    except Exception:
        say("SELFTEST FALHOU\n" + traceback.format_exc())
        return 1


def main() -> None:
    if "--selftest" in sys.argv:
        code = selftest()
        os._exit(code)
    run_gui()


if __name__ == "__main__":
    main()
