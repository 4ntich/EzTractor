"""Gera web/app/themes.css (variáveis de cor por tema e modo). Rode: python web/scripts/gen_themes.py"""

from pathlib import Path

STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]


def hx(h: str) -> str:
    h = h.lstrip("#")
    return f"{int(h[0:2], 16)} {int(h[2:4], 16)} {int(h[4:6], 16)}"


# Superfícies/texto no modo escuro (50 = mais claro ... 950 = fundo). No claro a escala é invertida.
SURFACES = {
    "teal": ["#ECFBFC", "#D6F0F3", "#B8DEE3", "#92C4CC", "#8DBBC4", "#6A9EA8", "#30636F", "#1E4C58", "#113A45", "#092A34", "#041C23"],
    "zinc": ["#FAFAFA", "#F4F4F5", "#E4E4E7", "#D4D4D8", "#A1A1AA", "#71717A", "#52525B", "#3F3F46", "#27272A", "#18181B", "#09090B"],
    "stone": ["#FBF8F1", "#F3EEE3", "#E2D9C6", "#CBBFA6", "#B5A88C", "#8E8169", "#5A5040", "#433B2F", "#2D2820", "#1C1914", "#0E0C09"],
    "green": ["#EEFBF5", "#D7F3E6", "#B4E4CE", "#86CDAE", "#6FBF9D", "#5E9C82", "#2C6A52", "#1F5240", "#153B2E", "#0D271F", "#061611"],
    "plum": ["#FCF2F6", "#F5E1EA", "#E6C5D3", "#D1A0B5", "#BE8CA3", "#9A7086", "#664257", "#4E3143", "#382331", "#251720", "#150C12"],
}
ACCENTS = {
    "blue": ["#EFF8FF", "#DBEEFF", "#B9DEFF", "#84C5FF", "#48A6FF", "#1684FF", "#006CE6", "#0056BD", "#004599", "#003473", "#00214D"],
    "violet": ["#F5F3FF", "#EDE9FE", "#DDD6FE", "#C4B5FD", "#A78BFA", "#8B5CF6", "#7C3AED", "#6D28D9", "#5B21B6", "#4C1D95", "#2E1065"],
    "gold": ["#FFFBEB", "#FDF3CF", "#F9E39B", "#F2CC62", "#E6B53A", "#D4A02A", "#B5821E", "#8F6418", "#6B4A14", "#4A330F", "#2B1D08"],
    "emerald": ["#ECFDF5", "#D1FAE5", "#A7F3D0", "#6EE7B7", "#34D399", "#10B981", "#059669", "#047857", "#065F46", "#064E3B", "#022C22"],
    "sunset": ["#FFF4ED", "#FFE6D5", "#FECCAA", "#FDAA74", "#FB7D3C", "#F95D16", "#EA430C", "#C2300C", "#9A2812", "#7C2412", "#430F07"],
}

THEMES = {
    # nome: (superfície, destaque, texto do botão, fundo escuro, fundo claro, vidro molhado?)
    "aero": ("teal", "blue", "#FFFFFF",
             "radial-gradient(1400px 900px at 12% -20%, rgba(64,224,208,.20), transparent 80%),"
             "radial-gradient(1200px 800px at 100% 0%, rgba(0,160,210,.16), transparent 82%),"
             "linear-gradient(165deg, #063B46 0%, #04303A 55%, #042A33 100%)",
             "radial-gradient(1400px 900px at 12% -20%, rgba(64,224,208,.28), transparent 82%),"
             "linear-gradient(165deg, #EAF8FA 0%, #DAEFF3 55%, #EAF8FA 100%)", True),
    "violeta": ("zinc", "violet", "#FFFFFF",
                "radial-gradient(1000px 600px at 10% -10%, rgba(139,92,246,.30), transparent 60%),"
                "radial-gradient(800px 600px at 100% 10%, rgba(236,72,153,.18), transparent 60%),"
                "linear-gradient(160deg, #0B0B12 0%, #14111F 50%, #09090B 100%)",
                "radial-gradient(1000px 600px at 10% -10%, rgba(139,92,246,.22), transparent 60%),"
                "linear-gradient(160deg, #F7F5FF 0%, #EEEAFB 100%)", False),
    "ouro": ("stone", "gold", "#1C1408",
             "radial-gradient(1000px 600px at 12% -12%, rgba(212,160,42,.22), transparent 60%),"
             "radial-gradient(700px 500px at 100% 0%, rgba(255,255,255,.05), transparent 60%),"
             "linear-gradient(160deg, #0E0C09 0%, #17130D 50%, #0A0907 100%)",
             "radial-gradient(1000px 600px at 12% -12%, rgba(212,160,42,.22), transparent 60%),"
             "linear-gradient(160deg, #FBF7EE 0%, #F1E9D6 100%)", False),
    "esmeralda": ("green", "emerald", "#FFFFFF",
                  "radial-gradient(1000px 600px at 10% -10%, rgba(16,185,129,.28), transparent 60%),"
                  "radial-gradient(800px 500px at 100% 10%, rgba(5,150,105,.18), transparent 60%),"
                  "linear-gradient(160deg, #04140F 0%, #072019 50%, #03100B 100%)",
                  "radial-gradient(1000px 600px at 10% -10%, rgba(16,185,129,.25), transparent 60%),"
                  "linear-gradient(160deg, #F0FBF6 0%, #DDF3E9 100%)", False),
    "sunset": ("plum", "sunset", "#FFFFFF",
               "radial-gradient(1000px 600px at 8% -10%, rgba(249,93,22,.28), transparent 60%),"
               "radial-gradient(900px 600px at 100% 0%, rgba(236,72,153,.25), transparent 60%),"
               "linear-gradient(160deg, #150C12 0%, #26121D 50%, #0F080C 100%)",
               "radial-gradient(1000px 600px at 8% -10%, rgba(249,93,22,.22), transparent 60%),"
               "radial-gradient(900px 600px at 100% 0%, rgba(236,72,153,.18), transparent 60%),"
               "linear-gradient(160deg, #FFF6F0 0%, #FBE6EE 100%)", False),
}

DROPLETS = (  # gotas irregulares (tamanhos/posições/ladrilhos diferentes => sem padrão visível)
    "radial-gradient(ellipse 2.2px 3px at 14% 18%, rgba(255,255,255,.20), rgba(255,255,255,.05) 70%, transparent 100%),"
    "radial-gradient(circle at 71% 63%, rgba(255,255,255,.13) 0 1.2px, transparent 2.4px),"
    "radial-gradient(ellipse 3.5px 4.5px at 33% 77%, rgba(255,255,255,.10), rgba(255,255,255,.03) 70%, transparent 100%),"
    "radial-gradient(circle at 86% 21%, rgba(255,255,255,.09) 0 0.8px, transparent 1.8px),"
    "radial-gradient(ellipse 1.6px 2.4px at 52% 41%, rgba(255,255,255,.12), transparent 100%)"
)


def block(selector: str, surface: list[str], accent: list[str], on_accent: str, bg: str, dark: bool, wet: bool) -> str:
    z = surface if dark else list(reversed(surface))
    if not dark:  # no claro o "900" (cartões) é branco puro e o fundo vem do gradiente
        z = z[:9] + ["#FFFFFF"] + [z[10]]
    lines = [f"{selector} {{", f"  color-scheme: {'dark' if dark else 'light'};"]
    lines += [f"  --z-{s}: {hx(c)};" for s, c in zip(STEPS, z)]
    acc = accent if dark else list(reversed(accent))  # no claro, tons de destaque escuros p/ contraste
    lines += [f"  --a-{s}: {hx(c)};" for s, c in zip(STEPS, acc)]
    # botões: mesma cor nos dois modos
    lines += [f"  --b-{s}: {hx(c)};" for s, c in zip(STEPS, accent)]
    strong = "#FFFFFF" if dark else surface[10]
    lines += [
        f"  --strong: {hx(strong)};",
        f"  --on-accent: {hx(on_accent)};",
        f"  --bg: {bg};",
        f"  --glass-bg: {'rgba(255,255,255,.065)' if dark else 'rgba(255,255,255,.58)'};",
        f"  --glass-bg-strong: {'rgba(255,255,255,.10)' if dark else 'rgba(255,255,255,.78)'};",
        f"  --glass-border: {('rgba(190,245,255,.24)' if wet else 'rgba(255,255,255,.12)') if dark else 'rgba(255,255,255,.9)'};",
        f"  --glass-edge: {'rgba(0,0,0,.35)' if dark else 'rgba(15,40,50,.10)'};",
        "  --glass-highlight: linear-gradient(180deg, rgba(255,255,255,"
        f"{'.20' if wet else '.08'}) 0%, rgba(255,255,255,{'.05' if wet else '.02'}) 44%, rgba(255,255,255,0) 50%);",
        "  --glass-shadow: 0 1px 0 rgba(255,255,255,"
        f"{'.22' if dark else '.9'}) inset, 0 22px 45px -18px rgba(0,0,0,{'.6' if dark else '.18'}), 0 2px 8px rgba(0,0,0,{'.25' if dark else '.06'});",
        f"  --droplets: {DROPLETS if wet else 'none'};",
        "}",
    ]
    return "\n".join(lines)


out = ["/* Gerado por web/scripts/gen_themes.py — não edite à mão. */"]
for name, (surf, acc, on_accent, bg_dark, bg_light, wet) in THEMES.items():
    base = ":root" if name == "aero" else f':root[data-theme="{name}"]'
    dark_sel = f'{base}, {base}[data-mode="dark"]' if name == "aero" else f'{base}, {base}[data-mode="dark"]'
    if name == "aero":
        dark_sel = ':root, :root[data-theme="aero"]'
        light_sel = ':root[data-mode="light"]:not([data-theme]), :root[data-theme="aero"][data-mode="light"]'
    else:
        light_sel = f'{base}[data-mode="light"]'
    out.append(block(dark_sel, SURFACES[surf], ACCENTS[acc], on_accent, bg_dark, True, wet))
    out.append(block(light_sel, SURFACES[surf], ACCENTS[acc], on_accent, bg_light, False, wet))

Path(__file__).resolve().parents[1].joinpath("app", "themes.css").write_text("\n\n".join(out) + "\n", encoding="utf-8")
print("themes.css gerado:", len(THEMES), "temas")
