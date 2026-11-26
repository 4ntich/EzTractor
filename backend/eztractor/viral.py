"""Descobrir vídeos/clipes virais no YouTube.

- Com chave (YouTube Data API v3, oficial e grátis: ~100 buscas/dia): visualizações, curtidas, data e
  duração; dá para ordenar pelo que está VIRALIZANDO (visualizações por dia).
- Sem chave (ou se a chave falhar/a cota acabar): busca do yt-dlp com os filtros do próprio YouTube
  ("mais vistos" no período), só com título, link e duração.
"""

import base64
import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

from .config import get_settings

log = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
PERIODS = {"today": 1, "week": 7, "month": 30, "year": 365, "any": None}
KINDS = ("shorts", "videos", "any")
SORTS = ("trending", "views", "engagement")
SHORTS_MAX_S = 180  # Shorts têm até 3 min
_CACHE_S = 600
_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()


_YT_ID = None


def youtube_video_id(url: str | None) -> str | None:
    """ID de 11 caracteres de qualquer link do YouTube (watch?v=, /shorts/, youtu.be/, /live/, /embed/)."""
    import re

    global _YT_ID
    if _YT_ID is None:
        _YT_ID = re.compile(r"(?:[?&]v=|/shorts/|youtu\.be/|/live/|/embed/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")
    m = _YT_ID.search(url or "")
    return m.group(1) if m else None


def known_videos(db) -> dict[str, dict]:
    """Vídeos do YouTube que já têm projeto: {id do vídeo: {id, status, title}} (o mais recente vence)."""
    from sqlalchemy import select

    from .models import Project

    out: dict[str, dict] = {}
    rows = db.execute(select(Project.id, Project.title, Project.status, Project.youtube_id, Project.source_url)
                      .order_by(Project.created_at)).all()
    for pid, title, status, yid, src in rows:
        vid = yid or youtube_video_id(src)
        if vid:
            out[vid] = {"id": pid, "status": status, "title": title}
    return out


class ViralError(Exception):
    """Erro para mostrar ao usuário (chave inválida, sem internet...)."""


def _iso_duration(d: str) -> int:
    """'PT1M5S' -> 65."""
    import re

    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def _item(vid: str, title: str, channel: str, channel_id: str, published: datetime | None, views: int | None,
          likes: int | None, comments: int | None, duration: int | None, thumb: str) -> dict:
    now = datetime.now(timezone.utc)
    age_h = max(1.0, (now - published).total_seconds() / 3600) if published else None
    per_day = round(views / max(age_h / 24, 0.25)) if views is not None and age_h else None
    return {
        "id": vid, "url": f"https://www.youtube.com/watch?v={vid}" if not (duration and duration <= SHORTS_MAX_S)
        else f"https://www.youtube.com/shorts/{vid}",
        "title": title, "channel": channel,
        "channel_url": f"https://www.youtube.com/channel/{channel_id}" if channel_id else None,
        "published_at": published.isoformat() if published else None,
        "age_hours": round(age_h, 1) if age_h else None,
        "views": views, "likes": likes, "comments": comments,
        "views_per_day": per_day,
        "engagement": round((likes or 0) / views, 4) if views and likes is not None else None,
        "duration_s": duration, "is_short": bool(duration and duration <= SHORTS_MAX_S),
        "thumbnail": thumb or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
    }


# ---------------------------------------------------------------- API oficial
def _api_get(path: str, params: dict, key: str) -> dict:
    try:
        r = httpx.get(f"{API}/{path}", params=params, headers={"X-Goog-Api-Key": key}, timeout=20)
    except httpx.HTTPError as e:
        raise ViralError(f"sem conexão com o YouTube: {e}") from None
    if r.status_code == 200:
        return r.json()
    try:
        reason = r.json()["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, TypeError):
        reason = str(r.status_code)
    if reason in ("keyInvalid", "badRequest") or r.status_code == 400:
        raise ViralError("chave do YouTube inválida")
    if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
        raise ViralError("a cota grátis de hoje da chave do YouTube acabou (renova à meia-noite do Pacífico)")
    if reason in ("accessNotConfigured", "SERVICE_DISABLED"):
        raise ViralError("a YouTube Data API v3 não está ativada no projeto dessa chave")
    raise ViralError(f"o YouTube recusou a busca ({reason})")


def search_api(q: str, key: str, period: str, kind: str, region: str | None, limit: int) -> list[dict]:
    params = {"part": "snippet", "type": "video", "q": q, "maxResults": 50, "order": "viewCount",
              "safeSearch": "none"}
    days = PERIODS.get(period)
    if days:
        params["publishedAfter"] = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if kind == "shorts":
        params["videoDuration"] = "short"  # < 4 min; filtramos <= 3 min abaixo
    elif kind == "videos":
        params["videoDuration"] = "medium"  # 4 a 20 min (vídeos "normais")
    if region:
        params["regionCode"] = region
        params["relevanceLanguage"] = {"BR": "pt", "PT": "pt", "US": "en", "ES": "es", "MX": "es"}.get(region, "")
        if not params["relevanceLanguage"]:
            params.pop("relevanceLanguage")
    found = _api_get("search", params, key).get("items", [])
    ids = [i["id"]["videoId"] for i in found if i.get("id", {}).get("videoId")]
    if not ids:
        return []
    stats = _api_get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[:50]),
                                "maxResults": 50}, key).get("items", [])
    out = []
    for v in stats:
        sn, st, cd = v.get("snippet", {}), v.get("statistics", {}), v.get("contentDetails", {})
        dur = _iso_duration(cd.get("duration", ""))
        if kind == "shorts" and dur > SHORTS_MAX_S:
            continue
        try:
            pub = datetime.fromisoformat(sn.get("publishedAt", "").replace("Z", "+00:00"))
        except ValueError:
            pub = None
        num = lambda k: int(st[k]) if st.get(k) is not None else None  # noqa: E731
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        out.append(_item(v["id"], sn.get("title", ""), sn.get("channelTitle", ""), sn.get("channelId", ""), pub,
                         num("viewCount"), num("likeCount"), num("commentCount"), dur, thumb))
    return out


def check_key(key: str) -> None:
    """Testa a chave com a chamada mais barata (1 unidade da cota)."""
    _api_get("videos", {"part": "id", "id": "dQw4w9WgXcQ"}, key)


# ---------------------------------------------------------------- sem chave (yt-dlp)
def _sp(period: str, kind: str) -> str:
    """Filtro da página de busca do YouTube: ordenar por visualizações + período + tipo vídeo + duração."""
    upload = {"today": 2, "week": 3, "month": 4, "year": 5}.get(period)
    inner = b""
    if upload:
        inner += bytes([0x08, upload])
    inner += bytes([0x10, 0x01])  # tipo: vídeo
    dur = {"shorts": 1, "videos": 3}.get(kind)  # 1 = menos de 4 min, 3 = 4 a 20 min
    if dur:
        inner += bytes([0x18, dur])
    raw = bytes([0x08, 0x03, 0x12, len(inner)]) + inner  # 0x08 0x03 = ordenar por visualizações
    return base64.urlsafe_b64encode(raw).decode()


def search_ytdlp(q: str, period: str, kind: str, limit: int) -> list[dict]:
    from urllib.parse import quote_plus

    import yt_dlp

    url = f"https://www.youtube.com/results?search_query={quote_plus(q)}&sp={_sp(period, kind)}"
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": min(60, limit * 2)}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise ViralError(f"não foi possível buscar no YouTube: {str(e)[:200]}") from None
    out = []
    for e in info.get("entries") or []:
        vid = e.get("id")
        if not vid:
            continue
        dur = int(e["duration"]) if e.get("duration") else None
        if kind == "shorts" and dur and dur > SHORTS_MAX_S:
            continue
        thumbs = e.get("thumbnails") or []
        out.append(_item(vid, e.get("title") or "", e.get("channel") or e.get("uploader") or "",
                         e.get("channel_id") or "", None, e.get("view_count"), None, None, dur,
                         thumbs[-1]["url"] if thumbs else ""))
    return out


# ---------------------------------------------------------------- entrada única
def _rank(items: list[dict], sort: str) -> list[dict]:
    if sort == "views":
        key = lambda i: i["views"] or 0  # noqa: E731
    elif sort == "engagement":  # curtidas/visualizações, sem favorecer vídeos com quase nenhuma view
        key = lambda i: (i["engagement"] or 0) * math.log10(max(10, i["views"] or 0))  # noqa: E731
    else:  # viralizando: visualizações por dia
        key = lambda i: i["views_per_day"] or 0  # noqa: E731
    return sorted(items, key=key, reverse=True)


def search(q: str, period: str = "week", kind: str = "shorts", sort: str = "trending", region: str | None = "BR",
           limit: int = 25) -> dict:
    q = (q or "").strip()
    if not q:
        raise ViralError("digite um jogo ou tema para buscar")
    period = period if period in PERIODS else "week"
    kind = kind if kind in KINDS else "shorts"
    sort = sort if sort in SORTS else "trending"
    limit = max(5, min(50, int(limit)))
    key = get_settings().youtube_api_key.strip()
    ck = (q.lower(), period, kind, sort, region, limit, bool(key))
    with _lock:
        hit = _cache.get(ck)
        if hit and time.time() - hit[0] < _CACHE_S:
            return {**hit[1], "cached": True}

    notice = None
    source = "api" if key else "ytdlp"
    if key:
        try:
            items = _rank(search_api(q, key, period, kind, region, limit), sort)
        except ViralError as e:  # chave com problema ou cota acabou: segue sem chave e avisa
            log.warning("busca de virais pela API falhou: %s", e)
            notice = f"{e}. Mostrando a busca sem chave (sem números)."
            source = "ytdlp"
    if source == "ytdlp":
        items = search_ytdlp(q, period, kind, limit)  # já vem na ordem "mais vistos" do YouTube
        if not key:
            notice = "Sem chave do YouTube: resultados na ordem de mais vistos do período, sem números."
    result = {"source": source, "notice": notice, "results": items[:limit], "cached": False,
              "params": {"q": q, "period": period, "kind": kind, "sort": sort, "region": region}}
    with _lock:
        _cache[ck] = (time.time(), result)
    return result
