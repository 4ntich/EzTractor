"""Renderiza um clipe (vertical por padrão) com ffmpeg."""

from dataclasses import dataclass, field
from pathlib import Path

from .media import run


@dataclass
class RenderSpec:
    start: float
    end: float
    height: int = 1920  # 1920 => 1080x1920; 1280 => 720x1280
    layout: str = "crop"  # crop | fit (fundo desfocado) | contain (fundo sólido) | split (webcam + jogo)
    facecam: dict | None = None  # {x,y,w,h} normalizado
    ass_path: Path | None = None
    width: int | None = None  # None => 9:16 a partir da altura
    background: str = "#000000"  # cor de fundo do modo contain
    zoom: float = 1.0  # zoom no vídeo (1 = sem zoom)
    vignette: bool = False
    bars: list[dict] = field(default_factory=list)  # [{x,y,w,h,color}] em px de saída
    progress: dict | None = None  # {color, height (px), position top|bottom}
    fonts_dir: Path | None = None

    def __post_init__(self):
        if self.width is None:
            self.width = int(round(self.height * 9 / 16 / 2)) * 2
        self.width = _even(self.width)
        self.height = _even(self.height)


def _even(v: float) -> int:
    return max(2, int(round(v)) // 2 * 2)


def _hex(c: str) -> str:
    return "0x" + c.lstrip("#")


def _esc(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def build_filter(spec: RenderSpec, src_w: int, src_h: int) -> str:
    W, H = spec.width, spec.height
    z = max(0.5, spec.zoom)
    ZW, ZH = _even(W * z), _even(H * z)
    if spec.layout == "crop":
        graph = f"[0:v]scale={ZW}:{ZH}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[base]"
    elif spec.layout == "fit":
        graph = (
            f"[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2[bg];"
            f"[b]scale={ZW}:{ZH}:force_original_aspect_ratio=decrease,crop='min(iw,{W})':'min(ih,{H})'[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
        )
    elif spec.layout == "contain":
        graph = (
            f"[0:v]scale={ZW}:{ZH}:force_original_aspect_ratio=decrease,"
            f"crop='min(iw,{W})':'min(ih,{H})',"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={_hex(spec.background)},setsar=1[base]"
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
            f"[cam][game]vstack=inputs=2,setsar=1[base]"
        )
    else:
        raise ValueError(f"layout desconhecido: {spec.layout}")

    chain = []
    if spec.vignette:
        chain.append("vignette=angle=PI/4.5")
    for b in spec.bars:
        chain.append(f"drawbox=x={int(b['x'])}:y={int(b['y'])}:w={max(1, int(b['w']))}:h={max(1, int(b['h']))}"
                     f":color={_hex(b['color'])}@1:t=fill")
    cur = "base"
    if chain:
        graph += f";[{cur}]{','.join(chain)}[deco]"
        cur = "deco"

    if spec.progress:
        dur = max(0.1, spec.end - spec.start)
        ph = max(2, int(spec.progress["height"]))
        y = 0 if spec.progress.get("position") == "top" else H - ph
        graph += (
            f";color=c={_hex(spec.progress['color'])}:s={W}x{ph}:r=30:d={dur:.3f}[pb]"
            f";[{cur}][pb]overlay=x='-w+w*min(1,t/{dur:.3f})':y={y}:shortest=1:eof_action=pass[prog]"
        )
        cur = "prog"

    if spec.ass_path:
        ass = f"ass=filename='{_esc(spec.ass_path)}'"
        if spec.fonts_dir:
            ass += f":fontsdir='{_esc(spec.fonts_dir)}'"
        graph += f";[{cur}]{ass}[v]"
    else:
        graph += f";[{cur}]null[v]"
    return graph


def render_clip(src: Path, dst: Path, spec: RenderSpec, src_w: int, src_h: int, has_audio: bool,
                on_progress=None) -> Path:
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
        "-r", "30", "-t", f"{duration:.3f}", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(dst),
    ]
    run(cmd, on_progress=on_progress, duration=duration)
    return dst


def render_still(src: Path | None, at_s: float, dst: Path, spec: RenderSpec, src_w: int, src_h: int,
                 frame_at: float = 1.2) -> Path:
    """Um quadro do resultado (prévia do template). Sem vídeo, usa um fundo de teste."""
    if src is None:
        sample = (spec.fonts_dir.parent / "sample-gameplay.jpg") if spec.fonts_dir else None
        if sample is not None and sample.exists():  # mesma imagem de fundo da prévia do editor
            src, src_w, src_h = sample, 1920, 1080
            seek = ["-loop", "1", "-t", "4"]
            inp = ["-i", str(src)]
            cmd = ["ffmpeg", "-y", "-v", "error", *seek, *inp, "-filter_complex", build_filter(spec, src_w, src_h),
                   "-map", "[v]", "-ss", f"{frame_at:.2f}", "-frames:v", "1", "-q:v", "3", str(dst)]
            run(cmd)
            return dst
    if src is None:
        src_w, src_h = 1920, 1080
        inp = ["-f", "lavfi", "-i", f"gradients=s={src_w}x{src_h}:c0=0x1e1b4b:c1=0x7c3aed:c2=0x0f172a:x0=0:y0=0"
               f":x1={src_w}:y1={src_h}:nb_colors=3:d=4"]
        seek = []
    else:
        inp = ["-i", str(src)]
        seek = ["-ss", f"{at_s:.3f}"]
    # o quadro é pego em `frame_at` s do clipe, depois das animações de entrada
    cmd = ["ffmpeg", "-y", "-v", "error", *seek, *inp, "-filter_complex", build_filter(spec, src_w, src_h),
           "-map", "[v]", "-ss", f"{frame_at:.2f}", "-frames:v", "1", "-q:v", "3", str(dst)]
    run(cmd)
    return dst


def cut_concat(src: Path, segs: list[tuple[float, float]], dst: Path, has_audio: bool, final: bool = False,
               on_progress=None) -> Path:
    """Junta os trechos [ini, fim] de `src` (remove o que ficou de fora). final=True => qualidade de entrega."""
    n = len(segs)
    v_split = f"[0:v]split={n}" + "".join(f"[vi{i}]" for i in range(n)) if n > 1 else "[0:v]null[vi0]"
    parts = [v_split]
    if has_audio:
        parts.append(f"[0:a]asplit={n}" + "".join(f"[ai{i}]" for i in range(n)) if n > 1 else "[0:a]anull[ai0]")
    for i, (a, b) in enumerate(segs):
        parts.append(f"[vi{i}]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        if has_audio:
            parts.append(f"[ai{i}]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
    ins = "".join(f"[v{i}][a{i}]" if has_audio else f"[v{i}]" for i in range(n))
    parts.append(f"{ins}concat=n={n}:v=1:a={1 if has_audio else 0}[v]" + ("[a]" if has_audio else ""))
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", ";".join(parts), "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k" if final else "160k"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast" if final else "ultrafast", "-crf", "20" if final else "14",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(dst)]
    run(cmd, on_progress=on_progress, duration=sum(b - a for a, b in segs))
    return dst
