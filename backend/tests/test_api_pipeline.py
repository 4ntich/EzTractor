import json
import subprocess


def _probe(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")


def test_auth_flow(client):
    r = client.post("/auth/register", json={"email": "A@B.com", "password": "12345678"})
    assert r.status_code == 201
    assert client.post("/auth/register", json={"email": "a@b.com", "password": "12345678"}).status_code == 409
    assert client.post("/auth/login", json={"email": "a@b.com", "password": "errada!!"}).status_code == 401
    tok = client.post("/auth/login", json={"email": "a@b.com", "password": "12345678"}).json()["token"]
    me = client.get("/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["credits"] == 120 and me["plan"] == "free"
    assert client.get("/me").status_code == 401


def test_upload_generates_ranked_vertical_clips(client, auth, sample_video):
    settings = {"clip_min_s": 8, "clip_max_s": 15, "max_clips": 3}
    with open(sample_video, "rb") as f:
        r = client.post("/projects/upload", headers=auth, files={"file": ("live.mp4", f, "video/mp4")},
                        data={"title": "Live teste", "settings": json.dumps(settings)})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    p = client.get(f"/projects/{pid}", headers=auth).json()
    assert p["status"] == "ready", p["error"]
    assert p["credits_charged"] == 1
    assert 1 <= len(p["clips"]) <= 3
    top = p["clips"][0]
    # o clipe mais bem ranqueado precisa conter o pico de áudio (30–35s)
    assert top["start_s"] <= 33 <= top["end_s"], top
    assert all(7.99 <= c["end_s"] - c["start_s"] <= 15.5 for c in p["clips"]), p["clips"]
    assert [c["score"] for c in p["clips"]] == sorted((c["score"] for c in p["clips"]), reverse=True)

    # vídeo vertical 720x1280 (plano free) servido por URL assinada
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

    me = client.get("/me", headers=auth).json()
    assert me["credits"] == 119

    # edição re-renderiza
    r = client.patch(f"/clips/{top['id']}", headers=auth, json={"start_s": 29, "end_s": 37, "hook": "OLHA ISSO"})
    assert r.status_code == 200 and r.json()["render_status"] == "ready"
    assert client.patch(f"/clips/{top['id']}", headers=auth, json={"start_s": 50, "end_s": 40}).status_code == 422


def test_split_layout_requires_facecam(client, auth, sample_video):
    with open(sample_video, "rb") as f:
        r = client.post("/projects/upload", headers=auth, files={"file": ("x.mp4", f)},
                        data={"settings": json.dumps({"layout": "split"})})
    assert r.status_code == 422


def test_other_users_cannot_see_project(client, auth, sample_video):
    with open(sample_video, "rb") as f:
        pid = client.post("/projects/upload", headers=auth, files={"file": ("x.mp4", f)},
                          data={"settings": json.dumps({"max_clips": 1, "clip_min_s": 5, "clip_max_s": 10})}).json()["id"]
    other = client.post("/auth/register", json={"email": "z@z.com", "password": "12345678"}).json()["token"]
    h2 = {"Authorization": f"Bearer {other}"}
    assert client.get(f"/projects/{pid}", headers=h2).status_code == 404
    assert client.get("/projects", headers=h2).json() == []
    assert client.delete(f"/projects/{pid}", headers=h2).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=auth).status_code == 204


def test_rejects_bad_extension_and_failed_download_refunds(client, auth):
    r = client.post("/projects/upload", headers=auth, files={"file": ("x.txt", b"oi")})
    assert r.status_code == 415
    r = client.post("/projects/url", headers=auth, json={"url": "https://invalid.invalid/video"})
    assert r.status_code == 201
    p = client.get(f"/projects/{r.json()['id']}", headers=auth).json()
    assert p["status"] == "failed" and p["credits_charged"] == 0
    assert client.get("/me", headers=auth).json()["credits"] == 120
