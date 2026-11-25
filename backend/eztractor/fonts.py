"""Fontes disponíveis nos templates.

Os arquivos ficam em web/public/fonts (servidos ao navegador pelo editor e usados pelo
libass no render), então a prévia e o vídeo final usam exatamente as mesmas fontes.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import get_settings


@dataclass(frozen=True)
class Font:
    key: str
    label: str
    family: str  # nome da família dentro do .ttf (usado no ASS e no CSS)
    regular: str  # arquivo
    bold: str | None = None  # arquivo do negrito, se houver (senão o negrito é sintético)
    group: str = "Básicas"


FONTS: dict[str, Font] = {f.key: f for f in [
    Font("sans", "Sem serifa (Poppins)", "Poppins", "Poppins-Regular.ttf", "Poppins-Bold.ttf"),
    Font("serif", "Serifada (DM Serif)", "DM Serif Display", "DMSerifDisplay-Regular.ttf"),
    Font("mono", "Monoespaçada (Space Mono)", "Space Mono", "SpaceMono-Regular.ttf", "SpaceMono-Bold.ttf"),
    Font("condensed", "Condensada (Fjalla One)", "Fjalla One", "FjallaOne-Regular.ttf"),
    Font("anton", "Impacto (Anton)", "Anton", "Anton-Regular.ttf", group="Títulos"),
    Font("bebas", "Bebas Neue", "Bebas Neue", "BebasNeue-Regular.ttf", group="Títulos"),
    Font("archivo", "Pesada (Archivo Black)", "Archivo Black", "ArchivoBlack-Regular.ttf", group="Títulos"),
    Font("bungee", "Letreiro (Bungee)", "Bungee", "Bungee-Regular.ttf", group="Títulos"),
    Font("rubikmono", "Bloco (Rubik Mono One)", "Rubik Mono One", "RubikMonoOne-Regular.ttf", group="Títulos"),
    Font("russo", "Gamer (Russo One)", "Russo One", "RussoOne-Regular.ttf", group="Games"),
    Font("blackops", "Militar (Black Ops One)", "Black Ops One", "BlackOpsOne-Regular.ttf", group="Games"),
    Font("pixel", "Pixel / Arcade (Press Start 2P)", "Press Start 2P", "PressStart2P-Regular.ttf", group="Games"),
    Font("bangers", "Quadrinhos (Bangers)", "Bangers", "Bangers-Regular.ttf", group="Divertidas"),
    Font("luckiest", "Cartoon (Luckiest Guy)", "Luckiest Guy", "LuckiestGuy-Regular.ttf", group="Divertidas"),
    Font("marker", "Marcador (Permanent Marker)", "Permanent Marker", "PermanentMarker-Regular.ttf",
         group="Divertidas"),
    Font("brush", "Pincel (Caveat Brush)", "Caveat Brush", "CaveatBrush-Regular.ttf", group="Divertidas"),
    Font("pacifico", "Manuscrita (Pacifico)", "Pacifico", "Pacifico-Regular.ttf", group="Divertidas"),
]}


def fonts_dir() -> Path:
    configured = get_settings().fonts_dir
    if configured:
        return Path(configured)
    # repositório: backend/eztractor/fonts.py -> web/public/fonts
    return Path(__file__).resolve().parents[2] / "web" / "public" / "fonts"


def get_font(key: str) -> Font:
    return FONTS.get(key, FONTS["sans"])


@lru_cache(maxsize=64)
def _pil_font(path: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(path, size)


def font_file(key: str, bold: bool) -> Path | None:
    f = get_font(key)
    name = f.bold if (bold and f.bold) else f.regular
    p = fonts_dir() / name
    return p if p.exists() else None


# Fator medido (altura da letra no navegador / altura no libass com o mesmo tamanho), por fonte e negrito.
# O libass dimensiona pela "altura da célula" da fonte, o navegador pelo "em": sem isso o vídeo sairia
# com o texto 15%–60% menor que a prévia. Recalibrar: tests/test_templates.py::test_font_size_matches_browser.
_ASS_RATIO: dict[tuple[str, bool], float] = {
    ("sans", False): 1.772, ("sans", True): 1.75, ("serif", False): 1.375, ("mono", False): 1.489,
    ("mono", True): 1.489, ("condensed", False): 1.621, ("anton", False): 1.737, ("bebas", False): 1.296,
    ("archivo", False): 1.353, ("bungee", False): 2.571, ("rubikmono", False): 1.228, ("russo", False): 1.207,
    ("blackops", False): 1.429, ("pixel", False): 1.575, ("bangers", False): 1.729, ("luckiest", False): 1.231,
    ("marker", False): 1.448, ("brush", False): 1.291, ("pacifico", False): 1.956,
}


def ass_size_ratio(key: str, bold: bool = False) -> float:
    """Converte o tamanho CSS (px do 'em') para o 'Fontsize' do ASS, para o vídeo ficar igual à prévia."""
    f = get_font(key)
    use_bold = bool(bold and f.bold)
    return _ASS_RATIO.get((f.key, use_bold)) or _ASS_RATIO.get((f.key, False)) or 1.5


def text_width(text: str, key: str, bold: bool, size_px: float, letter_spacing: float = 0) -> float:
    """Largura do texto em px (para quebrar linhas igual ao navegador)."""
    path = font_file(key, bold)
    if path is None or not text:
        return len(text) * size_px * 0.55
    try:
        font = _pil_font(str(path), 200)
        w = font.getlength(text) * size_px / 200
    except Exception:
        w = len(text) * size_px * 0.55
    return w + letter_spacing * max(0, len(text) - 1)


def catalog() -> list[dict]:
    return [{"key": f.key, "label": f.label, "family": f.family, "group": f.group,
             "files": [x for x in (f.regular, f.bold) if x]} for f in FONTS.values()]
