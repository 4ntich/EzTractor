from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class LoginIn(BaseModel):
    password: str


class TokenOut(BaseModel):
    token: str


class AuthStatusOut(BaseModel):
    password_required: bool


class OllamaStatus(BaseModel):
    online: bool
    model: str
    model_ready: bool


class CapabilitiesOut(BaseModel):
    default_ranker: str
    default_render_height: int
    claude_configured: bool
    ollama: OllamaStatus


# lado maior do vídeo final -> rótulo (9:16: 640 = 360x640 … 3840 = 2160x3840)
RENDER_QUALITIES = {640: "360p", 854: "480p", 1280: "720p", 1920: "1080p", 2560: "1440p", 3840: "2160p (4K)"}


class FacecamRect(BaseModel):
    """Retângulo normalizado (0..1) da webcam no vídeo original."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class ProjectSettings(BaseModel):
    clip_min_s: int = Field(15, ge=5, le=180)
    clip_max_s: int = Field(45, ge=5, le=180)
    max_clips: int = Field(8, ge=1, le=30)
    language: str | None = None  # None = autodetectar
    layout: str = Field("crop", pattern="^(crop|split|fit)$")
    facecam: FacecamRect | None = None
    game: str = ""
    captions: bool = True
    # None = usa o padrão do servidor (EZT_RANKER)
    ranker: str | None = Field(None, pattern="^(heuristic|ollama|claude)$")
    # Template visual. Se o campo não for enviado, usa o template marcado como padrão.
    template_id: str | None = None
    # "clips" = gerar cortes com IA | "download" = só baixar o vídeo (com ou sem template)
    mode: str = Field("clips", pattern="^(clips|download)$")
    # altura máxima ao baixar de um link (0 = melhor disponível)
    download_height: int = Field(1080)
    # pular propaganda, pedidos de inscrição e finais de vídeo
    skip_ads: bool = True
    # qualidade do vídeo final (lado maior em px). None = padrão do app (EZT_RENDER_HEIGHT)
    render_height: int | None = None

    @field_validator("download_height")
    @classmethod
    def _height(cls, v: int) -> int:
        if v not in (0, 2160, 1440, 1080, 720, 480, 360):
            raise ValueError("qualidade inválida")
        return v

    @field_validator("render_height")
    @classmethod
    def _render_height(cls, v: int | None) -> int | None:
        if v is not None and v not in RENDER_QUALITIES:
            raise ValueError("qualidade de saída inválida")
        return v

    @model_validator(mode="after")
    def _check(self):
        if self.clip_max_s < self.clip_min_s:
            raise ValueError("clip_max_s deve ser >= clip_min_s")
        if self.layout == "split" and self.facecam is None:
            raise ValueError("layout 'split' exige o retângulo 'facecam'")
        return self


class ProjectFromUrlIn(BaseModel):
    url: str
    title: str = ""
    settings: ProjectSettings = ProjectSettings()

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL deve começar com http(s)://")
        return v


class ClipOut(BaseModel):
    id: str
    start_s: float
    end_s: float
    score: int
    title: str
    hook: str
    reason: str
    render_status: str
    ranker: str = "heuristic"
    video_url: str | None = None
    download_url: str | None = None  # mesmo vídeo, salvo com o título do clipe
    cuts: list[list[float]] = []
    thumb_url: str | None = None


class ProjectOut(BaseModel):
    id: str
    title: str
    source_type: str
    source_url: str | None
    duration_s: float | None
    status: str
    stage: str
    progress: int
    error: str | None
    settings: dict
    control: str = "run"
    source_file_url: str | None = None  # vídeo original (para baixar)
    skip_segments: list[dict] = []
    created_at: datetime
    clips: list[ClipOut] = []


class ClipUpdateIn(BaseModel):
    start_s: float | None = None
    end_s: float | None = None
    cuts: list[list[float]] | None = Field(None, max_length=200)
    title: str | None = Field(None, max_length=200)
    hook: str | None = Field(None, max_length=200)



# ---------------------------------------------------------------- templates
HEX = r"^#[0-9A-Fa-f]{6}$"

ANIMATIONS = "^(none|fade|pop|slide-up|slide-down|slide-left|typewriter|pulse|zoom-in)$"


class TemplateLayer(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    kind: str = Field("text", pattern="^(title|text|tag)$")
    # Aceita variáveis preenchidas em cada clipe: {titulo} {gancho} {jogo} {numero} {total} {nota} {projeto} {data}
    text: str = Field("", max_length=300)
    x: float = Field(50, ge=0, le=100)  # % da largura (âncora conforme o alinhamento)
    y: float = Field(50, ge=0, le=100)  # % da altura (centro vertical do bloco)
    boxWidth: float = Field(84, ge=10, le=100)  # largura máxima antes de quebrar linha (% da tela)
    fontSize: float = Field(32, ge=6, le=400)  # px na largura do template
    color: str = Field("#F1EBDD", pattern=HEX)
    opacity: float = Field(100, ge=0, le=100)
    align: str = Field("center", pattern="^(left|center|right)$")
    bold: bool = False
    italic: bool = False
    uppercase: bool = False
    letterSpacing: float = Field(0, ge=-10, le=60)  # px
    rotation: float = Field(0, ge=-45, le=45)  # graus
    fontFamily: str = "sans"
    # efeitos
    outlineWidth: float = Field(0, ge=0, le=30)
    outlineColor: str = Field("#000000", pattern=HEX)
    shadowDepth: float = Field(0, ge=0, le=30)
    shadowColor: str = Field("#000000", pattern=HEX)
    shadowOpacity: float = Field(60, ge=0, le=100)
    glow: bool = False  # brilho neon (desfoca o contorno)
    backgroundEnabled: bool = False  # caixa atrás do texto (desativa o contorno)
    backgroundColor: str = Field("#252522", pattern=HEX)
    backgroundOpacity: float = Field(100, ge=0, le=100)
    backgroundPadding: float = Field(12, ge=0, le=60)
    # animação e tempo
    animation: str = Field("none", pattern=ANIMATIONS)
    showMode: str = Field("always", pattern="^(always|start|end)$")
    showSeconds: float = Field(3, ge=0.5, le=60)

    @field_validator("fontFamily")
    @classmethod
    def _font(cls, v: str) -> str:
        from .fonts import FONTS

        if v not in FONTS:
            raise ValueError(f"fonte desconhecida: {v}")
        return v


class TemplateFrame(BaseModel):
    sideBorders: bool = False
    headerBorder: bool = False
    footerBorder: bool = False
    color: str = Field("#FFFFFF", pattern=HEX)
    sideWidthPercent: float = Field(5, ge=0.1, le=45)
    headerHeightPercent: float = Field(8, ge=0.1, le=45)
    footerHeightPercent: float = Field(8, ge=0.1, le=45)


class TemplateCaptions(BaseModel):
    """Estilo das legendas automáticas (fala transcrita) quando o template é usado."""

    fontFamily: str = "anton"
    fontSize: float = Field(84, ge=10, le=200)
    color: str = Field("#FFFFFF", pattern=HEX)
    highlightColor: str = Field("#FFE600", pattern=HEX)
    outlineColor: str = Field("#000000", pattern=HEX)
    outlineWidth: float = Field(5, ge=0, le=20)
    y: float = Field(72, ge=5, le=95)  # % da altura
    uppercase: bool = True
    wordsPerLine: int = Field(3, ge=1, le=8)
    animation: str = Field("pop", pattern="^(none|pop)$")  # palavra atual "pula"

    @field_validator("fontFamily")
    @classmethod
    def _font(cls, v: str) -> str:
        from .fonts import FONTS

        if v not in FONTS:
            raise ValueError(f"fonte desconhecida: {v}")
        return v


class TemplateProgressBar(BaseModel):
    enabled: bool = False
    color: str = Field("#C9AE73", pattern=HEX)
    heightPercent: float = Field(0.8, ge=0.2, le=5)
    position: str = Field("bottom", pattern="^(top|bottom)$")


class TemplateConfig(BaseModel):
    aspectRatio: str = Field("9:16", max_length=10)
    width: int = Field(1080, ge=240, le=3840)
    height: int = Field(1920, ge=240, le=3840)
    fitMode: str = Field("cover", pattern="^(cover|contain|blur)$")
    videoZoom: float = Field(100, ge=50, le=200)  # % (zoom no vídeo dentro da tela)
    backgroundColor: str = Field("#252522", pattern=HEX)
    accentColor: str = Field("#C9AE73", pattern=HEX)
    layoutPreset: str = Field("free", max_length=30)
    vignette: bool = False
    frame: TemplateFrame = TemplateFrame()
    captions: TemplateCaptions = TemplateCaptions()
    progressBar: TemplateProgressBar = TemplateProgressBar()
    layers: list[TemplateLayer] = Field(default_factory=list, max_length=10)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    config: TemplateConfig
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("dê um nome ao template")
        return v


class TemplateOut(BaseModel):
    id: str
    name: str
    config: TemplateConfig
    is_default: bool
    created_at: datetime
    updated_at: datetime


class TemplatePreviewIn(BaseModel):
    config: TemplateConfig
    project_id: str | None = None  # usa um quadro desse projeto como fundo


class ApplyTemplateIn(BaseModel):
    template_id: str | None = None  # None = remover template
