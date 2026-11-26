"""Sinais da audiência (o que o público achou viral), quando o vídeo veio do YouTube:

- "Mais repetidos" (heatmap): o gráfico de trechos que os espectadores voltaram para reassistir;
- chat gravado de lives: picos de mensagens, risadas ("kkkk", KEKW, 😂) e empolgação ("POG", "W", 🔥).

Tudo vem pelo yt-dlp, de graça. Vídeos enviados do computador ou de outros sites ficam sem esses sinais.
"""

import json
import re
import unicodedata
from pathlib import Path

import numpy as np

CHAT_DELAY_S = (2, 12)  # o chat reage alguns segundos DEPOIS do lance

_LAUGH = re.compile(r"k{3,}|(?:ha){2,}|(?:he){3,}|(?:ja){2,}|(?:rs){2,}|\blol+\b|\blmao+\b|\brofl\b|"
                    r"kek|\blul\b|omegalul|😂|🤣|💀|😆|😹")
_HYPE = re.compile(r"\bpog+\b|poggers|pogchamp|\bw+\b|\bgg+\b|\bclip|clipa|insano|absurdo|caralho|\bomg\b|\bwtf\b|"
                   r"no way|let'?s go|vamo+|bora|🔥|😱|😮|🤯|❗|!{3,}|\?{3,}")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# ---------------------------------------------------------------- "mais repetidos"
def heatmap_per_second(heatmap: list[dict] | None, n_seconds: int) -> np.ndarray | None:
    """Valores do gráfico (0-1) por segundo, ou None se o vídeo não tem."""
    if not heatmap:
        return None
    out = np.zeros(n_seconds, dtype=np.float32)
    for h in heatmap:
        try:
            a, b, v = float(h["start_time"]), float(h["end_time"]), float(h["value"])
        except (KeyError, TypeError, ValueError):
            continue
        out[int(a):max(int(a) + 1, int(np.ceil(b)))] = v
    return out if out.max() > 0 else None


def heat_relative(heat: np.ndarray) -> np.ndarray:
    """0 = normal do vídeo, 1 = o trecho mais repetido."""
    med = float(np.median(heat))
    span = max(float(heat.max()) - med, 1e-6)
    return np.clip((heat - med) / span, 0, 1).astype(np.float32)


# ---------------------------------------------------------------- chat de lives (YouTube)
def _message_text(renderer: dict) -> str:
    parts = []
    for run in (renderer.get("message") or {}).get("runs", []):
        if "text" in run:
            parts.append(run["text"])
        elif "emoji" in run:
            e = run["emoji"]
            parts.append(e.get("emojiId") if len(e.get("emojiId", "")) <= 2 else " ".join(e.get("shortcuts", [])[:1]))
    return " ".join(p for p in parts if p)


def parse_youtube_chat(path: Path) -> list[tuple[float, str]]:
    """Arquivo .live_chat.json do yt-dlp (uma ação por linha) -> [(segundo do vídeo, texto)]."""
    out: list[tuple[float, str]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            replay = obj.get("replayChatItemAction") or {}
            try:
                t = int(replay.get("videoOffsetTimeMsec", -1)) / 1000
            except (TypeError, ValueError):
                continue
            if t < 0:
                continue
            for action in replay.get("actions", []):
                item = ((action.get("addChatItemAction") or {}).get("item")) or {}
                r = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                if r:
                    out.append((t, _message_text(r)))
    return out


def chat_per_second(messages: list[tuple[float, str]], n_seconds: int) -> dict:
    """Contagens por segundo: mensagens, risadas e empolgação."""
    msgs = np.zeros(n_seconds, dtype=np.float32)
    fun = np.zeros(n_seconds, dtype=np.float32)
    for t, text in messages:
        s = int(t)
        if 0 <= s < n_seconds:
            msgs[s] += 1
            txt = _norm(text)
            if _LAUGH.search(txt) or _HYPE.search(txt):
                fun[s] += 1
    return {"msgs": msgs.round(2).tolist(), "fun": fun.round(2).tolist(), "total": len(messages)}


def _rolling_median(x: np.ndarray, half: int, stride: int = 10) -> np.ndarray:
    """Mediana móvel aproximada (calculada a cada `stride` s e interpolada): rápida para lives longas."""
    n = len(x)
    if n == 0:
        return x
    pts = np.arange(0, n, stride)
    med = np.array([np.median(x[max(0, p - half):p + half + 1]) for p in pts], dtype=np.float32)
    return np.interp(np.arange(n), pts, med).astype(np.float32)


def chat_signal(msgs: np.ndarray, fun: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(z do volume do chat, fração de risada/empolgação), já adiantados para o momento do lance."""
    n = len(msgs)
    k = np.ones(5) / 5
    rate = np.convolve(msgs, k, mode="same")
    fun_rate = np.convolve(fun, k, mode="same")
    base = _rolling_median(rate, 300)  # o chat costuma crescer ao longo da live: compara com o "normal" do trecho
    spread = _rolling_median(np.abs(rate - base), 300) * 1.4826
    z = (rate - base) / np.maximum(spread, 0.5)
    share = np.where(rate > 0.2, fun_rate / np.maximum(rate, 1e-6), 0.0)
    # o lance no segundo s aparece no chat entre s+2 e s+12: usa o pico dessa janela
    a, b = CHAT_DELAY_S
    lead_z = np.zeros(n, dtype=np.float32)
    lead_fun = np.zeros(n, dtype=np.float32)
    for s in range(n):
        lo, hi = min(n, s + a), min(n, s + b + 1)
        if hi > lo:
            lead_z[s] = z[lo:hi].max()
            lead_fun[s] = share[lo:hi].max()
    return lead_z.astype(np.float32), lead_fun.astype(np.float32)


# ---------------------------------------------------------------- download (yt-dlp)
def download_youtube_chat(url: str, dest_dir: Path, on_progress=None) -> Path | None:
    """Baixa o chat gravado de uma live do YouTube. Sem chat (ou falha) -> None, sem derrubar o processo."""
    import logging

    from ..control import Cancelled, current

    log = logging.getLogger(__name__)
    try:
        import yt_dlp
    except ImportError:  # pragma: no cover
        return None
    ctrl = current()

    def hook(d: dict) -> None:
        if ctrl is not None:
            ctrl.check()
        if on_progress and d.get("status") == "downloading":
            frag, total = d.get("fragment_index"), d.get("fragment_count")
            if frag and total:
                on_progress(min(1.0, frag / total))

    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "skip_download": True, "writesubtitles": True, "subtitleslangs": ["live_chat"],
        "outtmpl": str(dest_dir / "chat.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True,
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Cancelled:
        raise
    except Exception as e:
        if ctrl is not None and ctrl.state(fresh=True) == "cancel":
            raise Cancelled() from e
        log.warning("chat da live indisponível: %s", e)
        return None
    found = sorted(dest_dir.glob("chat*.live_chat.json"))
    return found[0] if found else None
