import json
import subprocess
import threading
import time

import pytest


def _upload(client, video, settings: dict, title: str = "") -> dict:
    with open(video, "rb") as f:
        r = client.post("/projects/upload", files={"file": ("live.mp4", f, "video/mp4")},
                        data={"title": title, "settings": json.dumps(settings)})
    assert r.status_code == 201, r.text
    return r.json()


def _wait(client, pid, statuses, timeout=90):
    end = time.time() + timeout
    p = {}
    while time.time() < end:
        p = client.get(f"/projects/{pid}").json()
        if p["status"] in statuses:
            return p
        time.sleep(0.2)
    raise AssertionError(f"tempo esgotado esperando {statuses}: {p.get('status')} {p.get('stage')}")


@pytest.fixture(scope="module")
def long_video(tmp_path_factory):
    out = tmp_path_factory.mktemp("long") / "long.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=240",
        "-f", "lavfi", "-i", "aevalsrc='0.02*sin(2*PI*440*t)+if(between(t,100,104),0.8*sin(2*PI*880*t),0)':s=44100:d=240",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


# ---------------------------------------------------------------- pausar / continuar / cancelar
def test_pause_resume_and_cancel_while_processing(client, long_video, monkeypatch):
    from eztractor import config

    monkeypatch.setenv("EZT_QUEUE_MODE", "inline")  # processamento numa thread, como no app real
    config.get_settings.cache_clear()
    settings = {"max_clips": 3, "clip_min_s": 8, "clip_max_s": 15, "render_height": 1280}

    p = _upload(client, long_video, settings)
    pid = p["id"]
    assert client.post(f"/projects/{pid}/pause").json()["control"] == "pause"
    paused = _wait(client, pid, {"paused"})
    time.sleep(1.5)
    still = client.get(f"/projects/{pid}").json()
    assert still["status"] == "paused" and still["progress"] == paused["progress"]  # parado de verdade
    assert client.delete(f"/projects/{pid}").status_code == 409  # não exclui no meio

    assert client.post(f"/projects/{pid}/resume").status_code == 200
    done = _wait(client, pid, {"ready", "failed"})
    assert done["status"] == "ready", done["error"]
    assert done["clips"] and all(c["render_status"] == "ready" for c in done["clips"])

    # cancelar no meio
    p2 = _upload(client, long_video, settings)
    time.sleep(0.3)
    assert client.post(f"/projects/{p2['id']}/cancel").status_code == 200
    t0 = time.time()
    cancelled = _wait(client, p2["id"], {"cancelled", "ready", "failed"}, timeout=30)
    assert cancelled["status"] == "cancelled" and time.time() - t0 < 10
    assert all(c["render_status"] == "ready" for c in cancelled["clips"])  # incompletos descartados
    assert client.post(f"/projects/{p2['id']}/cancel").status_code == 409

    # reprocessar depois de cancelar funciona
    assert client.post(f"/projects/{p2['id']}/reprocess").status_code == 200
    assert _wait(client, p2["id"], {"ready", "failed"})["status"] == "ready"
    assert client.delete(f"/projects/{p2['id']}").status_code == 204
    config.get_settings.cache_clear()


def test_cancel_kills_running_ffmpeg(client, tmp_path):
    """O cancelamento encerra o ffmpeg em andamento (não espera ele terminar)."""
    from eztractor.control import Cancelled, Control, activate
    from eztractor.db import session_factory
    from eztractor.models import Project
    from eztractor.pipeline.media import run

    with session_factory()() as db:
        p = Project(title="x", source_type="upload", control="run")
        db.add(p)
        db.commit()
        pid = p.id
    errors = []

    def work():
        token = activate(Control(pid))
        try:  # ~20 s de trabalho em tempo real (-re)
            run(["ffmpeg", "-y", "-v", "error", "-re", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=20",
                 "-f", "null", "-"])
        except Cancelled:
            errors.append("cancelado")
        finally:
            from eztractor.control import _current
            _current.reset(token)

    t = threading.Thread(target=work)
    t0 = time.time()
    t.start()
    time.sleep(1)
    with session_factory()() as db:
        db.get(Project, pid).control = "cancel"
        db.commit()
    t.join(timeout=10)
    assert errors == ["cancelado"] and time.time() - t0 < 6


def test_interrupted_projects_are_recovered_on_startup(client):
    from eztractor.api.main import recover_interrupted
    from eztractor.config import get_settings
    from eztractor.db import session_factory
    from eztractor.models import Project

    with session_factory()() as db:
        p = Project(title="x", source_type="upload", status="processing")
        db.add(p)
        db.commit()
        pid = p.id
    get_settings().queue_mode = "inline"
    try:
        recover_interrupted()
    finally:
        get_settings().queue_mode = "sync"
    p = client.get(f"/projects/{pid}").json()
    assert p["status"] == "failed" and "Reprocessar" in p["error"]


# ---------------------------------------------------------------- só baixar
def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format",
                          str(path)], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    return v["width"], v["height"], float(data["format"]["duration"])


def test_download_only_without_template(client, sample_video):
    p = _upload(client, sample_video, {"mode": "download"}, title="Minha Live: parte 1/2")
    p = client.get(f"/projects/{p['id']}").json()
    assert p["status"] == "ready" and p["settings"]["mode"] == "download"
    assert len(p["clips"]) == 1 and p["clips"][0]["end_s"] == 60  # vídeo inteiro, editável
    from eztractor.db import session_factory
    from eztractor.models import Clip, Project

    with session_factory()() as db:  # sem cortes e sem template: usa o próprio arquivo (sem reconverter)
        assert db.get(Clip, p["clips"][0]["id"]).render_key == db.get(Project, p["id"]).source_key
    r = client.get(p["source_file_url"])
    assert r.status_code == 200 and len(r.content) > 10_000
    assert "attachment" in r.headers["content-disposition"]
    from urllib.parse import unquote

    assert unquote(r.headers["content-disposition"]).endswith("Minha Live parte 1 2.mp4")


def test_download_only_with_template_renders_whole_video(client, sample_video):
    from eztractor.presets import PRESETS
    from eztractor import storage
    from eztractor.db import session_factory
    from eztractor.models import Clip

    tpl = client.post("/templates", json={"name": "T", "config": PRESETS[0]["config"]}).json()
    p = _upload(client, sample_video, {"mode": "download", "template_id": tpl["id"], "render_height": 640})
    p = client.get(f"/projects/{p['id']}").json()
    assert p["status"] == "ready", p["error"]
    assert len(p["clips"]) == 1
    c = p["clips"][0]
    assert c["start_s"] == 0 and abs(c["end_s"] - 60) < 0.5
    with session_factory()() as db:
        key = db.get(Clip, c["id"]).render_key
    w, h, dur = _probe(storage.path_for(key))
    assert (w, h) == (360, 640) and abs(dur - 60) < 1

    # tirar o template depois: volta a ser o arquivo original (mesmo clipe, sem reconverter)
    client.post(f"/projects/{p['id']}/apply-template", json={"template_id": None})
    after = client.get(f"/projects/{p['id']}").json()["clips"]
    assert len(after) == 1 and after[0]["id"] == c["id"] and after[0]["render_status"] == "ready"


@pytest.mark.parametrize("height,size", [(854, (480, 854)), (1920, (1080, 1920))])
def test_render_quality_per_project(client, sample_video, height, size):
    from eztractor import storage
    from eztractor.db import session_factory
    from eztractor.models import Clip

    p = _upload(client, sample_video, {"max_clips": 1, "clip_min_s": 5, "clip_max_s": 6, "render_height": height})
    p = client.get(f"/projects/{p['id']}").json()
    with session_factory()() as db:
        key = db.get(Clip, p["clips"][0]["id"]).render_key
    assert _probe(storage.path_for(key))[:2] == size


def test_invalid_quality_rejected(client):
    r = client.post("/projects/url", json={"url": "https://x.invalid/v", "settings": {"render_height": 999}})
    assert r.status_code == 422
    r = client.post("/projects/url", json={"url": "https://x.invalid/v", "settings": {"download_height": 123}})
    assert r.status_code == 422
    caps = client.get("/capabilities").json()
    assert caps["default_render_height"] == 1280


# ---------------------------------------------------------------- edição: aparar e cortar
def test_trim_and_cut_rendered_clip(client, sample_video):
    from eztractor import storage
    from eztractor.db import session_factory
    from eztractor.models import Clip

    p = _upload(client, sample_video, {"max_clips": 1, "clip_min_s": 10, "clip_max_s": 15, "render_height": 640})
    c = client.get(f"/projects/{p['id']}").json()["clips"][0]
    s0 = c["start_s"]
    r = client.patch(f"/clips/{c['id']}", json={"start_s": s0, "end_s": s0 + 12, "cuts": [[s0 + 3, s0 + 7]]})
    assert r.status_code == 200, r.text
    c2 = client.get(f"/projects/{p['id']}").json()["clips"][0]
    assert c2["render_status"] == "ready" and c2["cuts"] == [[round(s0 + 3, 2), round(s0 + 7, 2)]]
    with session_factory()() as db:
        key = db.get(Clip, c["id"]).render_key
    assert abs(_probe(storage.path_for(key))[2] - 8) < 0.4  # 12 s - 4 s cortados

    bad = [
        {"cuts": [[s0 - 5, s0 + 1]]},  # fora do trecho
        {"cuts": [[s0 + 1, s0 + 5], [s0 + 4, s0 + 6]]},  # sobrepostos
        {"start_s": s0, "end_s": s0 + 0.5, "cuts": []},  # vazio
    ]
    for b in bad:
        assert client.patch(f"/clips/{c['id']}", json=b).status_code == 422, b


def test_download_mode_cuts_whole_video_and_long_trim_allowed(client, sample_video):
    from eztractor import storage
    from eztractor.db import session_factory
    from eztractor.models import Clip

    p = _upload(client, sample_video, {"mode": "download"})
    c = client.get(f"/projects/{p['id']}").json()["clips"][0]
    r = client.patch(f"/clips/{c['id']}", json={"start_s": 2, "end_s": 58, "cuts": [[10, 20], [30, 35]]})
    assert r.status_code == 200, r.text
    with session_factory()() as db:
        key = db.get(Clip, c["id"]).render_key
    w, h, dur = _probe(storage.path_for(key))
    assert (w, h) == (1280, 720) and abs(dur - 41) < 0.5  # mantém o formato original; 56 s - 15 s


def test_ads_detected_from_transcript_are_skipped():
    from eztractor.ads import cuts_within, from_transcript, merge

    words = []
    t = 0.0
    for w in ("galera hoje o vídeo é patrocinado pela loja X use o código EZ").split():
        words.append({"w": w, "start": 40 + t, "end": 40.3 + t})
        t += 0.4
    for w in "valeu galera até o próximo vídeo".split():
        words.append({"w": w, "start": 570 + t, "end": 570.3 + t})
        t += 0.4
    segs = from_transcript(words, 600)
    cats = {s["category"] for s in segs}
    assert "sponsor" in cats and "outro" in cats
    outro = next(s for s in segs if s["category"] == "outro")
    assert outro["end"] == 600  # corta até o fim (tela final com outros canais)
    assert merge([{"start": 0, "end": 5, "category": "a", "reason": "A"},
                  {"start": 6, "end": 9, "category": "b", "reason": "B"}])[0]["end"] == 9
    assert cuts_within(30, 50, segs)  # um clipe que encosta no patrocínio recebe corte


def test_candidates_avoid_skip_segments():
    import numpy as np

    from eztractor.pipeline.candidates import generate
    from eztractor.pipeline.signals import Signals

    n = 300
    audio = np.zeros(n, dtype=np.float32)
    audio[100:106] = 4.0  # momento forte...
    audio[200:206] = 3.0
    sig = Signals(audio, np.zeros(n), np.zeros(n), np.zeros(n))
    skips = [{"start": 95, "end": 110, "category": "sponsor", "reason": "x"}]  # ...dentro de um patrocínio
    for c in generate(sig, n, [], 8, 15, limit=4, excluded=skips):
        assert c.end <= 95 or c.start >= 110, (c.start, c.end)


def test_sponsorblock_segments(monkeypatch):
    import httpx

    from eztractor.ads import from_sponsorblock

    def fake_get(url, params=None, timeout=None):
        assert "videoID" in params
        return httpx.Response(200, json=[{"segment": [12.5, 40.0], "category": "sponsor"},
                                         {"segment": [580, 600], "category": "outro"}],
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    segs = from_sponsorblock("abc", 600)
    assert [(s["start"], s["end"], s["reason"]) for s in segs] == [(12.5, 40.0, "Patrocínio"), (580, 600, "Final do vídeo")]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("off")))
    assert from_sponsorblock("abc", 600) == []


def test_download_all_clips_as_zip(client, sample_video):
    import io
    import zipfile

    p = _upload(client, sample_video, {"render_height": 640, "max_clips": 3, "min_duration_s": 10, "max_duration_s": 15},
                title="Live: sexta/à noite")
    p = _wait(client, p["id"], {"ready", "failed"})
    assert p["status"] == "ready", p["error"]
    ready = [c for c in p["clips"] if c["render_status"] == "ready"]
    assert len(ready) >= 2

    link = client.get(f"/projects/{p['id']}/download-all").json()
    assert link["count"] == len(ready) and link["url"].startswith(f"/zips/{p['id']}?sig=")
    r = client.get(link["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "clipes.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    videos = [n for n in z.namelist() if n.endswith(".mp4")]
    texts = [n for n in z.namelist() if n.endswith(".txt")]
    assert len(videos) == len(ready) and videos[0].startswith("01 - ") and len(set(videos)) == len(videos)
    # cada vídeo tem a legenda + hashtags ao lado, com o mesmo nome
    assert sorted(t[:-4] for t in texts) == sorted(v[:-4] for v in videos)
    first = z.read(texts[0] if texts[0].startswith("01 - ") else sorted(texts)[0]).decode("utf-8-sig").strip()
    assert first == p["clips"][0]["social_text"] and "#" in first

    # link adulterado ou de outro projeto não funciona
    assert client.get(link["url"] + "x").status_code == 403
    assert client.get(link["url"].replace(p["id"], "outro")).status_code == 403
