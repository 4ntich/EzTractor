"""Wrappers finos sobre ffmpeg/ffprobe."""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class MediaError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    duration_s: float
    width: int
    height: int
    has_audio: bool


# No Windows (app sem console) cada ffmpeg abriria uma janela preta: CREATE_NO_WINDOW evita isso.
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def run(cmd: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    # utf-8 explícito: no Windows o padrão seria cp1252 e a saída do ffmpeg quebraria a leitura
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, **_NO_WINDOW)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-1500:]
        raise MediaError(f"{cmd[0]} falhou ({proc.returncode}): {tail}")
    return proc


def probe(path: Path) -> MediaInfo:
    out = run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    ).stdout
    data = json.loads(out)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise MediaError("arquivo não contém trilha de vídeo")
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise MediaError("não foi possível determinar a duração do vídeo")
    return MediaInfo(duration, int(video["width"]), int(video["height"]), has_audio)


def extract_audio(src: Path, dst: Path, sample_rate: int = 16000) -> Path:
    """WAV mono 16 kHz PCM s16 — entrada para transcrição e análise de energia."""
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sample_rate),
         "-c:a", "pcm_s16le", str(dst)])
    return dst


def thumbnail(src: Path, at_s: float, dst: Path, height: int = 640) -> Path:
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{at_s:.3f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale=-2:{height}", str(dst)])
    return dst
