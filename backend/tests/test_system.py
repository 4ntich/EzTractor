import json

import pytest


@pytest.fixture()
def desktop(tmp_path, monkeypatch):
    """Simula o app Windows: senha + confiança no localhost + config.env."""
    from tests.conftest import _make_client
    from eztractor import config, db

    cfg = tmp_path / "config.env"
    cfg.write_text("# comentário\nEZT_RANKER=heuristic\nEZT_LAN_ACCESS=0\n", encoding="utf-8")
    monkeypatch.setenv("EZT_TRUST_LOCALHOST", "1")
    monkeypatch.setenv("EZT_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("EZT_APP_VERSION", "0.7.0")
    with _make_client(tmp_path, monkeypatch, password="segredo1") as c:
        yield c, cfg
    db.reset_engine()
    config.get_settings.cache_clear()


def test_local_window_needs_no_login_but_phone_does(desktop):
    from starlette.testclient import TestClient

    c, _ = desktop
    # TestClient conecta como "testclient"; forçamos o IP via transport scope
    local = TestClient(c.app, client=("127.0.0.1", 5000))
    phone = TestClient(c.app, client=("192.168.0.50", 5000))
    assert local.get("/auth/status").json() == {"password_required": False}
    assert local.get("/projects").status_code == 200
    assert phone.get("/auth/status").json() == {"password_required": True}
    assert phone.get("/projects").status_code == 401
    tok = phone.post("/auth/login", json={"password": "segredo1"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert phone.get("/projects", headers=h).status_code == 200
    # celular logado não pode mudar configurações do PC
    assert phone.post("/system/lan", json={"enabled": False}, headers=h).status_code == 403
    assert phone.post("/system/update/install", headers=h).status_code == 403


def test_enable_lan_writes_config_and_requires_password(desktop):
    from starlette.testclient import TestClient

    c, cfg = desktop
    local = TestClient(c.app, client=("127.0.0.1", 5000))
    assert local.post("/system/lan", json={"enabled": True, "password": "123"}).status_code == 422
    r = local.post("/system/lan", json={"enabled": True, "password": "minhasenha"})
    assert r.status_code == 200 and r.json()["restart_required"]
    text = cfg.read_text(encoding="utf-8")
    assert "# comentário" in text and "EZT_LAN_ACCESS=1" in text and "EZT_APP_PASSWORD=minhasenha" in text
    assert "EZT_RANKER=heuristic" in text
    info = local.get("/system/info").json()
    assert info["version"] == "0.7.0" and info["lan"]["configurable"] and info["is_local"]
    assert local.get("/system/qr.svg", params={"data": "http://192.168.0.2:8765/app/"}).text.startswith("<svg")


def test_update_check_and_versions(desktop, monkeypatch):
    import httpx

    from eztractor import updater

    from starlette.testclient import TestClient

    c = TestClient(desktop[0].app, client=("127.0.0.1", 5000))
    updater._cache.update(at=0.0, data=None)
    assert updater.parse_version("0.10.0") > updater.parse_version("0.9.9")
    assert updater.parse_version("0.8.0") > updater.parse_version("0.8.0-dev.3")

    def fake_get(url, **kw):
        return httpx.Response(200, json={
            "tag_name": "v0.8.0", "body": "novidades", "html_url": "https://x/rel",
            "assets": [{"name": "EzTractor-Setup-0.8.0.exe", "browser_download_url": "https://x/s.exe",
                        "size": 123, "digest": "sha256:" + "a" * 64}]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    r = c.get("/system/update", params={"force": True}).json()
    assert r["available"] and r["latest"] == "0.8.0" and r["current"] == "0.7.0" and r["sha256"] == "a" * 64
    assert r["can_install"] is False  # nos testes não é o app Windows

    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("off")))
    updater._cache.update(at=0.0, data=None)
    r = c.get("/system/update", params={"force": True}).json()
    assert r["available"] is False and "verificar" in r["error"]
