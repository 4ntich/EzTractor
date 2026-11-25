from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class LoginIn(BaseModel):
    password: str


class TokenOut(BaseModel):
    token: str


class AuthStatusOut(BaseModel):
    password_required: bool


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
    video_url: str | None = None
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
    created_at: datetime
    clips: list[ClipOut] = []


class ClipUpdateIn(BaseModel):
    start_s: float | None = None
    end_s: float | None = None
    title: str | None = Field(None, max_length=200)
    hook: str | None = Field(None, max_length=200)

