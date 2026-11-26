# -*- mode: python ; coding: utf-8 -*-
# Empacota o EzTractor para Windows (pasta "dist/EzTractor" com EzTractor.exe).
# Uso:  pyinstaller packaging/windows/eztractor.spec --noconfirm
# Antes: compilar o site (web/out) e, para incluir o ffmpeg, definir EZT_FFMPEG_DIR com ffmpeg.exe e ffprobe.exe.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

HERE = Path(SPECPATH)
ROOT = HERE.parents[1]
WEB = ROOT / "web" / "out"
assert WEB.is_dir(), "compile o site antes: cd web && npm run build"

datas = [(str(WEB), "web"), (str(HERE / "eztractor.ico"), ".")]
binaries = []
ffmpeg_dir = os.environ.get("EZT_FFMPEG_DIR")
if ffmpeg_dir:  # build "shared" do ffmpeg: ffmpeg.exe + ffprobe.exe + DLLs compartilhadas
    fdir = Path(ffmpeg_dir)
    assert (fdir / "ffmpeg.exe").exists() and (fdir / "ffprobe.exe").exists(), f"ffmpeg não encontrado em {fdir}"
    for f in [fdir / "ffmpeg.exe", fdir / "ffprobe.exe", *fdir.glob("*.dll")]:
        binaries.append((str(f), "ffmpeg"))

# Código protegido: se EZT_OBF_DIR existir (PyArmor), empacota o eztractor/launcher ofuscados de lá.
OBF = os.environ.get("EZT_OBF_DIR")
if OBF:
    OBF = Path(OBF)
    OBF = OBF if OBF.is_absolute() else (ROOT / OBF).resolve()
SRC = OBF if OBF else (ROOT / "backend")
LAUNCHER = (SRC / "launcher.py") if OBF else (HERE / "launcher.py")
sys.path.insert(0, str(SRC))
_ezt = collect_submodules("eztractor")
assert "eztractor.pipeline.run" in _ezt, f"módulos do eztractor não encontrados: {_ezt}"
# Com o código ofuscado o PyInstaller não enxerga os imports internos: liste-os aqui.
hiddenimports = _ezt + collect_submodules("fastapi") + collect_submodules("starlette") + [
    "anthropic", "httpx", "httpcore", "yt_dlp", "jwt", "segno", "numpy", "wave",
    "PIL.ImageFont", "PIL.Image", "PIL.ImageDraw",
    "uvicorn", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on", "h11",
    "pydantic", "pydantic_settings", "sqlalchemy.dialects.sqlite", "python_multipart", "multipart",
    "tkinter", "tkinter.messagebox",
    "cv2", "shapely", "pyclipper", "omegaconf",
]
if OBF:  # runtime do PyArmor (decifra os módulos em memória)
    runtime = next(Path(OBF).glob("pyarmor_runtime_*"))
    hiddenimports.append(runtime.name)
hiddenimports += ["segno", "webview", "webview.menu", "webview.platforms.edgechromium", "webview.platforms.winforms", "clr"]
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av", "yt_dlp", "webview",
            "rapidocr", "omegaconf", "pyclipper"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # pacote opcional ausente no ambiente de build
        print(f"aviso: não foi possível coletar {pkg}: {e}")

a = Analysis(
    [str(LAUNCHER)],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "matplotlib", "IPython", "psycopg", "psycopg_binary", "pandas", "lxml", "hf_xet", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="EzTractor",
    console=False,
    icon=str(HERE / "eztractor.ico"),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="EzTractor")
