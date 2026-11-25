"""Orquestra o processamento de um projeto. Executado pelo worker (RQ) ou numa thread (modo inline)."""

import logging
import shutil
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from .. import credits, storage
from ..db import session_factory
from ..models import PLAN_LIMITS, Clip, Project, ProjectStatus
from . import candidates as cand_mod
from . import ranker, signals
from .captions import build_ass, write_ass
from .ingest import download_url
from .media import extract_audio, probe, thumbnail
from .render import RenderSpec, render_clip
from .transcribe import transcribe

log = logging.getLogger(__name__)
WATERMARK = "feito com EzTractor"


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


def _render(db: Session, project: Project, clip: Clip, workdir: Path) -> None:
    limits = PLAN_LIMITS[project.user.plan]
    st = project.settings or {}
    spec = RenderSpec(
        start=clip.start_s, end=clip.end_s, height=limits["render_height"],
        layout=st.get("layout", "crop"), facecam=st.get("facecam"),
    )
    ass = build_ass(
        project.transcript or [], clip.start_s, clip.end_s, spec.width, spec.height,
        hook=clip.hook, watermark=WATERMARK if limits["watermark"] else None,
        captions=st.get("captions", True),
    )
    spec.ass_path = write_ass(workdir / f"{clip.id}.ass", ass)

    base = f"{storage.project_dir(project.id)}/clips/{clip.id}"
    video_key, thumb_key = f"{base}.mp4", f"{base}.jpg"
    src = _source_path(project)
    info = probe(src)
    out = render_clip(src, storage.path_for(video_key), spec, info.width, info.height, info.has_audio)
    # miniatura tirada do próprio clipe vertical (já com legenda/gancho)
    thumbnail(out, min(1.5, (clip.end_s - clip.start_s) / 2), storage.path_for(thumb_key))
    clip.render_key, clip.thumb_key, clip.render_status = video_key, thumb_key, "ready"
    db.commit()


def process_project(project_id: str) -> None:
    db = session_factory()()
    workdir = Path(tempfile.mkdtemp(prefix="ezt-"))
    project = db.get(Project, project_id)
    if project is None:
        log.error("projeto %s não encontrado", project_id)
        return
    try:
        st = project.settings or {}
        _update(db, project, status=ProjectStatus.processing.value, stage="ingest", progress=2, error=None)

        # 1) Ingestão
        if project.source_type == "url" and not project.source_key:
            dl = download_url(project.source_url or "", workdir / "dl")
            key = f"{storage.project_dir(project.id)}/source{dl.suffix}"
            shutil.move(str(dl), storage.path_for(key))
            project.source_key = key
        src = _source_path(project)
        info = probe(src)
        limits = PLAN_LIMITS[project.user.plan]
        if info.duration_s > limits["max_video_minutes"] * 60:
            raise ValueError(f"vídeo excede o limite do plano ({limits['max_video_minutes']} min)")
        project.duration_s, project.width, project.height = info.duration_s, info.width, info.height

        # 2) Cobrança (uma única vez por projeto)
        if project.credits_charged == 0:
            cost = credits.cost_for_duration(info.duration_s)
            credits.charge(db, project.user_id, cost, project.id)
            project.credits_charged = cost
        _update(db, project, stage="transcribe", progress=15)

        # 3) Áudio + transcrição
        wav = None
        words: list[dict] = []
        if info.has_audio:
            wav = extract_audio(src, workdir / "audio.wav")
            words, lang = transcribe(wav, st.get("language"))
            if lang and not st.get("language"):
                project.settings = {**st, "language": lang}
                st = project.settings
        _update(db, project, stage="analyze", progress=45, transcript=words)

        # 4) Sinais + candidatos + ranking
        sig = signals.compute(src, wav, info.duration_s, words)
        max_clips = int(st.get("max_clips", 8))
        min_s, max_s = int(st.get("clip_min_s", 15)), int(st.get("clip_max_s", 45))
        cands = cand_mod.generate(sig, info.duration_s, words, min_s, max_s, limit=max_clips * 2)
        _update(db, project, stage="rank", progress=60)
        ranked, method = ranker.rank(cands, words, info.duration_s, st.get("game", ""), min_s, max_s)
        ranked = ranked[:max_clips]

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

        # 5) Render
        for i, clip in enumerate(clips):
            try:
                _render(db, project, clip, workdir)
            except Exception:
                log.exception("falha ao renderizar clipe %s", clip.id)
                clip.render_status = "failed"
                db.commit()
            _update(db, project, progress=70 + int(30 * (i + 1) / max(1, len(clips))))

        _update(db, project, status=ProjectStatus.ready.value, stage="done", progress=100)
    except Exception as e:
        log.exception("falha ao processar projeto %s", project_id)
        db.rollback()
        project = db.get(Project, project_id)
        if project is not None:
            if project.credits_charged:
                credits.grant(db, project.user_id, project.credits_charged, "refund", project.id)
                project.credits_charged = 0
            project.status = ProjectStatus.failed.value
            project.error = str(e)[:2000]
            db.commit()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        db.close()


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
