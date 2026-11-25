"""Wrappers finos sobre ffmpeg/ffprobe."""

import json
import subprocess
import sys
import tempfile
import time
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


def run(cmd: list[str], timeout: float | None = None, on_progress=None,
        duration: float | None = None) -> subprocess.CompletedProcess:
    """Executa ffmpeg/ffprobe. Se houver um processamento ativo (control), respeita pausar/cancelar:
    na pausa o processo é suspenso, no cancelamento é encerrado e `Cancelled` é lançado."""
    from ..control import Cancelled, current

    ctrl = current()
    # saída em arquivos temporários: sem risco de travar com saídas grandes (ex.: showinfo de 4 h de vídeo)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdout=out, stderr=err, stdin=subprocess.DEVNULL, **_NO_WINDOW)
        start = time.monotonic()
        try:
            while True:
                try:
                    proc.wait(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if timeout is not None and time.monotonic() - start > timeout:
                    raise MediaError(f"{cmd[0]} demorou mais que {timeout:.0f}s")
                if ctrl is not None:
                    ctrl.check(proc)
                if on_progress and duration:  # lê "out_time_us=" escrito por `-progress pipe:1`
                    out.seek(0, 2)
                    size = out.tell()
                    out.seek(max(0, size - 4096))
                    tail = out.read().decode("ascii", errors="ignore")
                    marks = [ln for ln in tail.splitlines() if ln.startswith("out_time_us=")]
                    if marks:
                        try:
                            on_progress(min(1.0, int(marks[-1].split("=")[1]) / 1e6 / duration))
                        except ValueError:
                            pass
        except BaseException:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        out.seek(0)
        err.seek(0)
        stdout = out.read().decode("utf-8", errors="replace")
        stderr = err.read().decode("utf-8", errors="replace")
    if proc.returncode != 0:
        if ctrl is not None and ctrl.state(fresh=True) == "cancel":
            raise Cancelled()
        raise MediaError(f"{cmd[0]} falhou ({proc.returncode}): {stderr[-1500:]}")
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


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
