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
from ..ads import cuts_within, from_sponsorblock, from_transcript, merge, overlap
from ..control import Cancelled, Control, activate, checkpoint
from ..control import _current as _control_var
from ..models import ACTIVE_STATUSES, Clip, Project, ProjectStatus, Template
from . import candidates as cand_mod
from . import audience, overlays, ranker, signals, visual
from .captions import build_ass, write_ass
from .social import dominant_signal, make_caption, make_hashtags
from .ingest import download_url
from .media import extract_audio, probe, thumbnail
from .render import RenderSpec, cut_concat, render_clip
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


def kept_segments(start: float, end: float, cuts: list | None) -> list[tuple[float, float]]:
    """[start, end] menos os cortes => trechos mantidos, em ordem."""
    segs, cur = [], start
    for a, b in sorted((max(start, c[0]), min(end, c[1])) for c in (cuts or []) if c[1] > c[0]):
        if a > cur + 0.05:
            segs.append((cur, a))
        cur = max(cur, b)
    if end > cur + 0.05:
        segs.append((cur, end))
    return segs


def remap_words(words: list[dict], segs: list[tuple[float, float]]) -> list[dict]:
    """Leva as palavras para a linha do tempo do vídeo editado (sem os trechos cortados)."""
    out, acc = [], 0.0
    for a, b in segs:
        for w in words:
            if w["start"] >= a and w["end"] <= b + 0.05:
                out.append({**w, "start": round(w["start"] - a + acc, 2), "end": round(min(w["end"], b) - a + acc, 2)})
        acc += b - a
    return out


def _render(db: Session, project: Project, clip: Clip, workdir: Path, on_progress=None) -> None:
    st = project.settings or {}
    max_side = int(st.get("render_height") or get_settings().render_height)
    cfg = _template_config(db, project)
    original_layout = st.get("mode") == "download" and cfg is None
    base = f"{storage.project_dir(project.id)}/clips/{clip.id}"
    video_key, thumb_key = f"{base}.mp4", f"{base}.jpg"
    src = _source_path(project)
    info = probe(src)
    segs = kept_segments(clip.start_s, clip.end_s, clip.cuts)
    if not segs:
        raise ValueError("o vídeo editado ficou vazio")
    dur = sum(b - a for a, b in segs)

    if original_layout:
        # só baixar, sem template: sem cortes o próprio arquivo é o resultado; com cortes, junta os trechos
        if len(segs) == 1 and segs[0][0] <= 0.05 and segs[0][1] >= (project.duration_s or 0) - 0.05:
            clip.render_key = project.source_key
        else:
            cut_concat(src, segs, storage.path_for(video_key), info.has_audio, final=True, on_progress=on_progress)
            clip.render_key = video_key
        thumbnail(storage.path_for(clip.render_key), min(3.0, dur / 2), storage.path_for(thumb_key))
        clip.thumb_key, clip.render_status = thumb_key, "ready"
        db.commit()
        return

    words = project.transcript or []
    if len(segs) > 1:  # cortes no meio: junta os trechos num arquivo temporário e renderiza a partir dele
        joined = workdir / f"{clip.id}-joined.mp4"
        cut_concat(src, segs, joined, info.has_audio, final=False)
        src, start, end, words = joined, 0.0, dur, remap_words(words, segs)
    else:
        start, end = segs[0]

    if cfg is not None:
        # consulta o banco: durante o processamento `project.clips` ainda não tem os clipes recém-criados
        db.flush()
        ranked = list(db.scalars(select(Clip).where(Clip.project_id == project.id)
                                 .order_by(Clip.score.desc(), Clip.start_s)))
        rank = next((i + 1 for i, c in enumerate(ranked) if c.id == clip.id), 1)
        spec = template_spec(cfg, start, end, max_side, st.get("layout", "crop"), st.get("facecam"))
        ass = build_template_ass(cfg, words, start, end,
                                 clip_context(clip, project, len(ranked), rank), captions=st.get("captions", True))
    else:
        spec = RenderSpec(start=start, end=end, height=max_side, layout=st.get("layout", "crop"),
                          facecam=st.get("facecam"))
        ass = build_ass(words, start, end, spec.width, spec.height, hook=clip.hook, captions=st.get("captions", True))
    spec.ass_path = write_ass(workdir / f"{clip.id}.ass", ass)

    out = render_clip(src, storage.path_for(video_key), spec, info.width, info.height, info.has_audio,
                      on_progress=on_progress)
    thumbnail(out, min(1.5, dur / 2), storage.path_for(thumb_key))
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
    """Modo "só baixar": um único "clipe" com o vídeo inteiro (dá para aparar e cortar no editor)."""
    for c in list(project.clips):
        db.delete(c)
    db.flush()
    st = project.settings or {}
    dur = float(project.duration_s or 0)
    cuts = cuts_within(0.0, dur, project.skip_segments or []) if st.get("skip_ads", True) else []
    clip = Clip(project_id=project.id, start_s=0.0, end_s=dur, score=100, title=project.title or "", hook="",
                reason="Vídeo completo" + (f" sem {len(cuts)} trecho(s) de propaganda/final." if cuts else "."),
                signals={"ranker": "download"}, cuts=cuts,
                caption=make_caption(project.title or "", "", st.get("game", ""), st.get("language")),
                hashtags=make_hashtags(st.get("game", ""), st.get("language")))
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
            if dl.extractor.startswith("youtube") and dl.video_id:
                project.youtube_id = dl.video_id[:32]
            project.audience = {"heatmap": dl.heatmap, "channel": dl.channel_names, "has_live_chat": dl.has_live_chat}
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


def _own_names(project: Project) -> list[str]:
    return list((project.audience or {}).get("channel") or [])


def _detect_skips(db: Session, project: Project, duration: float, vis=None, banners: list[dict] | None = None) -> None:
    """Propaganda/inscrição/final: transcrição + SponsorBlock + imagem (vinhetas, telas paradas, tela final)
    + banners lidos na imagem."""
    st = project.settings or {}
    if not st.get("skip_ads", True):
        project.skip_segments = []
    else:
        segs = from_transcript(project.transcript or [], duration)
        if project.youtube_id:
            segs += from_sponsorblock(project.youtube_id, duration)
        if vis is not None:
            _, speech = signals.word_counts(project.transcript or [], max(1, int(duration) + 1))
            segs += visual.skip_segments(vis, speech, duration)
        segs += banners or []
        project.skip_segments = merge(segs)
    db.commit()


def _scan_banners(db: Session, project: Project, info, src: Path, windows: list[tuple[float, float]],
                  done: set[float], on_progress=None) -> list[dict]:
    st = project.settings or {}
    if not st.get("skip_ads", True) or not st.get("read_banners", True) or not overlays.available():
        return []
    segs, stats = overlays.find_banners(src, windows, info.duration_s, info.width, info.height,
                                        own_names=_own_names(project), on_progress=on_progress, already=done)
    an = dict((project.settings or {}).get("analysis") or {})
    an["ocr_frames"] = an.get("ocr_frames", 0) + stats.get("frames", 0)
    project.settings = {**(project.settings or {}), "analysis": an}
    return segs


def _fetch_chat(db: Session, project: Project, duration: float, workdir: Path, on_progress=None) -> None:
    """Baixa e resume o chat de uma live do YouTube (uma vez por projeto)."""
    aud = dict(project.audience or {})
    if not aud.get("has_live_chat") or aud.get("chat") or not project.source_url:
        return
    path = audience.download_youtube_chat(project.source_url, workdir / "chat", on_progress=on_progress)
    if path is not None:
        msgs = audience.parse_youtube_chat(path)
        aud["chat"] = audience.chat_per_second(msgs, max(1, int(duration) + 1))
        project.audience = aud
        db.commit()


def _record_analysis(db: Session, project: Project, sig, skips: list[dict]) -> None:
    an = dict((project.settings or {}).get("analysis") or {})
    aud = project.audience or {}
    an.update({
        "visual": sig.motion_z is not None,
        "chat_msgs": int((aud.get("chat") or {}).get("total", 0)),
        "heatmap": sig.heat is not None,
        "skips": {cat: sum(1 for s in skips if cat in s.get("category", "")) for cat in
                  ("sponsor", "interaction", "outro", "vinheta", "parado", "endscreen", "banner")},
    })
    project.settings = {**(project.settings or {}), "analysis": an}
    db.commit()


def _clips_mode(db: Session, project: Project, info, src: Path, workdir: Path, prog: _Progress) -> None:
    _update(db, project, stage="transcribe", progress=15)
    wav = _transcribe_project(db, project, info, src, workdir, prog.span(15, 45))
    st = project.settings or {}
    words = project.transcript or []
    _update(db, project, stage="analyze", progress=45)
    _fetch_chat(db, project, info.duration_s, workdir, on_progress=prog.span(45, 48))
    checkpoint()
    vis = visual.extract(src)  # trocas de cena + miniaturas numa só passada
    _detect_skips(db, project, info.duration_s, vis=vis)
    skips = project.skip_segments or []
    sig = signals.compute(src, wav, info.duration_s, words, vis=vis, audience=project.audience)
    checkpoint()
    max_clips = int(st.get("max_clips", 8))
    min_s, max_s = int(st.get("clip_min_s", 15)), int(st.get("clip_max_s", 45))
    limit = max_clips * 2
    cands = cand_mod.generate(sig, info.duration_s, words, min_s, max_s, limit=limit, excluded=skips)

    # banners de outros canais: lê o texto da imagem só nos candidatos (+ começo e fim do vídeo)
    _update(db, project, stage="banners", progress=52)
    dur = info.duration_s
    done: set[float] = set()
    windows = [(c.start - 3, c.end + 3) for c in cands] + [(0, min(dur, 45)), (max(0, dur - 90), dur)]
    banners = _scan_banners(db, project, info, src, windows, done, on_progress=prog.span(52, 57))
    if banners:  # gera de novo evitando os banners e lê os candidatos novos
        _detect_skips(db, project, dur, vis=vis, banners=banners)
        skips = project.skip_segments or []
        cands = cand_mod.generate(sig, dur, words, min_s, max_s, limit=limit, excluded=skips)
        more = _scan_banners(db, project, info, src, [(c.start - 3, c.end + 3) for c in cands], done,
                             on_progress=prog.span(57, 59))
        if more:
            banners += more
            _detect_skips(db, project, dur, vis=vis, banners=banners)
            skips = project.skip_segments or []
            cands = cand_mod.generate(sig, dur, words, min_s, max_s, limit=limit, excluded=skips)
    _record_analysis(db, project, sig, skips)
    for c in cands:  # avisa a IA de trechos suspeitos por perto
        if overlap(c.start - 5, c.end + 5, skips) > 0:
            c.stats["skip_nearby"] = True
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
        game, lang = st.get("game", ""), (project.settings or {}).get("language")
        clip = Clip(project_id=project.id, start_s=r.start, end_s=r.end, score=r.score, title=r.title,
                    hook=r.hook, reason=r.reason, signals={**r.stats, "ranker": method},
                    cuts=cuts_within(r.start, r.end, skips),  # se a IA estendeu para dentro de um trecho a pular
                    # legenda/hashtags da IA; sem IA (ou se ela não mandou), o gerador grátis
                    caption=r.caption or make_caption(r.title, r.hook, game, lang, dominant_signal(r.stats)),
                    hashtags=r.hashtags or make_hashtags(game, lang))
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
    if (cfg is not None and st.get("captions", True)) or st.get("skip_ads", True):
        _update(db, project, stage="transcribe", progress=45)
        _transcribe_project(db, project, info, src, workdir, prog.span(45, 60))
    vis = banners = None
    if st.get("skip_ads", True):
        _update(db, project, stage="analyze", progress=60)
        vis = visual.extract(src)
        dur = info.duration_s
        banners = _scan_banners(db, project, info, src, [(0, min(dur, 45)), (max(0, dur - 90), dur)], set())
    _detect_skips(db, project, info.duration_s, vis=vis, banners=banners)
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
        if (project.settings or {}).get("mode") == "download" and not project.clips:
            _whole_video_clip(db, project)  # mantém aparas/cortes de um clipe existente
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
