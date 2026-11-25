"""Gera legendas ASS (estilo "palavra destacada") + gancho + marca d'água para o render vertical."""

from pathlib import Path


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[dict], max_words: int = 3, max_gap: float = 0.6) -> list[list[dict]]:
    """Agrupa palavras em blocos curtos para leitura rápida em tela vertical."""
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > max_gap):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(
    words: list[dict],
    clip_start: float,
    clip_end: float,
    width: int,
    height: int,
    hook: str = "",
    watermark: str | None = None,
    captions: bool = True,
) -> str:
    """`words` com tempos absolutos do vídeo original; a saída usa tempos relativos ao clipe."""
    scale = height / 1920
    fs_caption = int(78 * scale)
    fs_hook = int(64 * scale)
    fs_wm = int(34 * scale)
    margin_v = int(height * 0.22)
    outline = max(2, int(6 * scale))

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Caption,DejaVu Sans,{fs_caption},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,"
        f"100,100,0,0,1,{outline},2,2,60,60,{margin_v},1",
        f"Style: Hook,DejaVu Sans,{fs_hook},&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,"
        f"100,100,0,0,3,{int(14 * scale)},0,8,80,80,{int(height * 0.08)},1",
        f"Style: Watermark,DejaVu Sans,{fs_wm},&H80FFFFFF,&H80FFFFFF,&H80000000,&H00000000,-1,0,0,0,"
        f"100,100,0,0,1,2,0,3,30,30,30,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    dur = clip_end - clip_start

    if captions:
        in_clip = [w for w in words if w["end"] > clip_start and w["start"] < clip_end]
        for chunk in chunk_words(in_clip):
            for i, w in enumerate(chunk):
                start = max(w["start"], clip_start) - clip_start
                # cada palavra fica destacada até a próxima começar (ou o bloco terminar)
                end = (chunk[i + 1]["start"] if i + 1 < len(chunk) else w["end"]) - clip_start
                end = min(max(end, start + 0.05), dur)
                parts = []
                for j, other in enumerate(chunk):
                    word = _esc(other["w"]).upper()
                    parts.append("{\\c&H00FFFF&}" + word + "{\\c&HFFFFFF&}" if j == i else word)
                lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{' '.join(parts)}")

    if hook:
        lines.append(f"Dialogue: 1,{_ts(0)},{_ts(min(3.0, dur))},Hook,,0,0,0,,{_esc(hook)}")
    if watermark:
        lines.append(f"Dialogue: 2,{_ts(0)},{_ts(dur)},Watermark,,0,0,0,,{_esc(watermark)}")
    return "\n".join(lines) + "\n"


def write_ass(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
