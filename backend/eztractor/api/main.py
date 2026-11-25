import json
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..auth import check_password, create_token, password_required, require_auth
from ..config import get_settings
from ..db import get_db, init_db
from ..fonts import catalog as fonts_catalog
from ..models import Clip, Project, ProjectStatus, Template
from ..pipeline.media import MediaError, probe
from ..pipeline.template_render import VARIABLES, normalize, render_preview
from ..presets import PRESETS
from ..pipeline.ranker import ollama_status
from ..queue import enqueue_project, enqueue_project_render, enqueue_render
from ..schemas import (
    ApplyTemplateIn,
    AuthStatusOut,
    CapabilitiesOut,
    ClipOut,
    ClipUpdateIn,
    LoginIn,
    ProjectFromUrlIn,
    ProjectOut,
    ProjectSettings,
    TemplateIn,
    TemplateOut,
    TemplatePreviewIn,
    TokenOut,
)

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".flv", ".avi"}


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    yield


# ---------- arquivos (URLs assinadas, pois <video> não envia header Authorization)
def sign(key: str | None) -> str | None:
    if not key:
        return None
    exp = datetime.now(timezone.utc) + timedelta(hours=6)
    sig = jwt.encode({"k": key, "exp": exp, "p": "file"}, get_settings().jwt_secret, algorithm="HS256")
    return f"/files/{key}?sig={sig}"


def clip_out(c: Clip) -> ClipOut:
    ready = c.render_status == "ready"
    return ClipOut(
        id=c.id, start_s=c.start_s, end_s=c.end_s, score=c.score, title=c.title, hook=c.hook,
        reason=c.reason, render_status=c.render_status, ranker=(c.signals or {}).get("ranker", "heuristic"),
        video_url=sign(c.render_key) if ready else None,
        thumb_url=sign(c.thumb_key) if ready else None,
    )


def project_out(p: Project, with_clips: bool = True) -> ProjectOut:
    return ProjectOut(
        id=p.id, title=p.title, source_type=p.source_type, source_url=p.source_url,
        duration_s=p.duration_s, status=p.status, stage=p.stage, progress=p.progress, error=p.error,
        settings=p.settings or {}, created_at=p.created_at,
        clips=[clip_out(c) for c in p.clips] if with_clips else [],
    )


def resolve_settings(db: Session, settings: ProjectSettings) -> dict:
    """Valida o template escolhido; se nenhum foi informado, usa o template padrão (se houver)."""
    data = settings.model_dump()
    if "template_id" not in settings.model_fields_set:
        default = db.scalar(select(Template).where(Template.is_default.is_(True)))
        data["template_id"] = default.id if default else None
    elif data["template_id"] and db.get(Template, data["template_id"]) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "template não encontrado")
    return data


def template_out(t: Template) -> TemplateOut:
    return TemplateOut(id=t.id, name=t.name, config=normalize(t.config), is_default=t.is_default,
                       created_at=t.created_at, updated_at=t.updated_at)


def get_project_or_404(db: Session, project_id: str) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "projeto não encontrado")
    return p


# Rotas protegidas pela senha (se configurada)
api = APIRouter(dependencies=[Depends(require_auth)])


@api.get("/capabilities", response_model=CapabilitiesOut)
def capabilities():
    """Quais métodos de análise estão disponíveis agora (para o formulário do front)."""
    return CapabilitiesOut(
        default_ranker=get_settings().ranker,
        claude_configured=bool(os.environ.get("ANTHROPIC_API_KEY")),
        ollama=ollama_status(),
    )


@api.post("/projects/url", response_model=ProjectOut, status_code=201)
def create_from_url(body: ProjectFromUrlIn, db: Session = Depends(get_db)):
    p = Project(title=body.title or body.url, source_type="url", source_url=body.url,
                settings=resolve_settings(db, body.settings))
    db.add(p)
    db.commit()
    enqueue_project(p.id)
    db.refresh(p)
    return project_out(p)


@api.post("/projects/upload", response_model=ProjectOut, status_code=201)
def create_from_upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    settings: str = Form("{}"),
    db: Session = Depends(get_db),
):
    try:
        parsed = ProjectSettings.model_validate(json.loads(settings or "{}"))
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"configurações inválidas: {e}") from None
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"formato não suportado: {ext or '?'}")

    p = Project(title=title or (file.filename or "Upload"), source_type="upload", settings=resolve_settings(db, parsed))
    db.add(p)
    db.flush()
    key = f"{storage.project_dir(p.id)}/source{ext}"
    dest = storage.path_for(key)
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    written = 0
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                db.rollback()
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "arquivo muito grande")
            out.write(chunk)
    p.source_key = key
    db.commit()
    enqueue_project(p.id)
    db.refresh(p)
    return project_out(p)


@api.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.created_at.desc()))
    return [project_out(p, with_clips=False) for p in rows]


@api.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    return project_out(get_project_or_404(db, project_id))


@api.post("/projects/{project_id}/reprocess", response_model=ProjectOut)
def reprocess(project_id: str, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    if p.status in (ProjectStatus.queued.value, ProjectStatus.processing.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "projeto já está em processamento")
    p.status, p.stage, p.progress, p.error = ProjectStatus.queued.value, "", 0, None
    db.commit()
    enqueue_project(p.id)
    return project_out(p)


@api.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    if p.status == ProjectStatus.processing.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "aguarde o processamento terminar")
    db.delete(p)
    db.commit()
    shutil.rmtree(storage.path_for(storage.project_dir(project_id)), ignore_errors=True)


@api.patch("/clips/{clip_id}", response_model=ClipOut)
def update_clip(clip_id: str, body: ClipUpdateIn, db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clipe não encontrado")
    start = body.start_s if body.start_s is not None else clip.start_s
    end = body.end_s if body.end_s is not None else clip.end_s
    duration = clip.project.duration_s or end
    if not (0 <= start < end <= duration) or end - start > 180:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "intervalo inválido (máx. 180s)")
    needs_render = (start, end) != (clip.start_s, clip.end_s) or (body.hook is not None and body.hook != clip.hook)
    clip.start_s, clip.end_s = start, end
    if body.title is not None:
        clip.title = body.title
    if body.hook is not None:
        clip.hook = body.hook
    if needs_render:
        clip.render_status = "pending"
    db.commit()
    if needs_render:
        enqueue_render(clip.id)
        db.refresh(clip)
    return clip_out(clip)


# ---------- templates
@api.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    rows = db.scalars(select(Template).order_by(Template.is_default.desc(), Template.updated_at.desc()))
    return [template_out(t) for t in rows]


def _set_default(db: Session, tpl: Template, is_default: bool) -> None:
    if is_default:
        for other in db.scalars(select(Template).where(Template.is_default.is_(True), Template.id != tpl.id)):
            other.is_default = False
    tpl.is_default = is_default


@api.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateIn, db: Session = Depends(get_db)):
    tpl = Template(name=body.name, config=body.config.model_dump())
    db.add(tpl)
    db.flush()
    _set_default(db, tpl, body.is_default)
    db.commit()
    return template_out(tpl)


@api.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: str, body: TemplateIn, db: Session = Depends(get_db)):
    tpl = db.get(Template, template_id)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template não encontrado")
    tpl.name, tpl.config = body.name, body.config.model_dump()
    _set_default(db, tpl, body.is_default)
    db.commit()
    return template_out(tpl)


@api.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: str, db: Session = Depends(get_db)):
    tpl = db.get(Template, template_id)
    if tpl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template não encontrado")
    db.delete(tpl)
    db.commit()


@api.get("/template-presets")
def template_presets():
    """Galeria de estilos prontos."""
    return PRESETS


@api.get("/template-options")
def template_options():
    """Fontes e variáveis disponíveis para o editor."""
    return {"fonts": fonts_catalog(), "variables": VARIABLES}


@api.post("/templates/preview", responses={200: {"content": {"image/jpeg": {}}}})
def preview_template(body: TemplatePreviewIn, db: Session = Depends(get_db)):
    """Renderiza um quadro com o mesmo motor do vídeo final (sobre um vídeo seu, se informado)."""
    src = None
    w, h, at = 1920, 1080, 0.0
    if body.project_id:
        p = get_project_or_404(db, body.project_id)
        if p.source_key and storage.path_for(p.source_key).exists():
            src = storage.path_for(p.source_key)
            try:
                info = probe(src)
            except MediaError as e:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
            w, h = info.width, info.height
            best = p.clips[0] if p.clips else None
            at = best.start_s if best else min(30.0, info.duration_s / 2)
    with tempfile.TemporaryDirectory(prefix="ezt-prev-") as tmp:
        out = Path(tmp) / "preview.jpg"
        try:
            render_preview(body.config.model_dump(), out, tmp, src=src, src_w=w, src_h=h, at_s=at)
        except MediaError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"falha ao gerar prévia: {e}") from None
        return Response(out.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@api.post("/projects/{project_id}/apply-template", response_model=ProjectOut)
def apply_template(project_id: str, body: ApplyTemplateIn, db: Session = Depends(get_db)):
    """Troca o template do projeto e renderiza de novo todos os clipes."""
    p = get_project_or_404(db, project_id)
    if p.status in (ProjectStatus.queued.value, ProjectStatus.processing.value):
        raise HTTPException(status.HTTP_409_CONFLICT, "aguarde o processamento terminar")
    if body.template_id and db.get(Template, body.template_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template não encontrado")
    p.settings = {**(p.settings or {}), "template_id": body.template_id}
    for c in p.clips:
        c.render_status = "pending"
    db.commit()
    enqueue_project_render(p.id)
    db.refresh(p)
    return project_out(p)


def create_app() -> FastAPI:
    app = FastAPI(title="EzTractor API", version="0.2.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/auth/status", response_model=AuthStatusOut)
    def auth_status():
        return AuthStatusOut(password_required=password_required())

    @app.post("/auth/login", response_model=TokenOut)
    def login(body: LoginIn):
        if password_required() and not check_password(body.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "senha incorreta")
        return TokenOut(token=create_token())

    @app.get("/files/{key:path}")
    def get_file(key: str, sig: str):
        try:
            data = jwt.decode(sig, get_settings().jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link inválido ou expirado") from None
        if data.get("p") != "file" or data.get("k") != key:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link inválido")
        path = storage.path_for(key)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "arquivo não encontrado")
        return FileResponse(path)

    app.include_router(api)

    # Site estático (Next.js exportado). Montado por último para não encobrir as rotas da API.
    web_dir = get_settings().web_dir
    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


app = create_app()
