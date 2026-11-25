"""Renderiza um clipe vertical 9:16 com ffmpeg."""

from dataclasses import dataclass
from pathlib import Path

from .media import run


@dataclass
class RenderSpec:
    start: float
    end: float
    height: int = 1920  # 1920 => 1080x1920; 1280 => 720x1280
    layout: str = "crop"  # crop | fit | split
    facecam: dict | None = None  # {x,y,w,h} normalizado
    ass_path: Path | None = None

    @property
    def width(self) -> int:
        return int(round(self.height * 9 / 16 / 2)) * 2


def _even(v: float) -> int:
    return max(2, int(v) // 2 * 2)


def build_filter(spec: RenderSpec, src_w: int, src_h: int) -> str:
    W, H = spec.width, spec.height
    if spec.layout == "crop":
        graph = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[v]"
    elif spec.layout == "fit":
        graph = (
            f"[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )
    elif spec.layout == "split":
        if not spec.facecam:
            raise ValueError("layout split exige facecam")
        fc = spec.facecam
        cx, cy = int(fc["x"] * src_w) // 2 * 2, int(fc["y"] * src_h) // 2 * 2
        cw = _even(min(fc["w"] * src_w, src_w - cx))
        ch = _even(min(fc["h"] * src_h, src_h - cy))
        top_h = _even(H * 0.4)
        bot_h = H - top_h
        graph = (
            f"[0:v]split=2[a][b];"
            f"[a]crop={cw}:{ch}:{cx}:{cy},scale={W}:{top_h}:force_original_aspect_ratio=increase,"
            f"crop={W}:{top_h}[cam];"
            f"[b]scale={W}:{bot_h}:force_original_aspect_ratio=increase,crop={W}:{bot_h}[game];"
            f"[cam][game]vstack=inputs=2,setsar=1[v]"
        )
    else:
        raise ValueError(f"layout desconhecido: {spec.layout}")

    if spec.ass_path:
        p = str(spec.ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        graph = graph[: -len("[v]")] + f",ass=filename='{p}'[v]"
    return graph


def render_clip(src: Path, dst: Path, spec: RenderSpec, src_w: int, src_h: int, has_audio: bool) -> Path:
    duration = max(0.1, spec.end - spec.start)
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{spec.start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
        "-filter_complex", build_filter(spec, src_w, src_h),
        "-map", "[v]",
    ]
    if has_audio:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-r", "30", "-movflags", "+faststart", str(dst),
    ]
    run(cmd)
    return dst
