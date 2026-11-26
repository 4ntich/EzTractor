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
APP_VERSION = "dev"  # substituído no build (sed) pela versão real
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
# Onde rodar a transcrição: auto (placa de vídeo NVIDIA se o CUDA estiver instalado, senão processador) | cpu | cuda
EZT_WHISPER_DEVICE=auto

# Qualidade padrão do vídeo final (dá para escolher em cada projeto, na tela):
# 640=360p 854=480p 1280=720p 1920=1080p 2560=1440p 3840=4K
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
    cfg_path = None
    if not selftest:
        cfg_path = load_user_config(data_dir())
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
        "EZT_APP_VERSION": APP_VERSION,
        "EZT_TRUST_LOCALHOST": "1",   # a janela do app (localhost) nunca pede senha
        "EZT_UPDATER": "1",           # atualização automática disponível
    })
    if cfg_path is not None:
        os.environ["EZT_CONFIG_FILE"] = str(cfg_path)
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

    host = "0.0.0.0" if os.environ.get("EZT_LAN_ACCESS", "0") in ("1", "true", "True") else "127.0.0.1"
    config = uvicorn.Config(app, host=host, port=port, log_config=None, loop="asyncio",
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


# ---------------------------------------------------------------- janela própria (WebView2)
def _open_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]


class _DesktopApi:
    """Métodos que a página web chama (window.pywebview.api.*) — substituem o menu branco nativo."""

    # Só métodos públicos aqui: um atributo público (ex.: a janela) quebra a ponte JS do pywebview.
    def __init__(self, media_dir, url):
        self._media = media_dir
        self._url = url
        self._window = None

    def open_videos(self):
        _open_path(self._media / ".")

    def open_config(self):
        _open_path(data_dir() / "config.env")

    def open_browser(self):
        webbrowser.open(self._url)

    def quit(self):
        if self._window:
            self._window.destroy()


def _dark_titlebar(window) -> None:
    """Pinta a barra de título do Windows de escuro (combina com o app em vez do branco padrão)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        val = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (Win10 2004+ e builds antigas)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def _clear_page_cache_on_update(storage: Path) -> None:
    """Na 1ª abertura de uma versão nova, apaga o cache de páginas da janela (WebView2). Sem isso a janela
    podia continuar mostrando as páginas da versão anterior depois de atualizar. O armazenamento local
    (tema, preferências) fica intacto: só as pastas de cache são apagadas."""
    import shutil

    marker = storage / "versao.txt"
    try:
        if marker.exists() and marker.read_text(encoding="utf-8").strip() == APP_VERSION:
            return
        for name in ("Cache", "Code Cache", "GPUCache", "Service Worker"):
            for p in storage.rglob(name):
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
        storage.mkdir(parents=True, exist_ok=True)
        marker.write_text(APP_VERSION, encoding="utf-8")
    except OSError:
        pass  # nunca impede o app de abrir


def run_app(smoke: bool = False) -> int:
    """Abre o EzTractor numa janela própria (sem navegador). Retorna o código de saída."""
    import webview

    port = already_running()
    server = None
    if port is None:
        d = configure_env()
        port = free_port()
        os.environ["EZT_PORT"] = str(port)
        server = start_server(port, data_dir() / "eztractor.log")
    else:
        d = data_dir()
    url = f"http://127.0.0.1:{port}/app/"

    _clear_page_cache_on_update(data_dir() / "webview")
    webview.settings["ALLOW_DOWNLOADS"] = True  # botões "Baixar" abrem o "Salvar como"
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    api = _DesktopApi(d / "media", url)
    # sem menu nativo (a barra branca): as ações vão para um menu dentro do app, nas cores do tema
    window = webview.create_window(APP_NAME, url, width=1320, height=880, min_size=(420, 600),
                                   background_color="#04313B", text_select=True, js_api=api)
    api._window = window
    window.events.loaded += lambda: _dark_titlebar(window)
    result = {"code": 0}

    def smoke_check():  # --gui-smoke: confirma que a janela abriu e o app carregou dentro dela
        log = data_dir() / "gui-smoke.log"
        try:
            window.events.loaded.wait(30)
            ok = False
            for _ in range(60):
                info = window.evaluate_js("document.title + '|' + !!document.querySelector('nav')")
                if info and str(info).startswith("EzTractor") and str(info).endswith("true"):
                    ok = True
                    break
                time.sleep(0.5)
            log.write_text(f"janela: {info}\nGUI SMOKE {'OK' if ok else 'FALHOU'}", encoding="utf-8")
            result["code"] = 0 if ok else 1
        except Exception:
            log.write_text("GUI SMOKE FALHOU\n" + traceback.format_exc(), encoding="utf-8")
            result["code"] = 1
        finally:
            window.destroy()

    webview.start(smoke_check if smoke else None, gui="edgechromium" if sys.platform == "win32" else None,
                  private_mode=False, storage_path=str(data_dir() / "webview"))
    if server is not None:
        server.should_exit = True
        time.sleep(0.3)
    return result["code"]


def run_browser_fallback() -> None:
    """Sem WebView2 (raro no Windows 10/11): abre no navegador com uma janelinha de controle."""
    port = already_running()
    if port:  # já aberto: só mostra no navegador
        webbrowser.open(f"http://127.0.0.1:{port}/app/")
        return

    d = configure_env()
    log_file = data_dir() / "eztractor.log"
    import tkinter as tk
    from tkinter import messagebox

    port = free_port()
    os.environ["EZT_PORT"] = str(port)
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

        # leitura de banners (OCR) dentro do pacote: modelos, onnxruntime e OpenCV precisam estar lá
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        from eztractor.pipeline import overlays

        img = Image.new("RGB", (640, 360), (25, 25, 30))
        font = ImageFont.truetype(str(Path(os.environ["EZT_FONTS_DIR"]) / "Poppins-Bold.ttf"), 40)
        ImageDraw.Draw(img).text((30, 150), "INSCREVA-SE @OUTRO", font=font, fill=(255, 255, 255))
        txt = " ".join(str(t) for t in (overlays._get_engine()(np.array(img)).txts or ()))
        assert "INSCREVA" in txt.upper(), f"OCR não leu o texto de teste: {txt!r}"
        say(f"leitura de banners (OCR) ok: {txt!r}")

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


def _wait_pid(pid: int) -> None:
    import ctypes

    h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid) if sys.platform == "win32" else 0
    if h:
        ctypes.windll.kernel32.WaitForSingleObject(h, 15000)
        ctypes.windll.kernel32.CloseHandle(h)
    else:
        time.sleep(2)


def main() -> None:
    if "--wait-pid" in sys.argv:
        i = sys.argv.index("--wait-pid")
        try:
            _wait_pid(int(sys.argv[i + 1]))
        except (ValueError, IndexError):
            pass
    if "--selftest" in sys.argv:
        os._exit(selftest())
    if "--gui-smoke" in sys.argv:
        os._exit(run_app(smoke=True))
    try:
        code = run_app()
    except Exception:
        (data_dir() / "eztractor.log").open("a", encoding="utf-8").write(traceback.format_exc())
        run_browser_fallback()
        code = 0
    os._exit(code)


if __name__ == "__main__":
    main()
