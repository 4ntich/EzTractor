"""Legenda e hashtags prontas para postar (TikTok, Reels, Shorts), sem IA.

As IAs (Ollama/Claude) escrevem a própria legenda no ranker; isto aqui é o modo grátis e o plano B
para clipes antigos ou quando a IA não devolve legenda.
"""

import re
import unicodedata

MAX_HASHTAGS = 8  # mais que isso tende a ser tratado como spam pelas redes
MAX_CAPTION = 2200  # limite do Instagram (o TikTok aceita mais)

_EMOJI = {"audio": "😱", "scene": "🔥", "speech": "😂", "default": "🎮"}

_TEXT = {
    "pt": {"cta_game": "Segue pra mais clipes de {game}! 🎮", "cta": "Segue pra mais clipes! 🎮",
           "tags": ["#gaming", "#gamer", "#jogos", "#clips", "#viral", "#fyp", "#parati"]},
    "en": {"cta_game": "Follow for more {game} clips! 🎮", "cta": "Follow for more clips! 🎮",
           "tags": ["#gaming", "#gamer", "#games", "#clips", "#viral", "#fyp", "#foryou"]},
    "es": {"cta_game": "¡Sígueme para más clips de {game}! 🎮", "cta": "¡Sígueme para más clips! 🎮",
           "tags": ["#gaming", "#gamer", "#juegos", "#clips", "#viral", "#fyp", "#parati"]},
}

# jogos conhecidos: tags que a comunidade realmente usa (chave = nome normalizado, sem espaços)
_GAME_TAGS = {
    "valorant": ["#valorant", "#valorantclips"],
    "freefire": ["#freefire", "#ff"],
    "cs2": ["#cs2", "#counterstrike"],
    "csgo": ["#csgo", "#counterstrike"],
    "counterstrike": ["#counterstrike", "#cs2"],
    "counterstrike2": ["#cs2", "#counterstrike"],
    "fortnite": ["#fortnite", "#fortniteclips"],
    "minecraft": ["#minecraft", "#minecraftclips"],
    "gta": ["#gta", "#gtarp"],
    "gtav": ["#gta5", "#gtarp"],
    "gta5": ["#gta5", "#gtarp"],
    "gtarp": ["#gtarp", "#gta5"],
    "lol": ["#leagueoflegends", "#lol"],
    "leagueoflegends": ["#leagueoflegends", "#lol"],
    "warzone": ["#warzone", "#callofduty"],
    "callofduty": ["#callofduty", "#cod"],
    "apex": ["#apexlegends", "#apex"],
    "apexlegends": ["#apexlegends", "#apex"],
    "dota2": ["#dota2", "#dota"],
    "rocketleague": ["#rocketleague", "#rl"],
    "eafc": ["#eafc", "#fifa"],
    "fifa": ["#fifa", "#eafc"],
    "pubg": ["#pubg", "#pubgmobile"],
    "roblox": ["#roblox", "#robloxclips"],
}


def _lang(language: str | None) -> str:
    code = (language or "pt")[:2].lower()
    return code if code in _TEXT else "pt"


def _slug(text: str) -> str:
    """'Free Fire' -> 'freefire', 'Counter-Strike 2' -> 'counterstrike2'."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t.lower())


def normalize_hashtags(tags: list[str] | str | None) -> list[str]:
    """Aceita lista ou texto ('#a b, #c'); devolve tags únicas com '#', sem espaços, na ordem dada."""
    if tags is None:
        return []
    items = tags.replace(",", " ").split() if isinstance(tags, str) else tags
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        word = re.sub(r"[^\w]", "", str(raw).lstrip("#"), flags=re.UNICODE)
        if not word:
            continue
        tag = "#" + word
        if tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out[:30]


def make_hashtags(game: str = "", language: str | None = None) -> list[str]:
    slug = _slug(game)
    game_tags = _GAME_TAGS.get(slug) or ([f"#{slug}"] if 2 <= len(slug) <= 30 else [])
    return normalize_hashtags(game_tags + _TEXT[_lang(language)]["tags"])[:MAX_HASHTAGS]


def make_caption(title: str, hook: str = "", game: str = "", language: str | None = None,
                 dominant: str = "default") -> str:
    t = _TEXT[_lang(language)]
    title = (title or "").strip()
    hook = (hook or "").strip()
    first = f"{title} {_EMOJI.get(dominant, _EMOJI['default'])}".strip() if title else ""
    lines = [first] if first else []
    if hook and hook.lower().rstrip("!?.…") != title.lower().rstrip("!?.…"):
        lines.append(hook)
    lines.append(t["cta_game"].format(game=game.strip()) if game.strip() else t["cta"])
    return "\n".join(lines)[:MAX_CAPTION]


def dominant_signal(stats: dict | None) -> str:
    """Mesmo critério do gerador de títulos: o que mais chama atenção no clipe."""
    from .headlines import _dominant

    try:
        return _dominant(stats or {})
    except (KeyError, TypeError, ValueError):
        return "default"


def social_text(caption: str, hashtags: list[str]) -> str:
    """Texto final para colar na rede: legenda + linha em branco + hashtags."""
    tags = " ".join(hashtags)
    return f"{caption.strip()}\n\n{tags}".strip() if tags else caption.strip()
