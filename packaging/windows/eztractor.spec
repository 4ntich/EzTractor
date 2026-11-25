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

sys.path.insert(0, str(ROOT / "backend"))  # o pacote eztractor precisa estar visível para ser coletado
_ezt = collect_submodules("eztractor")
assert "eztractor.pipeline.run" in _ezt, f"módulos do eztractor não encontrados: {_ezt}"
hiddenimports = _ezt + [
    "anthropic", "httpx", "yt_dlp", "PIL.ImageFont", "sqlalchemy.dialects.sqlite", "python_multipart",
    "tkinter", "tkinter.messagebox",
]
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "tokenizers", "av", "yt_dlp"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # pacote opcional ausente no ambiente de build
        print(f"aviso: não foi possível coletar {pkg}: {e}")

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT / "backend")],
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
