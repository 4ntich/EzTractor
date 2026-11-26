import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    paused = "paused"
    cancelled = "cancelled"
    ready = "ready"
    failed = "failed"


ACTIVE_STATUSES = (ProjectStatus.queued.value, ProjectStatus.processing.value, ProjectStatus.paused.value)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(20))  # upload | url
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(255), nullable=True)  # caminho no storage
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.queued.value, index=True)
    stage: Mapped[str] = mapped_column(String(40), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pedido do usuário para o processamento em andamento: run | pause | cancel (ver control.py)
    control: Mapped[str] = mapped_column(String(10), default="run", server_default="run")
    # settings: clip_min_s, clip_max_s, max_clips, language, layout, facecam{x,y,w,h}, game, captions
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    transcript: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [{w,start,end}]
    # trechos a pular (propaganda, inscrição, final): [{start,end,category,reason,source}]
    skip_segments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    youtube_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # sinais da audiência (só vídeos do YouTube): {"heatmap": [...], "chat": {msgs, fun, total}, "channel": [...]}
    audience: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    clips: Mapped[list["Clip"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Clip.score.desc()"
    )


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    score: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    hook: Mapped[str] = mapped_column(String(200), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    signals: Mapped[dict] = mapped_column(JSON, default=dict)
    cuts: Mapped[list | None] = mapped_column(JSON, nullable=True)  # trechos removidos: [[ini, fim], ...] absolutos
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)  # legenda para postar (None = gerar na hora)
    hashtags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    render_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumb_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    render_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|ready|failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    project: Mapped[Project] = relationship(back_populates="clips")


class Template(Base):
    """Modelo visual (formato, moldura e camadas de texto) aplicado aos clipes."""

    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(60))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
