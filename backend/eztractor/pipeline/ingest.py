"""Ingestão: baixa VODs (YouTube, Twitch, Kick…) via yt-dlp."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..control import Cancelled, current
from .media import MediaError


@dataclass
class Downloaded:
    path: Path
    title: str
    video_id: str = ""
    extractor: str = ""


def _format(max_height: int) -> str:
    if not max_height:
        return "bv*+ba/b"
    return f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b"


def download_url(
    url: str, dest_dir: Path, max_height: int = 1080, on_progress: Callable[[float], None] | None = None,
) -> Downloaded:
    """Baixa o vídeo. `on_progress` recebe 0..1. Respeita pausar/cancelar do processamento atual."""
    try:
        import yt_dlp
    except ImportError as e:  # pragma: no cover
        raise MediaError("yt-dlp não instalado") from e

    ctrl = current()

    def hook(d: dict) -> None:
        if ctrl is not None:
            ctrl.check()  # na pausa o download fica parado aqui; no cancelamento lança Cancelled
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(1.0, d.get("downloaded_bytes", 0) / total))

    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "format": _format(max_height),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Cancelled:
        raise
    except Exception as e:  # yt-dlp lança várias classes próprias (e pode embrulhar o Cancelled)
        if ctrl is not None and ctrl.state(fresh=True) == "cancel":
            raise Cancelled() from e
        raise MediaError(f"falha ao baixar o vídeo: {e}") from e

    # após o merge a extensão pode mudar para .mp4
    if not path.exists():
        candidates = sorted(p for p in dest_dir.glob("source.*") if not p.name.endswith(".part"))
        if not candidates:
            raise MediaError("download concluído mas arquivo não encontrado")
        path = candidates[0]
    return Downloaded(path, str(info.get("title") or "").strip(), str(info.get("id") or ""),
                      str(info.get("extractor_key") or "").lower())
