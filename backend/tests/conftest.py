import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory) -> Path:
    """Vídeo de 60s com áudio baixo e um "grito" (pico) entre 30s e 35s, mais trocas de cena."""
    out = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=60",
        "-f", "lavfi", "-i",
        "aevalsrc='0.02*sin(2*PI*440*t)+if(between(t,30,35),0.8*sin(2*PI*880*t),0)':s=44100:d=60",
        "-vf", "hue=h='if(between(t,31,34),mod(t*400,360),0)'",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(out),
    ], check=True)
    return out


def _make_client(tmp_path, monkeypatch, password: str = ""):
    monkeypatch.setenv("EZT_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("EZT_STORAGE_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EZT_QUEUE_MODE", "sync")
    monkeypatch.setenv("EZT_TRANSCRIBER", "none")
    monkeypatch.setenv("EZT_RANKER", "heuristic")
    monkeypatch.setenv("EZT_RENDER_HEIGHT", "1280")
    monkeypatch.setenv("EZT_APP_PASSWORD", password)

    from eztractor import config, db

    config.get_settings.cache_clear()
    db.reset_engine()
    from eztractor.api.main import create_app

    return TestClient(create_app())


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from eztractor import config, db

    with _make_client(tmp_path, monkeypatch) as c:
        yield c
    db.reset_engine()
    config.get_settings.cache_clear()


@pytest.fixture()
def locked_client(tmp_path, monkeypatch):
    from eztractor import config, db

    with _make_client(tmp_path, monkeypatch, password="minha-senha") as c:
        yield c
    db.reset_engine()
    config.get_settings.cache_clear()
