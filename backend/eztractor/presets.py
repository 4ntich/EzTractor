"""Estilos de template prontos (galeria). O usuário pode usar direto ou copiar e editar."""

from .schemas import TemplateCaptions, TemplateConfig, TemplateFrame, TemplateLayer, TemplateProgressBar


def L(id: str, text: str, **kw) -> dict:
    return TemplateLayer(id=id, text=text, **kw).model_dump()


def C(**kw) -> dict:
    return TemplateCaptions(**kw).model_dump()


def F(**kw) -> dict:
    return TemplateFrame(**kw).model_dump()


def P(**kw) -> dict:
    return TemplateProgressBar(enabled=True, **kw).model_dump()


def cfg(**kw) -> dict:
    return TemplateConfig(**kw).model_dump()


PRESETS: list[dict] = [
    {
        "key": "gamer-neon", "name": "Gamer Neon", "category": "Games",
        "description": "Gancho com brilho neon ciano, nome do jogo e barra de progresso.",
        "config": cfg(
            backgroundColor="#0B0B14", accentColor="#00E5FF",
            layers=[
                L("hook", "{gancho}", kind="title", fontFamily="russo", fontSize=68, y=13, uppercase=True,
                  color="#FFFFFF", outlineWidth=3, outlineColor="#00E5FF", glow=True, animation="pop", boxWidth=88),
                L("game", "{jogo}", kind="tag", fontFamily="russo", fontSize=30, y=20.5, color="#00E5FF",
                  uppercase=True, letterSpacing=6, animation="fade"),
            ],
            captions=C(fontFamily="russo", fontSize=81, highlightColor="#00E5FF", y=70),
            progressBar=P(color="#00E5FF", heightPercent=0.7),
        ),
    },
    {
        "key": "impacto", "name": "Impacto Amarelo", "category": "Virais",
        "description": "Título gigante amarelo com contorno grosso, estilo vídeos virais.",
        "config": cfg(
            accentColor="#FFE600",
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="luckiest", fontSize=76, y=13, uppercase=True,
                  color="#FFE600", outlineWidth=7, outlineColor="#000000", shadowDepth=6, shadowOpacity=70,
                  animation="pop", boxWidth=90),
            ],
            captions=C(fontFamily="luckiest", fontSize=86, highlightColor="#FFE600", outlineWidth=6, y=71),
        ),
    },
    {
        "key": "meme", "name": "Meme Clássico", "category": "Virais",
        "description": "Texto branco com contorno preto em cima e embaixo, como os memes clássicos.",
        "config": cfg(
            layers=[
                L("top", "{gancho}", kind="title", fontFamily="anton", fontSize=78, y=9, uppercase=True,
                  color="#FFFFFF", outlineWidth=6, boxWidth=92),
                L("bottom", "@seucanal", kind="tag", fontFamily="anton", fontSize=44, y=92, uppercase=True,
                  color="#FFFFFF", outlineWidth=5),
            ],
            captions=C(fontFamily="anton", fontSize=84, y=70),
        ),
    },
    {
        "key": "tarja-preta", "name": "Tarjas Pretas", "category": "Clean",
        "description": "Barras pretas em cima e embaixo, título no cabeçalho e @ no rodapé.",
        "config": cfg(
            frame=F(headerBorder=True, footerBorder=True, color="#000000", headerHeightPercent=15,
                    footerHeightPercent=12),
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="sans", bold=True, fontSize=50, y=7.5,
                  color="#FFFFFF", boxWidth=90),
                L("handle", "@seucanal", kind="tag", fontFamily="sans", fontSize=30, y=94, color="#A1A1AA"),
            ],
            captions=C(fontFamily="sans", fontSize=75, highlightColor="#FACC15", y=68),
        ),
    },
    {
        "key": "desfocado", "name": "Gameplay com Fundo Desfocado", "category": "Clean",
        "description": "Vídeo inteiro no centro com fundo desfocado, texto acima e abaixo.",
        "config": cfg(
            fitMode="blur",
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="anton", fontSize=66, y=25, uppercase=True,
                  color="#FFFFFF", outlineWidth=4, boxWidth=90, animation="slide-down"),
                L("part", "{jogo} • parte {numero}", kind="tag", fontFamily="sans", bold=True, fontSize=34,
                  y=75, color="#FFFFFF", backgroundEnabled=True, backgroundColor="#7C3AED", backgroundPadding=14,
                  animation="fade"),
            ],
            captions=C(fontFamily="anton", fontSize=75, y=82),
        ),
    },
    {
        "key": "ranking", "name": "Top Ranking + CTA", "category": "Virais",
        "description": "“TOP 1” gigante, título em caixa e chamada para seguir nos últimos segundos.",
        "config": cfg(
            accentColor="#FACC15",
            layers=[
                L("rank", "TOP {numero}", kind="title", fontFamily="anton", fontSize=120, y=10, color="#FACC15",
                  outlineWidth=6, shadowDepth=5, animation="zoom-in"),
                L("title", "{titulo}", kind="text", fontFamily="sans", bold=True, fontSize=40, y=19, color="#FFFFFF",
                  backgroundEnabled=True, backgroundColor="#000000", backgroundOpacity=70, backgroundPadding=12,
                  boxWidth=86),
                L("cta", "SEGUE PRA VER O TOP {total}", kind="tag", fontFamily="anton", fontSize=58, y=50,
                  color="#000000", backgroundEnabled=True, backgroundColor="#FACC15", backgroundPadding=18,
                  animation="pop", showMode="end", showSeconds=3),
            ],
            captions=C(fontFamily="anton", fontSize=84, y=72, highlightColor="#FACC15"),
        ),
    },
    {
        "key": "noticia", "name": "Terço Inferior (Notícia)", "category": "Clean",
        "description": "Etiqueta e título em caixas à esquerda, estilo telejornal.",
        "config": cfg(
            layers=[
                L("tag", "{jogo}", kind="tag", fontFamily="bebas", fontSize=36, x=6, y=74, align="left",
                  color="#000000", backgroundEnabled=True, backgroundColor="#FFFFFF", backgroundPadding=10,
                  uppercase=True, letterSpacing=3, animation="slide-left"),
                L("title", "{titulo}", kind="title", fontFamily="bebas", fontSize=62, x=6, y=80, align="left",
                  color="#FFFFFF", backgroundEnabled=True, backgroundColor="#E11D48", backgroundPadding=12,
                  boxWidth=80, animation="slide-left"),
            ],
            captions=C(fontFamily="bebas", fontSize=91, y=62, highlightColor="#F43F5E", uppercase=True),
        ),
    },
    {
        "key": "arcade", "name": "Retrô Arcade", "category": "Games",
        "description": "Fonte pixel, bordas magenta, efeito máquina de escrever e vinheta.",
        "config": cfg(
            vignette=True, accentColor="#FF2BD6",
            frame=F(sideBorders=True, color="#FFFFFF", sideWidthPercent=2.5),
            layers=[
                L("hook", "{gancho}", kind="title", fontFamily="pixel", fontSize=36, y=12, color="#FFE600",
                  outlineWidth=4, uppercase=True, boxWidth=86, animation="typewriter"),
                L("score", "PLAYER 1   SCORE {nota}", kind="tag", fontFamily="pixel", fontSize=22, y=92,
                  color="#22D3EE", outlineWidth=3),
            ],
            captions=C(fontFamily="pixel", fontSize=47, highlightColor="#FF2BD6", outlineWidth=4, y=70,
                       wordsPerLine=2),
        ),
    },
    {
        "key": "militar", "name": "FPS Militar", "category": "Games",
        "description": "Fonte militar, cabeçalho verde-oliva e selo de killcam.",
        "config": cfg(
            vignette=True, accentColor="#C2B280",
            frame=F(headerBorder=True, color="#FFFFFF", headerHeightPercent=9),
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="blackops", fontSize=46, y=4.6, color="#E8E3C8",
                  uppercase=True, boxWidth=92),
                L("kill", "KILLCAM #{numero}", kind="tag", fontFamily="blackops", fontSize=28, y=92,
                  color="#C2B280", backgroundEnabled=True, backgroundColor="#000000", backgroundOpacity=65,
                  backgroundPadding=10, animation="fade"),
            ],
            captions=C(fontFamily="blackops", fontSize=75, highlightColor="#C2B280", y=72),
        ),
    },
    {
        "key": "quadrinhos", "name": "Quadrinhos", "category": "Divertidos",
        "description": "Letras de HQ inclinadas e um adesivo “TOP” amarelo.",
        "config": cfg(
            layers=[
                L("hook", "{gancho}", kind="title", fontFamily="bangers", fontSize=84, y=12, uppercase=True,
                  color="#FFFFFF", outlineWidth=8, rotation=-4, letterSpacing=2, animation="pop", boxWidth=88),
                L("sticker", "TOP {numero}", kind="tag", fontFamily="bangers", fontSize=70, x=82, y=23,
                  color="#000000", backgroundEnabled=True, backgroundColor="#FFE600", backgroundPadding=14,
                  rotation=8, animation="pop"),
            ],
            captions=C(fontFamily="bangers", fontSize=94, highlightColor="#FFE600", outlineWidth=6, y=72),
        ),
    },
    {
        "key": "minimalista", "name": "Minimalista", "category": "Clean",
        "description": "Título pequeno e discreto no canto, legendas limpas.",
        "config": cfg(
            layers=[
                L("title", "{titulo}", kind="text", fontFamily="sans", bold=True, fontSize=34, x=6, y=93,
                  align="left", color="#FFFFFF", shadowDepth=3, opacity=95, boxWidth=80),
            ],
            captions=C(fontFamily="sans", fontSize=73, highlightColor="#A78BFA", outlineWidth=4, y=74,
                       uppercase=False, animation="none"),
        ),
    },
    {
        "key": "cinema", "name": "Cinema", "category": "Clean",
        "description": "Vídeo inteiro com tarjas pretas, título serifado e tipografia espaçada.",
        "config": cfg(
            fitMode="contain", backgroundColor="#000000",
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="serif", fontSize=64, y=20, color="#FFFFFF",
                  animation="fade", boxWidth=86),
                L("game", "{jogo}", kind="tag", fontFamily="mono", fontSize=24, y=80, color="#C9AE73",
                  uppercase=True, letterSpacing=10),
            ],
            captions=C(fontFamily="sans", fontSize=65, highlightColor="#C9AE73", outlineWidth=3, y=67,
                       uppercase=False),
        ),
    },
    {
        "key": "moldura-ouro", "name": "Moldura Branca", "category": "Clean",
        "description": "Bordas brancas em volta, título serifado e assinatura.",
        "config": cfg(
            frame=F(sideBorders=True, headerBorder=True, footerBorder=True, color="#FFFFFF",
                    sideWidthPercent=2, headerHeightPercent=10, footerHeightPercent=7),
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="serif", fontSize=48, y=5, color="#1C1917",
                  boxWidth=90),
                L("sign", "@seucanal", kind="tag", fontFamily="mono", bold=True, fontSize=26, y=96.5,
                  color="#1C1917", uppercase=True, letterSpacing=6),
            ],
            captions=C(fontFamily="sans", fontSize=73, highlightColor="#C9AE73", y=74),
        ),
    },
    {
        "key": "pincel", "name": "Story Pincel", "category": "Divertidos",
        "description": "Letra de marcador inclinada e assinatura manuscrita.",
        "config": cfg(
            layers=[
                L("hook", "{gancho}", kind="title", fontFamily="marker", fontSize=64, y=14, color="#FFFFFF",
                  rotation=-3, shadowDepth=5, shadowOpacity=80, animation="slide-up", boxWidth=86),
                L("sign", "@seucanal", kind="tag", fontFamily="pacifico", fontSize=40, x=94, y=92, align="right",
                  color="#FDE68A", shadowDepth=3),
            ],
            captions=C(fontFamily="brush", fontSize=94, highlightColor="#FDE68A", outlineWidth=4, y=72,
                       uppercase=False),
        ),
    },
    {
        "key": "letreiro", "name": "Letreiro Pulsante", "category": "Games",
        "description": "Título em fonte de letreiro que pulsa durante todo o clipe.",
        "config": cfg(
            accentColor="#F97316",
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="bungee", fontSize=56, y=13, color="#F97316",
                  outlineWidth=5, outlineColor="#1C1917", animation="pulse", uppercase=True, boxWidth=90),
                L("score", "NOTA {nota}/100", kind="tag", fontFamily="rubikmono", fontSize=26, y=21, color="#FFFFFF",
                  backgroundEnabled=True, backgroundColor="#1C1917", backgroundOpacity=80, backgroundPadding=10),
            ],
            captions=C(fontFamily="bungee", fontSize=70, highlightColor="#F97316", y=72),
            progressBar=P(color="#F97316", heightPercent=1, position="top"),
        ),
    },
    {
        "key": "feed-quadrado", "name": "Feed Quadrado 1:1", "category": "Formatos",
        "description": "Formato quadrado para feed do Instagram/Facebook com fundo desfocado.",
        "config": cfg(
            aspectRatio="1:1", width=1080, height=1080, fitMode="blur",
            layers=[
                L("title", "{titulo}", kind="title", fontFamily="anton", fontSize=58, y=9, uppercase=True,
                  color="#FFFFFF", outlineWidth=4, boxWidth=92),
            ],
            captions=C(fontFamily="anton", fontSize=68, y=86),
        ),
    },
]


def get_preset(key: str) -> dict | None:
    return next((p for p in PRESETS if p["key"] == key), None)
