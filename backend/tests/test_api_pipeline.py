import json
import subprocess


def _probe(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")


def test_open_mode_needs_no_login(client):
    assert client.get("/auth/status").json() == {"password_required": False}
    assert client.get("/projects").json() == []


def test_password_mode(locked_client):
    c = locked_client
    assert c.get("/auth/status").json() == {"password_required": True}
    assert c.get("/projects").status_code == 401
    assert c.post("/auth/login", json={"password": "errada"}).status_code == 401
    tok = c.post("/auth/login", json={"password": "minha-senha"}).json()["token"]
    assert c.get("/projects", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert c.get("/projects", headers={"Authorization": "Bearer lixo"}).status_code == 401


def test_upload_generates_ranked_vertical_clips(client, sample_video):
    settings = {"clip_min_s": 8, "clip_max_s": 15, "max_clips": 3}
    with open(sample_video, "rb") as f:
        r = client.post("/projects/upload", files={"file": ("live.mp4", f, "video/mp4")},
                        data={"title": "Live teste", "settings": json.dumps(settings)})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    p = client.get(f"/projects/{pid}").json()
    assert p["status"] == "ready", p["error"]
    assert 1 <= len(p["clips"]) <= 3
    top = p["clips"][0]
    # o clipe mais bem ranqueado precisa conter o pico de áudio inteiro (30–35s)
    assert top["start_s"] <= 30.5 and top["end_s"] >= 35, top
    assert all(7.99 <= c["end_s"] - c["start_s"] <= 15.5 for c in p["clips"]), p["clips"]
    assert [c["score"] for c in p["clips"]] == sorted((c["score"] for c in p["clips"]), reverse=True)

    # vídeo vertical (EZT_RENDER_HEIGHT=1280 nos testes => 720x1280), servido por URL assinada
    assert top["render_status"] == "ready"
    vid = client.get(top["video_url"])
    assert vid.status_code == 200 and len(vid.content) > 1000
    from eztractor import storage
    from eztractor.db import session_factory
    from eztractor.models import Clip

    with session_factory()() as db:
        key = db.get(Clip, top["id"]).render_key
    stream = _probe(storage.path_for(key))
    assert (stream["width"], stream["height"]) == (720, 1280)

    # URL adulterada é rejeitada
    assert client.get(top["video_url"].replace("sig=", "sig=x")).status_code == 403

    # edição re-renderiza
    r = client.patch(f"/clips/{top['id']}", json={"start_s": 29, "end_s": 37, "hook": "OLHA ISSO"})
    assert r.status_code == 200 and r.json()["render_status"] == "ready"
    assert client.patch(f"/clips/{top['id']}", json={"start_s": 50, "end_s": 40}).status_code == 422

    assert client.delete(f"/projects/{pid}").status_code == 204
    assert client.get(f"/projects/{pid}").status_code == 404


def test_split_layout_requires_facecam(client, sample_video):
    with open(sample_video, "rb") as f:
        r = client.post("/projects/upload", files={"file": ("x.mp4", f)},
                        data={"settings": json.dumps({"layout": "split"})})
    assert r.status_code == 422


def test_rejects_bad_extension_and_reports_failed_download(client):
    assert client.post("/projects/upload", files={"file": ("x.txt", b"oi")}).status_code == 415
    r = client.post("/projects/url", json={"url": "https://invalid.invalid/video"})
    assert r.status_code == 201
    p = client.get(f"/projects/{r.json()['id']}").json()
    assert p["status"] == "failed" and "baixar" in p["error"]


def test_capabilities_and_ranker_per_project(client, sample_video, monkeypatch):
    import httpx

    def down(*a, **k):
        raise httpx.ConnectError("off")

    monkeypatch.setattr(httpx, "get", down)
    monkeypatch.setattr(httpx, "post", down)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    caps = client.get("/capabilities").json()
    assert caps["default_ranker"] == "heuristic" and caps["claude_configured"] is False
    assert caps["ollama"]["online"] is False

    with open(sample_video, "rb") as f:
        r = client.post("/projects/upload", files={"file": ("x.mp4", f)}, data={"settings": json.dumps(
            {"ranker": "ollama", "max_clips": 1, "clip_min_s": 5, "clip_max_s": 10, "game": "Valorant"})})
    p = client.get(f"/projects/{r.json()['id']}").json()
    assert p["status"] == "ready" and p["settings"]["ranker"] == "ollama"
    clip = p["clips"][0]
    assert clip["ranker"] == "heuristic"  # Ollama desligado => caiu para a heurística
    assert clip["hook"] and clip["title"].endswith("| Valorant")

    bad = client.post("/projects/url", json={"url": "https://x.com/v", "settings": {"ranker": "gpt"}})
    assert bad.status_code == 422


def test_serves_static_site_without_shadowing_api(tmp_path, monkeypatch):
    from tests.conftest import _make_client

    site = tmp_path / "site"
    (site / "app").mkdir(parents=True)
    (site / "index.html").write_text("<h1>home</h1>")
    (site / "app" / "index.html").write_text("<h1>painel</h1>")
    monkeypatch.setenv("EZT_WEB_DIR", str(site))
    with _make_client(tmp_path, monkeypatch) as c:
        assert "painel" in c.get("/app/").text
        assert c.get("/health").json() == {"ok": True}
        assert c.get("/projects").json() == []
