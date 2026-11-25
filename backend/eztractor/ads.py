"""Trechos a pular: propaganda/patrocínio, pedidos de inscrição e finais de vídeo (telas finais com outros canais).

Fontes: (1) SponsorBlock (YouTube, marcações da comunidade) e (2) frases típicas na transcrição.
"""

import logging
import re
import unicodedata

log = logging.getLogger(__name__)

SPONSORBLOCK_URL = "https://sponsor.ajay.app/api/skipSegments"
SB_CATEGORIES = ["sponsor", "selfpromo", "interaction", "outro", "preview"]
REASONS = {
    "sponsor": "Patrocínio", "selfpromo": "Autopromoção", "interaction": "Pedido de inscrição/like",
    "outro": "Final do vídeo", "preview": "Prévia/resumo", "ad": "Propaganda", "endscreen": "Tela final",
}

# (padrão, categoria, segundos antes, segundos depois)
_PHRASES = [
    (r"patrocin|oferecimento|parceiro deste video|parceria com|publi\b|publipost", "sponsor", 3, 30),
    (r"cupom|codigo promocional|use o codigo|desconto exclusivo|link na descri", "sponsor", 8, 15),
    (r"this video is sponsored|sponsored by|today's sponsor|promo code|use code|link in the description",
     "sponsor", 3, 30),
    (r"inscrev|se inscreve|ativa o sininho|ative o sininho|deixa o like|deixe seu like|subscribe|hit the bell",
     "interaction", 2, 8),
]
_OUTRO = r"ate o proximo video|ate a proxima|tchau galera|valeu galera|fui\b|see you next time|thanks for watching|obrigado por assistir"


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def merge(segs: list[dict], gap: float = 2.0) -> list[dict]:
    segs = sorted((s for s in segs if s["end"] - s["start"] > 0.3), key=lambda s: s["start"])
    out: list[dict] = []
    for s in segs:
        if out and s["start"] <= out[-1]["end"] + gap:
            last = out[-1]
            last["end"] = max(last["end"], s["end"])
            if s["category"] != last["category"]:
                last["reason"] = f"{last['reason']} + {s['reason']}"
        else:
            out.append(dict(s))
    return out


def from_transcript(words: list[dict], duration: float) -> list[dict]:
    if not words:
        return []
    text, starts = "", []
    for w in words:  # texto normalizado + início de cada caractere -> tempo
        token = _norm(w["w"]) + " "
        starts.extend([w["start"]] * len(token))
        text += token
    segs = []
    for pattern, cat, before, after in _PHRASES:
        for m in re.finditer(pattern, text):
            t = starts[m.start()]
            segs.append({"start": max(0.0, t - before), "end": min(duration, t + after), "category": cat,
                         "reason": REASONS[cat], "source": "transcricao"})
    for m in re.finditer(_OUTRO, text):  # despedida perto do fim => corta até o fim (tela final)
        t = starts[m.start()]
        if t >= duration * 0.8:
            segs.append({"start": max(0.0, t - 1), "end": duration, "category": "outro",
                         "reason": REASONS["outro"], "source": "transcricao"})
    return merge(segs)


def from_sponsorblock(video_id: str, duration: float, timeout: float = 6.0) -> list[dict]:
    import json

    import httpx

    try:
        r = httpx.get(SPONSORBLOCK_URL, params={"videoID": video_id, "categories": json.dumps(SB_CATEGORIES)},
                      timeout=timeout)
        if r.status_code == 404:  # vídeo sem marcações
            return []
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("SponsorBlock indisponível: %s", e)
        return []
    segs = []
    for item in data:
        s, e = item.get("segment", [0, 0])
        cat = item.get("category", "sponsor")
        segs.append({"start": max(0.0, float(s)), "end": min(duration, float(e)), "category": cat,
                     "reason": REASONS.get(cat, cat), "source": "sponsorblock"})
    return merge(segs)


def overlap(a0: float, a1: float, segs: list[dict]) -> float:
    return sum(max(0.0, min(a1, s["end"]) - max(a0, s["start"])) for s in segs)


def cuts_within(start: float, end: float, segs: list[dict]) -> list[list[float]]:
    """Partes de `segs` dentro de [start, end] (viram cortes do clipe)."""
    out = []
    for s in segs:
        a, b = max(start, s["start"]), min(end, s["end"])
        if b - a > 0.3:
            out.append([round(a, 2), round(b, 2)])
    return out
