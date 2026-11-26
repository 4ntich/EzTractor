"""Busca de virais no YouTube: API oficial (com chave) e yt-dlp (sem chave), com as respostas simuladas."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


SEARCH = {"items": [{"id": {"kind": "youtube#video", "videoId": v}} for v in ("aaa", "bbb", "ccc", "ddd")]}
VIDEOS = {"items": [
    # 1 milhão em 10 dias = 100 mil/dia
    {"id": "aaa", "snippet": {"title": "Capa absurda", "channelTitle": "Canal A", "channelId": "UCa",
                              "publishedAt": _iso(240), "thumbnails": {"high": {"url": "https://i.ytimg.com/a.jpg"}}},
     "statistics": {"viewCount": "1000000", "likeCount": "20000", "commentCount": "300"},
     "contentDetails": {"duration": "PT45S"}},
    # 300 mil em 12 h = 600 mil/dia -> o que mais está viralizando
    {"id": "bbb", "snippet": {"title": "Viralizou ontem", "channelTitle": "Canal B", "channelId": "UCb",
                              "publishedAt": _iso(12), "thumbnails": {}},
     "statistics": {"viewCount": "300000", "likeCount": "45000"}, "contentDetails": {"duration": "PT1M30S"}},
    # 3:30 -> não é Short
    {"id": "ccc", "snippet": {"title": "Longo demais", "channelTitle": "C", "channelId": "UCc",
                              "publishedAt": _iso(48)}, "statistics": {"viewCount": "5000000"},
     "contentDetails": {"duration": "PT3M30S"}},
    # likes ocultos
    {"id": "ddd", "snippet": {"title": "Sem likes", "channelTitle": "D", "channelId": "UCd", "publishedAt": _iso(72)},
     "statistics": {"viewCount": "90000"}, "contentDetails": {"duration": "PT20S"}},
]}


@pytest.fixture()
def fake_api(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers})
        if headers.get("X-Goog-Api-Key") == "chave-ruim-0000000000000000":
            return httpx.Response(400, json={"error": {"errors": [{"reason": "keyInvalid"}]}},
                                  request=httpx.Request("GET", url))
        if headers.get("X-Goog-Api-Key") == "chave-sem-cota-00000000000000":
            return httpx.Response(403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}},
                                  request=httpx.Request("GET", url))
        data = SEARCH if url.endswith("/search") else VIDEOS
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))

    from eztractor import viral

    monkeypatch.setattr(httpx, "get", fake_get)
    viral._cache.clear()
    return calls


@pytest.fixture()
def fake_ytdlp(monkeypatch):
    """Formato real devolvido pelo yt-dlp na busca (sem visualizações/data)."""
    import yt_dlp

    seen = {}

    class FakeYDL:
        def __init__(self, opts):
            seen["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def extract_info(self, url, download=False):
            seen["url"] = url
            return {"entries": [
                {"id": "x1", "title": "Clutch 1v5", "duration": 54, "url": "https://www.youtube.com/watch?v=x1"},
                {"id": "x2", "title": "Montagem longa", "duration": 235},
                {"id": "x3", "title": "Ace", "duration": 87, "thumbnails": [{"url": "https://i.ytimg.com/x3.jpg"}]},
            ]}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    from eztractor import viral

    viral._cache.clear()
    return seen


def _set_key(monkeypatch, key: str):
    from eztractor.config import get_settings

    monkeypatch.setattr(get_settings(), "youtube_api_key", key)


def test_api_ranks_by_views_per_day_and_filters_shorts(fake_api, monkeypatch):
    from eztractor import viral

    _set_key(monkeypatch, "chave-boa-00000000000000000000")
    r = viral.search("free fire capa", period="week", kind="shorts", sort="trending", region="BR")
    assert r["source"] == "api" and r["notice"] is None
    ids = [i["id"] for i in r["results"]]
    assert ids == ["bbb", "aaa", "ddd"]  # 600 mil/dia > 100 mil/dia > 30 mil/dia; 3:30 fica de fora
    top = r["results"][0]
    assert top["views"] == 300000 and 500_000 < top["views_per_day"] < 700_000
    assert top["is_short"] and top["url"] == "https://www.youtube.com/shorts/bbb" and top["duration_s"] == 90
    assert r["results"][1]["thumbnail"] == "https://i.ytimg.com/a.jpg"
    assert r["results"][2]["likes"] is None and r["results"][2]["engagement"] is None
    # a chave vai no cabeçalho, nunca no link (não aparece em logs)
    search_call = fake_api[0]
    assert "key" not in search_call["params"] and search_call["headers"]["X-Goog-Api-Key"]
    assert search_call["params"]["videoDuration"] == "short" and search_call["params"]["regionCode"] == "BR"
    assert search_call["params"]["relevanceLanguage"] == "pt" and "publishedAfter" in search_call["params"]
    assert fake_api[1]["params"]["id"] == "aaa,bbb,ccc,ddd"  # 1 chamada para os detalhes de todos


def test_api_other_sorts(fake_api, monkeypatch):
    from eztractor import viral

    _set_key(monkeypatch, "chave-boa-00000000000000000000")
    assert [i["id"] for i in viral.search("x", kind="any", sort="views")["results"]][:2] == ["ccc", "aaa"]
    assert viral.search("x", kind="shorts", sort="engagement")["results"][0]["id"] == "bbb"  # 15% de likes


def test_cache_saves_quota(fake_api, monkeypatch):
    from eztractor import viral

    _set_key(monkeypatch, "chave-boa-00000000000000000000")
    viral.search("capa", kind="shorts")
    n = len(fake_api)
    again = viral.search("CAPA ", kind="shorts")
    assert again["cached"] and len(fake_api) == n


@pytest.mark.parametrize("key,msg", [("chave-ruim-0000000000000000", "inválida"),
                                     ("chave-sem-cota-00000000000000", "cota")])
def test_bad_key_or_quota_falls_back_to_ytdlp(fake_api, fake_ytdlp, monkeypatch, key, msg):
    from eztractor import viral

    _set_key(monkeypatch, key)
    r = viral.search("valorant clutch", kind="shorts")
    assert r["source"] == "ytdlp" and msg in r["notice"] and "sem chave" in r["notice"]
    assert [i["id"] for i in r["results"]] == ["x1", "x3"]


def test_no_key_uses_ytdlp_with_youtube_filters(fake_ytdlp, monkeypatch):
    from eztractor import viral

    _set_key(monkeypatch, "")
    r = viral.search("valorant clutch", period="week", kind="shorts", limit=10)
    assert r["source"] == "ytdlp" and "Sem chave" in r["notice"]
    assert [i["id"] for i in r["results"]] == ["x1", "x3"]  # 3:55 não é Short
    assert r["results"][0]["views"] is None and r["results"][0]["views_per_day"] is None
    assert r["results"][1]["thumbnail"] == "https://i.ytimg.com/x3.jpg"
    # mesmo filtro testado ao vivo: mais vistos + esta semana + vídeo + menos de 4 min
    assert fake_ytdlp["url"].endswith("&sp=CAMSBggDEAEYAQ==") and "valorant+clutch" in fake_ytdlp["url"]
    assert fake_ytdlp["opts"]["extract_flat"] is True


def test_sp_filters():
    from eztractor.viral import _sp

    assert _sp("any", "any") == "CAMSAhAB"  # só "mais vistos" + vídeo
    assert _sp("today", "videos") == "CAMSBggCEAEYAw=="


def test_empty_query():
    from eztractor import viral

    with pytest.raises(viral.ViralError):
        viral.search("   ")


# ---------------------------------------------------------------- API do app
@pytest.fixture()
def desktop_client(tmp_path, monkeypatch):
    """Simula o app Windows: senha + confiança no localhost + config.env."""
    from eztractor import config, db
    from tests.conftest import _make_client

    cfg = tmp_path / "config.env"
    cfg.write_text("EZT_LAN_ACCESS=0\n", encoding="utf-8")
    monkeypatch.setenv("EZT_TRUST_LOCALHOST", "1")
    monkeypatch.setenv("EZT_CONFIG_FILE", str(cfg))
    monkeypatch.delenv("EZT_YOUTUBE_API_KEY", raising=False)
    with _make_client(tmp_path, monkeypatch, password="segredo1") as c:
        yield c, cfg
    db.reset_engine()
    config.get_settings.cache_clear()


def test_viral_endpoint_and_key_config(desktop_client, fake_api, monkeypatch):
    from starlette.testclient import TestClient

    c, cfg = desktop_client
    local = TestClient(c.app, client=("127.0.0.1", 5000))
    assert local.get("/system/youtube").json() == {"configured": False, "configurable": True}
    assert local.post("/system/youtube", json={"key": "curta"}).status_code == 422
    r = local.post("/system/youtube", json={"key": "chave-ruim-0000000000000000"})
    assert r.status_code == 422 and "inválida" in r.json()["detail"]
    assert local.post("/system/youtube", json={"key": "chave-boa-00000000000000000000"}).json() == {"configured": True}
    assert "EZT_YOUTUBE_API_KEY=chave-boa-00000000000000000000" in cfg.read_text(encoding="utf-8")
    r = local.get("/viral/search", params={"q": "free fire capa"}).json()
    assert r["source"] == "api" and r["results"][0]["id"] == "bbb"
    assert local.delete("/system/youtube").json() == {"configured": False}
    assert local.get("/system/youtube").json()["configured"] is False


def test_phone_cannot_change_the_key(desktop_client):
    from starlette.testclient import TestClient

    from eztractor.config import get_settings

    c, _ = desktop_client
    get_settings().lan_access = True
    phone = TestClient(c.app, client=("192.168.0.50", 5000))
    tok = phone.post("/auth/login", json={"password": "segredo1"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert phone.post("/system/youtube", json={"key": "chave-boa-00000000000000000000"}, headers=h).status_code == 403
    assert phone.delete("/system/youtube", headers=h).status_code == 403
