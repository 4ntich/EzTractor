"""Orquestra o processamento de um projeto. Executado pelo worker (RQ) ou numa thread (modo inline)."""

import logging
import shutil
import tempfile
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..config import get_settings
from ..db import session_factory
from ..control import Cancelled, Control, activate, checkpoint
from ..control import _current as _control_var
from ..models import ACTIVE_STATUSES, Clip, Project, ProjectStatus, Template
from . import candidates as cand_mod
from . import ranker, signals
from .captions import build_ass, write_ass
from .ingest import download_url
from .media import extract_audio, probe, thumbnail
from .render import RenderSpec, render_clip
from .template_render import build_template_ass, clip_context, normalize, template_spec
from .transcribe import transcribe

log = logging.getLogger(__name__)


def reset_control(token) -> None:
    _control_var.reset(token)


def _update(db: Session, project: Project, *, stage: str | None = None, progress: int | None = None, **kw) -> None:
    if stage is not None:
        project.stage = stage
    if progress is not None:
        project.progress = progress
    for k, v in kw.items():
        setattr(project, k, v)
    db.commit()


def _source_path(project: Project) -> Path:
    assert project.source_key
    return storage.path_for(project.source_key)


def _template_config(db: Session, project: Project) -> dict | None:
    tid = (project.settings or {}).get("template_id")
    if not tid:
        return None
    tpl = db.get(Template, tid)
    if tpl is None:
        log.warning("template %s do projeto %s não existe mais; renderizando sem template", tid, project.id)
        return None
    return normalize(tpl.config)


def _render(db: Session, project: Project, clip: Clip, workdir: Path, on_progress=None) -> None:
    st = project.settings or {}
    max_side = int(st.get("render_height") or get_settings().render_height)
    cfg = _template_config(db, project)
    if cfg is not None:
        # consulta o banco: durante o processamento `project.clips` ainda não tem os clipes recém-criados
        db.flush()
        ranked = list(db.scalars(select(Clip).where(Clip.project_id == project.id)
                                 .order_by(Clip.score.desc(), Clip.start_s)))
        rank = next((i + 1 for i, c in enumerate(ranked) if c.id == clip.id), 1)
        spec = template_spec(cfg, clip.start_s, clip.end_s, max_side, st.get("layout", "crop"), st.get("facecam"))
        ass = build_template_ass(cfg, project.transcript or [], clip.start_s, clip.end_s,
                                 clip_context(clip, project, len(ranked), rank), captions=st.get("captions", True))
    else:
        spec = RenderSpec(
            start=clip.start_s, end=clip.end_s, height=max_side,
            layout=st.get("layout", "crop"), facecam=st.get("facecam"),
        )
        ass = build_ass(
            project.transcript or [], clip.start_s, clip.end_s, spec.width, spec.height,
            hook=clip.hook, captions=st.get("captions", True),
        )
    spec.ass_path = write_ass(workdir / f"{clip.id}.ass", ass)

    base = f"{storage.project_dir(project.id)}/clips/{clip.id}"
    video_key, thumb_key = f"{base}.mp4", f"{base}.jpg"
    src = _source_path(project)
    info = probe(src)
    out = render_clip(src, storage.path_for(video_key), spec, info.width, info.height, info.has_audio,
                      on_progress=on_progress)
    # miniatura tirada do próprio clipe vertical (já com legenda/gancho)
    thumbnail(out, min(1.5, (clip.end_s - clip.start_s) / 2), storage.path_for(thumb_key))
    clip.render_key, clip.thumb_key, clip.render_status = video_key, thumb_key, "ready"
    db.commit()


class _Progress:
    """Atualiza a barra de progresso no banco sem escrever a cada chamada (máx. 1x/s)."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._last = 0.0

    def set(self, value: float, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last < 1.0:
            return
        self._last = now
        with session_factory()() as db:
            p = db.get(Project, self.project_id)
            if p is not None and int(value) > p.progress:
                p.progress = int(value)
                db.commit()

    def span(self, lo: float, hi: float):
        return lambda frac: self.set(lo + (hi - lo) * frac)


def _set_status(project_id: str, status: str) -> None:
    with session_factory()() as db:
        p = db.get(Project, project_id)
        if p is not None and p.status in ACTIVE_STATUSES:
            p.status = status
            db.commit()


def _whole_video_clip(db: Session, project: Project) -> Clip:
    """Modo "só baixar" com template: um único "clipe" com o vídeo inteiro."""
    for c in list(project.clips):
        db.delete(c)
    db.flush()
    clip = Clip(project_id=project.id, start_s=0.0, end_s=float(project.duration_s or 0), score=100,
                title=project.title or "", hook="", reason="Vídeo completo com o template aplicado.",
                signals={"ranker": "download"})
    db.add(clip)
    db.flush()
    return clip


def process_project(project_id: str) -> None:
    db = session_factory()()
    workdir = Path(tempfile.mkdtemp(prefix="ezt-"))
    project = db.get(Project, project_id)
    if project is None:
        log.error("projeto %s não encontrado", project_id)
        return
    ctrl = Control(project_id, on_pause=lambda paused: _set_status(
        project_id, ProjectStatus.paused.value if paused else ProjectStatus.processing.value))
    token = activate(ctrl)
    prog = _Progress(project_id)
    try:
        st = project.settings or {}
        mode = st.get("mode", "clips")
        ctrl.check()  # cancelado/pausado antes mesmo de começar (ex.: ainda na fila)
        _update(db, project, status=ProjectStatus.processing.value, stage="ingest", progress=1, error=None)

        # 1) Ingestão
        if project.source_type == "url" and not project.source_key:
            dl = download_url(project.source_url or "", workdir / "dl", max_height=int(st.get("download_height", 1080)),
                              on_progress=prog.span(1, 15 if mode == "clips" else 45))
            key = f"{storage.project_dir(project.id)}/source{dl.path.suffix}"
            shutil.move(str(dl.path), storage.path_for(key))
            project.source_key = key
            if dl.title and (not project.title or project.title == project.source_url):
                project.title = dl.title[:255]
            db.commit()
        src = _source_path(project)
        info = probe(src)
        max_min = get_settings().max_video_minutes
        if info.duration_s > max_min * 60:
            raise ValueError(f"vídeo maior que o limite configurado ({max_min} min, EZT_MAX_VIDEO_MINUTES)")
        project.duration_s, project.width, project.height = info.duration_s, info.width, info.height
        ctrl.check()

        if mode == "download":
            _download_mode(db, project, info, src, workdir, prog)
        else:
            _clips_mode(db, project, info, src, workdir, prog)

        _update(db, project, status=ProjectStatus.ready.value, stage="done", progress=100, control="run")
    except Cancelled:
        log.info("projeto %s cancelado", project_id)
        db.rollback()
        project = db.get(Project, project_id)
        if project is not None:
            for c in list(project.clips):  # mantém os clipes já prontos; descarta os incompletos
                if c.render_status != "ready":
                    db.delete(c)
            project.status, project.error, project.control = ProjectStatus.cancelled.value, None, "run"
            db.commit()
    except Exception as e:
        log.exception("falha ao processar projeto %s", project_id)
        db.rollback()
        project = db.get(Project, project_id)
        if project is not None:
            project.status, project.error, project.control = ProjectStatus.failed.value, str(e)[:2000], "run"
            db.commit()
    finally:
        reset_control(token)
        shutil.rmtree(workdir, ignore_errors=True)
        db.close()


def _transcribe_project(db: Session, project: Project, info, src: Path, workdir: Path, on_progress) -> Path | None:
    st = project.settings or {}
    wav = None
    words: list[dict] = []
    if info.has_audio:
        wav = extract_audio(src, workdir / "audio.wav")
        words, lang = transcribe(wav, st.get("language"), on_progress=on_progress)
        if lang and not st.get("language"):
            project.settings = {**st, "language": lang}
    project.transcript = words
    db.commit()
    return wav


def _clips_mode(db: Session, project: Project, info, src: Path, workdir: Path, prog: _Progress) -> None:
    _update(db, project, stage="transcribe", progress=15)
    wav = _transcribe_project(db, project, info, src, workdir, prog.span(15, 45))
    st = project.settings or {}
    words = project.transcript or []
    _update(db, project, stage="analyze", progress=45)

    sig = signals.compute(src, wav, info.duration_s, words)
    checkpoint()
    max_clips = int(st.get("max_clips", 8))
    min_s, max_s = int(st.get("clip_min_s", 15)), int(st.get("clip_max_s", 45))
    cands = cand_mod.generate(sig, info.duration_s, words, min_s, max_s, limit=max_clips * 2)
    _update(db, project, stage="rank", progress=60)
    ranked, method = ranker.rank(cands, words, info.duration_s, st.get("game", ""), min_s, max_s,
                                 method=st.get("ranker"), language=st.get("language"))
    ranked = ranked[:max_clips]
    checkpoint()

    for c in list(project.clips):
        db.delete(c)
    db.flush()
    clips = []
    for r in ranked:
        clip = Clip(project_id=project.id, start_s=r.start, end_s=r.end, score=r.score, title=r.title,
                    hook=r.hook, reason=r.reason, signals={**r.stats, "ranker": method})
        db.add(clip)
        clips.append(clip)
    _update(db, project, stage="render", progress=70)

    for i, clip in enumerate(clips):
        lo = 70 + 30 * i / max(1, len(clips))
        hi = 70 + 30 * (i + 1) / max(1, len(clips))
        try:
            _render(db, project, clip, workdir, on_progress=prog.span(lo, hi))
        except Cancelled:
            raise
        except Exception:
            log.exception("falha ao renderizar clipe %s", clip.id)
            clip.render_status = "failed"
            db.commit()
        prog.set(hi, force=True)


def _download_mode(db: Session, project: Project, info, src: Path, workdir: Path, prog: _Progress) -> None:
    st = project.settings or {}
    cfg = _template_config(db, project)
    if cfg is None:  # sem template: o próprio arquivo baixado é o resultado
        for c in list(project.clips):
            db.delete(c)
        db.commit()
        return
    if st.get("captions", True):
        _update(db, project, stage="transcribe", progress=45)
        _transcribe_project(db, project, info, src, workdir, prog.span(45, 60))
    clip = _whole_video_clip(db, project)
    _update(db, project, stage="render", progress=60)
    _render(db, project, clip, workdir, on_progress=prog.span(60, 99))


def render_one(clip_id: str) -> None:
    """Re-renderiza um clipe após edição (início/fim/gancho)."""
    db = session_factory()()
    workdir = Path(tempfile.mkdtemp(prefix="ezt-r-"))
    try:
        clip = db.get(Clip, clip_id)
        if clip is None:
            return
        try:
            _render(db, clip.project, clip, workdir)
        except Exception:
            log.exception("falha ao re-renderizar clipe %s", clip_id)
            clip.render_status = "failed"
            db.commit()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        db.close()


def render_all(project_id: str) -> None:
    """Re-renderiza todos os clipes (ex.: depois de trocar o template), em sequência."""
    db = session_factory()()
    workdir = Path(tempfile.mkdtemp(prefix="ezt-all-"))
    try:
        project = db.get(Project, project_id)
        if project is None:
            return
        if (project.settings or {}).get("mode") == "download":
            if _template_config(db, project) is None:  # sem template: só o arquivo original
                for c in list(project.clips):
                    db.delete(c)
                db.commit()
                return
            _whole_video_clip(db, project)
            db.commit()
            db.refresh(project)
        for clip in list(project.clips):
            try:
                _render(db, project, clip, workdir)
            except Exception:
                log.exception("falha ao re-renderizar clipe %s", clip.id)
                clip.render_status = "failed"
                db.commit()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        db.close()
