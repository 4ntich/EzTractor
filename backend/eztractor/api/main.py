import json
import os
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import jwt
from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from .. import system, updater
from ..auth import check_password, create_token, is_local, password_required, require_auth
from ..config import get_settings
from ..db import get_db, init_db
from ..fonts import catalog as fonts_catalog
from ..models import ACTIVE_STATUSES, Clip, Project, ProjectStatus, Template
from ..pipeline.media import MediaError, probe
from ..pipeline.social import dominant_signal, make_caption, make_hashtags, normalize_hashtags, social_text
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
    recover_interrupted()
    yield


def recover_interrupted() -> None:
    """No modo inline o processamento roda dentro do app: se ele foi fechado no meio, o trabalho
    morreu junto. Marca esses projetos para o usuário reprocessar (em vez de ficarem "rodando" para sempre)."""
    if get_settings().queue_mode != "inline":
        return
    from ..db import session_factory

    with session_factory()() as db:
        for p in db.scalars(select(Project).where(Project.status.in_(ACTIVE_STATUSES))):
            p.status, p.control = ProjectStatus.failed.value, "run"
            p.error = "Interrompido: o EzTractor foi fechado durante o processamento. Clique em Reprocessar."
        db.commit()


# ---------- arquivos (URLs assinadas, pois <video> não envia header Authorization)
def sign(key: str | None, download_name: str | None = None) -> str | None:
    if not key:
        return None
    exp = datetime.now(timezone.utc) + timedelta(hours=6)
    sig = jwt.encode({"k": key, "exp": exp, "p": "file"}, get_settings().jwt_secret, algorithm="HS256")
    url = f"/files/{key}?sig={sig}"
    if download_name:
        url += "&dl=" + quote(download_name)
    return url


def safe_filename(title: str, ext: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or "")
    name = re.sub(r"\s+", " ", name).strip(" .")[:120] or "video"
    return f"{name}{ext}"


def clip_social(c: Clip) -> tuple[str, list[str]]:
    """Legenda e hashtags do clipe; clipes antigos (sem legenda salva) ganham a gerada na hora."""
    st = (c.project.settings or {}) if c.project else {}
    game, lang = st.get("game", ""), st.get("language")
    caption = c.caption if c.caption is not None else make_caption(
        c.title or "", c.hook or "", game, lang, dominant_signal(c.signals))
    tags = c.hashtags if c.hashtags is not None else make_hashtags(game, lang)
    return caption, tags


def clip_out(c: Clip) -> ClipOut:
    ready = c.render_status == "ready"
    caption, tags = clip_social(c)
    return ClipOut(
        id=c.id, start_s=c.start_s, end_s=c.end_s, score=c.score, title=c.title, hook=c.hook,
        reason=c.reason, render_status=c.render_status, ranker=(c.signals or {}).get("ranker", "heuristic"),
        video_url=sign(c.render_key) if ready else None,
        download_url=sign(c.render_key, safe_filename(c.title or "clipe", Path(c.render_key).suffix)) if ready else None,
        cuts=c.cuts or [],
        thumb_url=sign(c.thumb_key) if ready else None,
        caption=caption, hashtags=tags, social_text=social_text(caption, tags),
    )


def project_out(p: Project, with_clips: bool = True) -> ProjectOut:
    return ProjectOut(
        id=p.id, title=p.title, source_type=p.source_type, source_url=p.source_url,
        duration_s=p.duration_s, status=p.status, stage=p.stage, progress=p.progress, error=p.error,
        settings=p.settings or {}, control=p.control or "run", created_at=p.created_at,
        skip_segments=p.skip_segments or [],
        source_file_url=sign(p.source_key, safe_filename(p.title, Path(p.source_key).suffix))
        if p.source_key and storage.path_for(p.source_key).exists() else None,
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
        default_render_height=get_settings().render_height,
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


@api.get("/projects/{project_id}/download-all")
def download_all_link(project_id: str, db: Session = Depends(get_db)):
    """Link assinado para baixar todos os clipes prontos num .zip (o navegador não envia o login no download)."""
    p = get_project_or_404(db, project_id)
    ready = [c for c in p.clips if c.render_status == "ready" and c.render_key and storage.path_for(c.render_key).exists()]
    if not ready:
        raise HTTPException(status.HTTP_409_CONFLICT, "nenhum clipe pronto para baixar")
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    sig = jwt.encode({"k": p.id, "exp": exp, "p": "zip"}, get_settings().jwt_secret, algorithm="HS256")
    return {"url": f"/zips/{p.id}?sig={sig}", "count": len(ready)}


def build_clips_zip(p: Project, dst: Path) -> int:
    """Clipes prontos, na ordem do ranking: '01 - Título.mp4'. Sem compressão (vídeo já é comprimido)."""
    import zipfile

    used: set[str] = set()
    n = 0
    with zipfile.ZipFile(dst, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
        for i, c in enumerate(p.clips, start=1):
            if c.render_status != "ready" or not c.render_key:
                continue
            src = storage.path_for(c.render_key)
            if not src.exists():
                continue
            name = safe_filename(f"{i:02d} - {c.title or 'clipe'}", src.suffix)
            stem, k = name, 2
            while name.lower() in used:  # títulos repetidos
                name = f"{Path(stem).stem} ({k}){src.suffix}"
                k += 1
            used.add(name.lower())
            z.write(src, arcname=name)
            # legenda + hashtags prontas, com o mesmo nome do vídeo (BOM: o Bloco de Notas abre emojis certinho)
            z.writestr(str(Path(name).with_suffix(".txt")), "\ufeff" + social_text(*clip_social(c)) + "\n")
            n += 1
    return n


@api.post("/projects/{project_id}/reprocess", response_model=ProjectOut)
def reprocess(project_id: str, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    if p.status in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "projeto já está em processamento")
    p.status, p.stage, p.progress, p.error, p.control = ProjectStatus.queued.value, "", 0, None, "run"
    db.commit()
    enqueue_project(p.id)
    return project_out(p)


@api.post("/projects/{project_id}/pause", response_model=ProjectOut)
def pause_project(project_id: str, db: Session = Depends(get_db)):
    """Pausa o processamento (o ffmpeg/download/transcrição param onde estão)."""
    p = get_project_or_404(db, project_id)
    if p.status not in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "o projeto não está em processamento")
    p.control = "pause"
    db.commit()
    return project_out(p)


@api.post("/projects/{project_id}/resume", response_model=ProjectOut)
def resume_project(project_id: str, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    if p.control != "pause":
        raise HTTPException(status.HTTP_409_CONFLICT, "o projeto não está pausado")
    p.control = "run"
    db.commit()
    return project_out(p)


@api.post("/projects/{project_id}/cancel", response_model=ProjectOut)
def cancel_project(project_id: str, db: Session = Depends(get_db)):
    """Cancela o processamento. Clipes já prontos são mantidos; dá para reprocessar depois."""
    p = get_project_or_404(db, project_id)
    if p.status not in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "o projeto não está em processamento")
    p.control = "cancel"
    db.commit()
    return project_out(p)


@api.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    p = get_project_or_404(db, project_id)
    if p.status in ACTIVE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "cancele o processamento antes de excluir")
    db.delete(p)
    db.commit()
    shutil.rmtree(storage.path_for(storage.project_dir(project_id)), ignore_errors=True)


@api.patch("/clips/{clip_id}", response_model=ClipOut)
def update_clip(clip_id: str, body: ClipUpdateIn, db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "clipe não encontrado")
    if clip.project.status in ACTIVE_STATUSES or clip.render_status == "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "aguarde a renderização atual terminar")
    start = body.start_s if body.start_s is not None else clip.start_s
    end = body.end_s if body.end_s is not None else clip.end_s
    duration = clip.project.duration_s or end
    whole_video = (clip.project.settings or {}).get("mode") == "download"
    if not (0 <= start < end <= duration + 0.05):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "início/fim inválidos")
    cuts = clip.cuts or []
    if body.cuts is not None:
        cuts = []
        for c in sorted(body.cuts, key=lambda c: c[0] if c else 0):
            if len(c) != 2 or not (start <= c[0] < c[1] <= end):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "corte fora do trecho do vídeo")
            if cuts and c[0] < cuts[-1][1]:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "cortes sobrepostos")
            cuts.append([round(c[0], 2), round(c[1], 2)])
    cuts = [c for c in cuts if c[0] >= start and c[1] <= end]  # aparar pode descartar cortes de fora
    final = (end - start) - sum(b - a for a, b in cuts)
    if final < 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "o vídeo precisa ter pelo menos 1 segundo")
    if not whole_video and final > 180:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "clipes podem ter no máximo 180 s")
    needs_render = ((start, end) != (clip.start_s, clip.end_s) or cuts != (clip.cuts or [])
                    or (body.hook is not None and body.hook != clip.hook))
    clip.start_s, clip.end_s, clip.cuts = start, end, cuts
    if body.title is not None:
        clip.title = body.title
    if body.hook is not None:
        clip.hook = body.hook
    if body.caption is not None:
        clip.caption = body.caption.strip()
    if body.hashtags is not None:
        clip.hashtags = normalize_hashtags(body.hashtags)
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
    # ignore_cleanup_errors: no Windows o antivirus/handle pode segurar o .jpg recem-criado
    # e a falha de limpeza derrubava uma previa que ja tinha dado certo (erro intermitente).
    with tempfile.TemporaryDirectory(prefix="ezt-prev-", ignore_cleanup_errors=True) as tmp:
        out = Path(tmp) / "preview.jpg"
        try:
            render_preview(body.config.model_dump(), out, tmp, src=src, src_w=w, src_h=h, at_s=at,
                           captions=body.captions)
        except MediaError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"falha ao gerar prévia: {e}") from None
        return Response(out.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@api.post("/projects/{project_id}/apply-template", response_model=ProjectOut)
def apply_template(project_id: str, body: ApplyTemplateIn, db: Session = Depends(get_db)):
    """Troca o template do projeto e renderiza de novo todos os clipes."""
    p = get_project_or_404(db, project_id)
    if p.status in ACTIVE_STATUSES:
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


# ---------- sistema: versão, atualização, acesso pelo celular
def _local_only(request: Request) -> None:
    if not is_local(request):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "só pode ser alterado no computador onde o EzTractor está instalado")


@api.get("/system/info")
def system_info(request: Request):
    s = get_settings()
    return {"version": s.app_version, "can_update": updater.can_install(), "can_restart": system.can_restart(),
            "is_local": is_local(request), "lan": system.lan_info()}


@api.get("/system/update")
def check_update(force: bool = False):
    return {**updater.state(), **updater.latest(force=force)}


@api.post("/system/update/install")
def install_update(request: Request):
    _local_only(request)
    try:
        return updater.install()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None


@api.get("/system/update/progress")
def update_progress():
    return updater.state()


class LanIn(BaseModel):
    enabled: bool
    password: str | None = None


@api.post("/system/lan")
def set_lan(body: LanIn, request: Request):
    _local_only(request)
    s = get_settings()
    values = {"EZT_LAN_ACCESS": "1" if body.enabled else "0"}
    new_password = False
    if body.password:
        if len(body.password) < 6:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "a senha precisa ter pelo menos 6 caracteres")
        values["EZT_APP_PASSWORD"] = body.password
        new_password = body.password != s.app_password
    elif body.enabled and not s.app_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "defina uma senha para o acesso pelo celular")
    try:
        system.apply_config(values)
        if new_password or not body.enabled:  # quem entrou com a senha antiga (ou com o acesso ligado) sai
            system.end_sessions()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return {"saved": True, "restart_required": system.lan_info()["restart_required"]}


@api.delete("/system/lan/password")
def delete_lan_password(request: Request):
    """Apaga a senha. Sem senha o celular não pode entrar, então o acesso pela rede também é desligado."""
    _local_only(request)
    try:
        system.apply_config({"EZT_APP_PASSWORD": "", "EZT_LAN_ACCESS": "0"})
        system.end_sessions()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return system.lan_info()


@api.post("/system/lan/disconnect")
def disconnect_devices(request: Request):
    """Encerra a conexão de todos os aparelhos (eles precisam entrar de novo com a senha)."""
    _local_only(request)
    try:
        system.end_sessions()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return system.lan_info()


@api.post("/system/restart")
def restart_app(request: Request):
    _local_only(request)
    try:
        system.restart()
    except RuntimeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return {"restarting": True}


@api.get("/system/qr.svg")
def qr(data: str):
    if len(data) > 300:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "texto longo demais")
    return Response(system.qr_svg(data), media_type="image/svg+xml")


_BLOCKED_PAGE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>EzTractor</title></head>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#04232a;color:#e6f4f6;
font-family:system-ui,sans-serif;padding:24px;text-align:center"><div><div style="font-size:42px">🔒</div>
<h1 style="font-size:20px;margin:12px 0 8px">{msg}</h1>
<p style="color:#8fb3ba;font-size:14px">Para usar pelo celular, ligue o acesso na página “Celular” do EzTractor no computador.</p>
</div></body></html>"""


def create_app() -> FastAPI:
    app = FastAPI(title="EzTractor API", version="0.2.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def lan_guard(request: Request, call_next):
        """App instalado: outros aparelhos só entram com o acesso pela rede ligado E senha definida.
        Vale na hora (desligar/excluir a senha não precisa reiniciar)."""
        s = get_settings()
        if s.config_file and not is_local(request) and not (s.lan_access and s.app_password):
            msg = "O acesso pelo celular está desligado no computador."
            if "text/html" in request.headers.get("accept", ""):  # abriu o endereço no navegador
                return HTMLResponse(_BLOCKED_PAGE.replace("{msg}", msg), status_code=403, headers={"Cache-Control": "no-store"})
            return JSONResponse({"detail": msg}, status_code=403)
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/auth/status", response_model=AuthStatusOut)
    def auth_status(request: Request):
        trusted = get_settings().trust_localhost and is_local(request)
        return AuthStatusOut(password_required=password_required() and not trusted)

    @app.post("/auth/login", response_model=TokenOut)
    def login(body: LoginIn):
        if password_required() and not check_password(body.password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "senha incorreta")
        return TokenOut(token=create_token())

    @app.get("/files/{key:path}")
    def get_file(key: str, sig: str, dl: str | None = None):
        try:
            data = jwt.decode(sig, get_settings().jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link inválido ou expirado") from None
        if data.get("p") != "file" or data.get("k") != key:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link inválido")
        path = storage.path_for(key)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "arquivo não encontrado")
        if dl:  # botão "baixar": salva com o nome do vídeo
            return FileResponse(path, filename=dl)
        return FileResponse(path)

    @app.get("/zips/{project_id}")
    def get_zip(project_id: str, sig: str, db: Session = Depends(get_db)):
        try:
            data = jwt.decode(sig, get_settings().jwt_secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link inválido ou expirado") from None
        if data.get("p") != "zip" or data.get("k") != project_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "link inválido")
        p = get_project_or_404(db, project_id)
        tmp_dir = Path(tempfile.mkdtemp(prefix="ezt-zip-"))
        out = tmp_dir / "clipes.zip"
        if not build_clips_zip(p, out):
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status.HTTP_404_NOT_FOUND, "nenhum clipe pronto para baixar")
        return FileResponse(out, filename=safe_filename(f"{p.title or 'projeto'} - clipes", ".zip"),
                            media_type="application/zip",
                            background=BackgroundTask(shutil.rmtree, tmp_dir, ignore_errors=True))

    app.include_router(api)

    # Site estático (Next.js exportado). Montado por último para não encobrir as rotas da API.
    web_dir = get_settings().web_dir
    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


app = create_app()
