"""Ingestão: baixa VODs (YouTube, Twitch, Kick…) via yt-dlp."""

from pathlib import Path

from .media import MediaError


def download_url(url: str, dest_dir: Path, max_height: int = 1080) -> Path:
    try:
        import yt_dlp
    except ImportError as e:  # pragma: no cover
        raise MediaError("yt-dlp não instalado") from e

    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as e:  # yt-dlp lança várias classes próprias
        raise MediaError(f"falha ao baixar o vídeo: {e}") from e

    # após o merge a extensão pode mudar para .mp4
    if not path.exists():
        candidates = sorted(dest_dir.glob("source.*"))
        if not candidates:
            raise MediaError("download concluído mas arquivo não encontrado")
        path = candidates[0]
    return path
