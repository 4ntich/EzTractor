"""Aplica um template (camadas de texto, legendas estilizadas, molduras) a um clipe.

Tudo que é texto vira ASS (renderizado pelo libass no ffmpeg); molduras, vinheta e barra de
progresso viram filtros do ffmpeg (ver render.py). Coordenadas do template são em px no tamanho
do template (ex.: 1080x1920); o libass escala para o tamanho real do vídeo.
"""

import re
from datetime import date

from ..fonts import ass_size_ratio, get_font, text_width
from .captions import _ts, chunk_words

VARIABLES = {
    "titulo": "Título do clipe (IA ou automático)",
    "gancho": "Gancho / frase de impacto",
    "jogo": "Nome do jogo",
    "numero": "Posição do clipe no ranking (1, 2, 3…)",
    "total": "Total de clipes do projeto",
    "nota": "Nota viral (0–100)",
    "projeto": "Título do projeto",
    "data": "Data de hoje (dd/mm/aaaa)",
}
_VAR_RE = re.compile(r"\{(\w+)\}")


def fill_vars(text: str, ctx: dict) -> str:
    """Troca {variavel} pelo valor do clipe. Variáveis desconhecidas ficam como estão."""
    def sub(m: re.Match) -> str:
        key = m.group(1).lower()
        if key in ctx:
            return str(ctx[key] if ctx[key] is not None else "")
        return m.group(0)

    out = _VAR_RE.sub(sub, text)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def clip_context(clip, project, total: int, rank: int) -> dict:
    st = project.settings or {}
    return {
        "titulo": clip.title or "",
        "gancho": clip.hook or "",
        "jogo": st.get("game", "") or "",
        "numero": rank,
        "total": total,
        "nota": clip.score,
        "projeto": project.title or "",
        "data": date.today().strftime("%d/%m/%Y"),
    }


SAMPLE_CONTEXT = {
    "titulo": "Meu deus que clutch", "gancho": "Ninguém acreditou nisso!", "jogo": "Valorant",
    "numero": 1, "total": 8, "nota": 94, "projeto": "Live de sexta", "data": date.today().strftime("%d/%m/%Y"),
}


# ---------------------------------------------------------------- utilidades ASS
def ass_color(hex_color: str, opacity: float = 100) -> str:
    """#RRGGBB + opacidade (0–100) -> &HAABBGGRR (no ASS alpha 00 = opaco)."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    alpha = round((100 - max(0, min(100, opacity))) / 100 * 255)
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _esc(text: str) -> str:
    return text.replace("\\", "∖").replace("{", "(").replace("}", ")")


def wrap_text(text: str, font_key: str, bold: bool, size_px: float, max_w: float, spacing: float = 0) -> list[str]:
    """Quebra em linhas que cabem em max_w px (medindo com a fonte real). Respeita quebras manuais."""
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            trial = f"{cur} {w}"
            if text_width(trial, font_key, bold, size_px, spacing) <= max_w:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


_ALIGN = {"left": 4, "center": 5, "right": 6}


def _style_line(name: str, layer: dict) -> str:
    font = get_font(layer["fontFamily"])
    size = layer["fontSize"] * ass_size_ratio(layer["fontFamily"], layer["bold"])
    box = layer["backgroundEnabled"]
    glow = layer["glow"]
    outline = layer["backgroundPadding"] if box else (max(layer["outlineWidth"], 4) if glow else layer["outlineWidth"])
    outline_colour = (ass_color(layer["backgroundColor"], layer["backgroundOpacity"]) if box
                      else ass_color(layer["outlineColor"], layer["opacity"]))
    return (
        f"Style: {name},{font.family},{size:.1f},"
        f"{ass_color(layer['color'], layer['opacity'])},&HFF000000,{outline_colour},"
        f"{ass_color(layer['shadowColor'], layer['shadowOpacity'] * layer['opacity'] / 100)},"
        f"{-1 if layer['bold'] else 0},{-1 if layer['italic'] else 0},0,0,100,100,"
        f"{layer['letterSpacing']:.1f},{-layer['rotation']:.1f},{3 if box else 1},{outline:.1f},"
        f"{layer['shadowDepth']:.1f},{_ALIGN[layer['align']]},0,0,0,1"
    )


def _layer_times(layer: dict, dur: float, preview: bool) -> tuple[float, float]:
    if preview or layer["showMode"] == "always":
        return 0.0, dur
    secs = min(layer["showSeconds"], dur)
    return (0.0, secs) if layer["showMode"] == "start" else (max(0.0, dur - secs), dur)


def _anim_tags(layer: dict, px: float, py: float, W: int, H: int, dur: float) -> tuple[str, bool]:
    """Retorna (tags, usa_karaoke). Tempos relativos ao início do evento."""
    a = layer["animation"]
    pos = f"\\pos({px:.0f},{py:.0f})"
    if a == "fade":
        return pos + "\\fad(350,250)", False
    if a == "pop":
        return pos + "\\fad(120,0)\\fscx40\\fscy40\\t(0,170,\\fscx112\\fscy112)\\t(170,280,\\fscx100\\fscy100)", False
    if a == "zoom-in":
        return pos + "\\fad(400,0)\\fscx135\\fscy135\\t(0,450,\\fscx100\\fscy100)", False
    if a == "slide-up":
        return f"\\move({px:.0f},{py + H * 0.06:.0f},{px:.0f},{py:.0f},0,350)\\fad(200,0)", False
    if a == "slide-down":
        return f"\\move({px:.0f},{py - H * 0.06:.0f},{px:.0f},{py:.0f},0,350)\\fad(200,0)", False
    if a == "slide-left":
        return f"\\move({px + W * 0.2:.0f},{py:.0f},{px:.0f},{py:.0f},0,350)\\fad(150,0)", False
    if a == "pulse":
        tags, t, n = pos, 0, 0
        while t < dur * 1000 and n < 80:
            tags += f"\\t({t},{t + 400},\\fscx108\\fscy108)\\t({t + 400},{t + 800},\\fscx100\\fscy100)"
            t += 800
            n += 1
        return tags, False
    if a == "typewriter":
        return pos, True
    return pos, False


def _layer_event(i: int, layer: dict, ctx: dict, W: int, H: int, dur: float, preview: bool) -> str | None:
    text = fill_vars(layer["text"], ctx)
    if layer["uppercase"]:
        text = text.upper()
    if not text:
        return None
    max_w = layer["boxWidth"] / 100 * W
    lines = wrap_text(text, layer["fontFamily"], layer["bold"], layer["fontSize"], max_w, layer["letterSpacing"])
    px, py = layer["x"] / 100 * W, layer["y"] / 100 * H
    start, end = _layer_times(layer, dur, preview)
    tags, karaoke = _anim_tags(layer, px, py, W, H, end - start)
    if layer["glow"] and not layer["backgroundEnabled"]:
        tags += "\\blur6"
    if karaoke and not preview:
        chars = sum(len(ln) for ln in lines) or 1
        step = max(2, min(8, int(150 / chars)))  # centésimos por letra (máx. ~1,5 s no total)
        body = "\\N".join("".join(f"{{\\ko{step}}}{_esc(c)}" for c in ln) for ln in lines)
    else:
        body = "\\N".join(_esc(ln) for ln in lines)
    return f"Dialogue: {10 + i},{_ts(start)},{_ts(end)},L{i},,0,0,0,,{{{tags}}}{body}"


def _caption_events(cap: dict, words: list[dict], clip_start: float, clip_end: float, W: int, H: int) -> list[str]:
    dur = clip_end - clip_start
    in_clip = [w for w in words if w["end"] > clip_start and w["start"] < clip_end]
    hl = ass_color(cap["highlightColor"])
    base = ass_color(cap["color"])
    px, py = W / 2, cap["y"] / 100 * H
    out = []
    for chunk in chunk_words(in_clip, max_words=cap["wordsPerLine"]):
        for i, w in enumerate(chunk):
            start = max(w["start"], clip_start) - clip_start
            end = (chunk[i + 1]["start"] if i + 1 < len(chunk) else w["end"]) - clip_start
            end = min(max(end, start + 0.05), dur)
            parts = []
            for j, other in enumerate(chunk):
                word = _esc(other["w"].upper() if cap["uppercase"] else other["w"])
                if j == i:
                    pop = "\\t(0,90,\\fscx118\\fscy118)\\t(90,180,\\fscx108\\fscy108)" if cap["animation"] == "pop" else ""
                    parts.append(f"{{\\1c{hl}{pop}}}{word}{{\\1c{base}\\fscx100\\fscy100}}")
                else:
                    parts.append(word)
            out.append(f"Dialogue: 5,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{{\\pos({px:.0f},{py:.0f})\\q2}}{' '.join(parts)}")
    return out


def build_template_ass(
    cfg: dict, words: list[dict], clip_start: float, clip_end: float, ctx: dict,
    captions: bool = True, preview: bool = False,
) -> str:
    W, H = int(cfg["width"]), int(cfg["height"])
    dur = max(0.1, clip_end - clip_start)
    cap = cfg["captions"]
    cap_size = cap["fontSize"] * ass_size_ratio(cap["fontFamily"], True)
    styles = [
        f"Style: Cap,{get_font(cap['fontFamily']).family},{cap_size:.1f},{ass_color(cap['color'])},&HFF000000,"
        f"{ass_color(cap['outlineColor'])},&H64000000,-1,0,0,0,100,100,0,0,1,{cap['outlineWidth']:.1f},2,5,0,0,0,1",
    ]
    events = []
    for i, layer in enumerate(cfg["layers"]):
        styles.append(_style_line(f"L{i}", layer))
        ev = _layer_event(i, layer, ctx, W, H, dur, preview)
        if ev:
            events.append(ev)
    if captions:
        events.extend(_caption_events(cap, words, clip_start, clip_end, W, H))

    head = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
        "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
    ]
    return "\n".join(head + styles + ["", "[Events]",
                     "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"] + events) + "\n"


def frame_bars(cfg: dict, out_w: int, out_h: int) -> list[dict]:
    """Retângulos da moldura em px do vídeo de saída."""
    f = cfg["frame"]
    bars = []
    if f["headerBorder"]:
        bars.append({"x": 0, "y": 0, "w": out_w, "h": round(out_h * f["headerHeightPercent"] / 100), "color": f["color"]})
    if f["footerBorder"]:
        h = round(out_h * f["footerHeightPercent"] / 100)
        bars.append({"x": 0, "y": out_h - h, "w": out_w, "h": h, "color": f["color"]})
    if f["sideBorders"]:
        w = round(out_w * f["sideWidthPercent"] / 100)
        bars += [{"x": 0, "y": 0, "w": w, "h": out_h, "color": f["color"]},
                 {"x": out_w - w, "y": 0, "w": w, "h": out_h, "color": f["color"]}]
    return bars


def output_size(cfg: dict, max_side: int) -> tuple[int, int]:
    """Tamanho final do vídeo: proporção do template, lado maior limitado a max_side."""
    W, H = int(cfg["width"]), int(cfg["height"])
    f = min(1.0, max_side / max(W, H))
    return max(2, int(W * f) // 2 * 2), max(2, int(H * f) // 2 * 2)


_FIT_TO_LAYOUT = {"cover": "crop", "contain": "contain", "blur": "fit"}


def template_spec(cfg: dict, start: float, end: float, max_side: int, project_layout: str = "crop",
                  facecam: dict | None = None):
    """RenderSpec a partir do template (o layout 'split' do projeto tem prioridade sobre o ajuste)."""
    from ..fonts import fonts_dir
    from .render import RenderSpec

    out_w, out_h = output_size(cfg, max_side)
    pb = cfg["progressBar"]
    return RenderSpec(
        start=start, end=end, width=out_w, height=out_h,
        layout="split" if project_layout == "split" and facecam else _FIT_TO_LAYOUT[cfg["fitMode"]],
        facecam=facecam, background=cfg["backgroundColor"], zoom=cfg["videoZoom"] / 100,
        vignette=cfg["vignette"], bars=frame_bars(cfg, out_w, out_h),
        progress={"color": pb["color"], "height": out_h * pb["heightPercent"] / 100, "position": pb["position"]}
        if pb["enabled"] else None,
        fonts_dir=fonts_dir(),
    )


def normalize(config: dict) -> dict:
    """Valida e completa um config salvo (templates antigos ganham os campos novos com padrão)."""
    from ..schemas import TemplateConfig

    return TemplateConfig.model_validate(config or {}).model_dump()


PREVIEW_WORDS = [  # legenda de exemplo para a prévia (tempo relativo ao início do clipe)
    {"w": "isso", "start": 0.7, "end": 0.95}, {"w": "foi", "start": 1.0, "end": 1.15},
    {"w": "insano", "start": 1.15, "end": 1.6}, {"w": "demais", "start": 1.65, "end": 2.0},
]


def render_preview(cfg: dict, dst, workdir, src=None, src_w: int = 1920, src_h: int = 1080, at_s: float = 0.0,
                   max_side: int = 960, ctx: dict | None = None):
    """Gera um JPG de como o template fica no vídeo (mesmo motor do render final)."""
    from pathlib import Path

    from .captions import write_ass
    from .render import render_still

    cfg = normalize(cfg)
    spec = template_spec(cfg, 0.0, 4.0, max_side)
    ass = build_template_ass(cfg, PREVIEW_WORDS, 0.0, 4.0, ctx or SAMPLE_CONTEXT, captions=True, preview=True)
    spec.ass_path = write_ass(Path(workdir) / "preview.ass", ass)
    return render_still(src, at_s, Path(dst), spec, src_w, src_h)
