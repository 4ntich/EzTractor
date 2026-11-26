"""Banners de outros canais / propaganda queimados na imagem, lendo o texto dos quadros (OCR local e grátis).

Só lê os trechos que interessam (candidatos a clipe + começo e fim do vídeo), 1 quadro a cada ~3 s.
Para não confundir com o próprio overlay do streamer:
- texto que aparece em boa parte dos quadros lidos (ex.: "twitch.tv/meucanal" fixo) é ignorado;
- o nome/@ do próprio canal (vindo do yt-dlp) é ignorado;
- alertas da live ("acabou de seguir", "obrigado pelo sub") não contam como propaganda.
"""

import logging
import re
import tempfile
import threading
import unicodedata
from pathlib import Path

import numpy as np

from .media import run

log = logging.getLogger(__name__)

STEP_S = 3.0
OCR_WIDTH = 640

# peso 2: quase sempre propaganda/pedido de outro canal; peso 1: só conta junto com outra pista
_STRONG = re.compile(r"inscrev|subscribe|patrocin|sponsor|cupom|coupon|desconto|discount|\d+ ?% ?off|"
                     r"link na bio|link in bio|link na descri|use o codigo|use code|sorteio|giveaway")
_WEAK = re.compile(r"\bcanal\b|\bchannel\b|\bsegue\b|\bsiga\b|\bfollow\b|assista|\bwatch\b|confira|check out|"
                   r"\bloja\b|\bstore\b|\bshop\b|compre|\bbuy\b|parceir|partner|\bpromo|\bcodigo\b|\bcode\b|baixe")
_HANDLE = re.compile(r"@[a-z0-9_.]{3,}")
_LINK = re.compile(r"youtube|youtu\.be|twitch\.tv|tiktok|instagram|kick\.com|discord\.gg|linktr\.ee|"
                   r"\bwww\.|\.com\b|\.gg/|\.tv/")
# alertas da própria live: não são propaganda
_ALERT = re.compile(r"acabou de seguir|just followed|new follower|novo seguidor|obrigad[oa] pel[oa]|thanks? for the|"
                    r"subscribed|se inscreveu|\bsub(s)?\b|resub|bits|donat|doou|doacao|raid|hosted|cheer")

_engine = None
_lock = threading.Lock()


def available() -> bool:
    try:
        import rapidocr  # noqa: F401
    except Exception:  # pragma: no cover - depende da instalação
        return False
    return True


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr import RapidOCR

            _engine = RapidOCR(params={"Global.log_level": "error"})
        return _engine


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def _key(text: str) -> str:
    """Chave para achar o mesmo texto em quadros diferentes (ignora pontuação e espaços)."""
    return re.sub(r"[^a-z0-9@]", "", norm(text))


def promo_score(text: str, own: list[str]) -> int:
    t = norm(text)
    if not t or _ALERT.search(t):
        return 0
    for o in own:  # menções ao próprio canal não contam
        t = t.replace(o, " ")
    score = 0
    if _STRONG.search(t):
        score += 2
    if _HANDLE.search(t):
        score += 2
    if _LINK.search(t):
        score += 2
    score += len(set(m.group(0) for m in _WEAK.finditer(t)))
    return score


def _read_frames(video: Path, start: float, end: float, src_w: int, src_h: int) -> tuple[np.ndarray, list[float]]:
    h = max(2, int(round(OCR_WIDTH * src_h / max(1, src_w) / 2)) * 2)
    with tempfile.TemporaryDirectory(prefix="ezt-ocr-", ignore_cleanup_errors=True) as tmp:
        raw = Path(tmp) / "f.rgb"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{max(0.5, end - start):.2f}",
             "-i", str(video), "-an", "-sn",
             # 1 quadro a cada STEP_S a partir do 1º (o filtro fps pegaria o quadro do MEIO de cada intervalo,
             # deslocando os horários em ~1,5 s)
             "-vf", f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{STEP_S - 0.02:.2f})',scale={OCR_WIDTH}:{h}",
             "-fps_mode", "vfr", "-f", "rawvideo", "-pix_fmt", "rgb24", str(raw)])
        data = np.fromfile(raw, dtype=np.uint8)
    size = OCR_WIDTH * h * 3
    n = data.size // size
    frames = data[: n * size].reshape(n, h, OCR_WIDTH, 3)
    return frames, [start + i * STEP_S for i in range(n)]


def _frame_at(video: Path, t: float, src_w: int, src_h: int) -> np.ndarray | None:
    frames, _ = _read_frames_one(video, t, src_w, src_h)
    return frames[0] if len(frames) else None


def _read_frames_one(video: Path, t: float, src_w: int, src_h: int):
    h = max(2, int(round(OCR_WIDTH * src_h / max(1, src_w) / 2)) * 2)
    with tempfile.TemporaryDirectory(prefix="ezt-ocr-", ignore_cleanup_errors=True) as tmp:
        raw = Path(tmp) / "f.rgb"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video), "-an", "-sn",
             "-frames:v", "1", "-vf", f"scale={OCR_WIDTH}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", str(raw)])
        data = np.fromfile(raw, dtype=np.uint8)
    size = OCR_WIDTH * h * 3
    n = data.size // size
    return data[: n * size].reshape(n, h, OCR_WIDTH, 3), [t]


def _merge_windows(windows: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted((max(0.0, a), min(duration, b)) for a, b in windows):
        if b <= a:
            continue
        if out and a <= out[-1][1] + STEP_S:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def find_banners(video: Path, windows: list[tuple[float, float]], duration: float, src_w: int, src_h: int,
                 own_names: list[str] | None = None, on_progress=None, already: set[float] | None = None,
                 ) -> tuple[list[dict], dict]:
    """Lê os quadros dos trechos `windows` e devolve (trechos com banner, estatísticas)."""
    from ..control import checkpoint

    if not available():
        return [], {"ocr": False}
    engine = _get_engine()
    own = [norm(o).lstrip("@") for o in (own_names or []) if o and len(norm(o).lstrip("@")) >= 3]
    windows = _merge_windows(windows, duration)
    total = sum(b - a for a, b in windows) or 1.0
    done = 0.0
    seen: list[tuple[float, list[str]]] = []  # (tempo, textos do quadro)
    for a, b in windows:
        frames, times = _read_frames(video, a, b, src_w, src_h)
        for img, t in zip(frames, times):
            checkpoint()
            if already is not None and any(abs(t - x) < STEP_S / 2 for x in already):
                continue
            try:
                res = engine(img)
                texts = [str(x) for x in (getattr(res, "txts", None) or ())]
            except Exception as e:  # OCR nunca pode derrubar o processamento
                log.warning("OCR falhou em %.1fs: %s", t, e)
                texts = []
            seen.append((t, texts))
            if already is not None:
                already.add(t)
        done += b - a
        if on_progress:
            on_progress(min(1.0, done / total))

    # texto que aparece em >= 35% dos quadros lidos = overlay fixo do próprio streamer
    counts: dict[str, int] = {}
    for _, texts in seen:
        for k in {_key(x) for x in texts if _key(x)}:
            counts[k] = counts.get(k, 0) + 1
    fixed = {k for k, c in counts.items() if len(seen) >= 6 and c / len(seen) >= 0.35}

    hits: list[tuple[float, str]] = []
    for t, texts in seen:
        shown = [x for x in texts if _key(x) not in fixed]
        joined = " ".join(shown)
        if promo_score(joined, own) >= 2 or any(promo_score(x, own) >= 2 for x in shown):
            hits.append((t, joined[:120]))

    def is_banner_at(t: float) -> bool:
        img = _frame_at(video, t, src_w, src_h)
        if img is None:
            return False
        try:
            texts = [str(x) for x in (getattr(engine(img), "txts", None) or ())]
        except Exception:
            return False
        shown = [x for x in texts if _key(x) not in fixed]
        return promo_score(" ".join(shown), own) >= 2 or any(promo_score(x, own) >= 2 for x in shown)

    def refine(inside: float, outside: float, steps: int = 3) -> float:
        """Busca binária da borda do banner entre um quadro com banner e um sem (precisão ~0,4 s)."""
        for _ in range(steps):
            mid = (inside + outside) / 2
            if is_banner_at(mid):
                inside = mid
            else:
                outside = mid
        return outside

    hit_times = [t for t, _ in hits]
    seen_times = sorted(t for t, _ in seen)
    segs: list[dict] = []
    for t, text in hits:
        a, b = max(0.0, t - STEP_S / 2), min(duration, t + STEP_S / 2)
        if segs and a <= segs[-1]["end"] + 0.1:
            segs[-1]["end"] = b
        else:
            segs.append({"start": round(a, 2), "end": round(b, 2), "category": "banner",
                         "reason": "Banner de outro canal/propaganda", "source": "imagem", "text": text,
                         "_first": t, "_last": t})
        segs[-1]["_last"] = t
    for seg in segs:  # bordas precisas: lê alguns quadros extras só perto do começo e do fim
        checkpoint()
        first, last = seg.pop("_first"), seg.pop("_last")
        before = max((x for x in seen_times if x < first), default=None)
        after = min((x for x in seen_times if x > last), default=None)
        if before is not None and first - before <= STEP_S * 1.5 and before not in hit_times:
            seg["start"] = round(max(0.0, refine(first, before) - 0.2), 2)
        if after is not None and after - last <= STEP_S * 1.5 and after not in hit_times:
            seg["end"] = round(min(duration, refine(last, after) + 0.2), 2)
    return segs, {"ocr": True, "frames": len(seen), "banners": len(segs)}
