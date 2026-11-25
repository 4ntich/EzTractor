"""Títulos, ganchos e explicações sem IA, a partir da transcrição e dos sinais.

Ideia: o melhor gancho costuma ser o que o streamer gritou no momento mais intenso.
1. Divide a fala do clipe em frases (pausas > 0,6 s ou pontuação).
2. Dá nota a cada frase: palavras de empolgação, proximidade do pico de áudio, tamanho bom para ler.
3. A melhor frase vira o gancho; o título combina essa frase (ou um modelo) com o nome do jogo.
"""

import re

from .signals import _HYPE_NORM, _MULTI_NORM, _norm

MAX_HOOK = 50
MAX_TITLE = 60

# Modelos usados quando não há fala aproveitável, por idioma e pelo sinal dominante do clipe.
TEMPLATES = {
    "pt": {
        "audio": ("Reação explosiva", "Espera o final…"),
        "scene": ("Ação sem parar", "Olha o que acontece"),
        "speech": ("Ele falou isso mesmo?", "Escuta isso"),
        "default": ("Melhor momento da live", "Olha isso!"),
        "reason": "Pico de volume {z}σ, {cuts} cortes de cena, {hype} palavras de empolgação.",
    },
    "en": {
        "audio": ("Explosive reaction", "Wait for the end…"),
        "scene": ("Non-stop action", "Watch what happens"),
        "speech": ("Did he really say that?", "Listen to this"),
        "default": ("Best moment of the stream", "Look at this!"),
        "reason": "Volume peak {z}σ, {cuts} scene cuts, {hype} hype words.",
    },
    "es": {
        "audio": ("Reacción explosiva", "Espera al final…"),
        "scene": ("Acción sin parar", "Mira lo que pasa"),
        "speech": ("¿De verdad dijo eso?", "Escucha esto"),
        "default": ("Mejor momento del directo", "¡Mira esto!"),
        "reason": "Pico de volumen {z}σ, {cuts} cortes de escena, {hype} palabras de emoción.",
    },
}

_END_PUNCT = re.compile(r"[.!?…]$")


def _lang(language: str | None) -> dict:
    return TEMPLATES.get((language or "pt")[:2].lower(), TEMPLATES["pt"])


def split_phrases(words: list[dict], max_gap: float = 0.6, max_words: int = 12) -> list[list[dict]]:
    phrases: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        if cur and (w["start"] - cur[-1]["end"] > max_gap or len(cur) >= max_words):
            phrases.append(cur)
            cur = []
        cur.append(w)
        if _END_PUNCT.search(w["w"]):
            phrases.append(cur)
            cur = []
    if cur:
        phrases.append(cur)
    return phrases


def _hype_count(phrase: list[dict]) -> int:
    toks = [_norm(w["w"]) for w in phrase]
    n = sum(1 for t in toks if t in _HYPE_NORM)
    n += sum(1 for a, b in zip(toks, toks[1:]) if f"{a} {b}" in _MULTI_NORM)
    return n


def _phrase_score(phrase: list[dict], peak_t: float | None) -> float:
    n = len(phrase)
    score = 3.0 * _hype_count(phrase)
    if peak_t is not None:
        mid = (phrase[0]["start"] + phrase[-1]["end"]) / 2
        score += max(0.0, 2.0 - abs(mid - peak_t) / 3)  # perto do pico vale mais
    score += 1.0 if 2 <= n <= 8 else (0.3 if n == 1 else 0.0)  # tamanho bom para tela
    if any("!" in w["w"] or "?" in w["w"] for w in phrase):
        score += 0.5
    return score


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    if len(text) > limit:
        cut = text[: limit - 1].rsplit(" ", 1)[0]
        text = cut.rstrip(" ,;:-") + "…"
    return text


def _dominant(stats: dict) -> str:
    z, cuts, hype, words = (stats.get(k, 0) for k in ("audio_peak_z", "scene_cuts", "hype_words", "words"))
    if z >= 2.0:
        return "audio"
    if cuts >= 3:
        return "scene"
    if words >= 15 or hype:
        return "speech"
    return "default"


def make_headline(
    clip_words: list[dict], stats: dict, game: str = "", language: str | None = None
) -> tuple[str, str, str]:
    """Retorna (título, gancho, motivo)."""
    t = _lang(language)
    peak_t = stats.get("peak_t")
    phrases = split_phrases(clip_words)
    best = max(phrases, key=lambda p: _phrase_score(p, peak_t), default=None)

    title_tpl, hook_tpl = t[_dominant(stats)]
    if best is not None and _phrase_score(best, peak_t) >= 1.5:
        phrase_text = " ".join(w["w"] for w in best)
        hook = _clean(phrase_text, MAX_HOOK)
        if not _END_PUNCT.search(hook) and _hype_count(best):
            hook += "!"
        title = _clean(phrase_text, MAX_TITLE)
    else:
        hook, title = hook_tpl, title_tpl

    if game and len(title) + len(game) + 3 <= MAX_TITLE:
        title = f"{title} | {game}"

    reason = t["reason"].format(
        z=f"{stats.get('audio_peak_z', 0):.1f}", cuts=stats.get("scene_cuts", 0), hype=stats.get("hype_words", 0)
    )
    return title, hook, reason
