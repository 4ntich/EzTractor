"""Detecção pela imagem (vinhetas, telas paradas, tela final, banners) e sinais da audiência."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

FONT = Path(__file__).resolve().parents[2] / "web" / "public" / "fonts" / "Poppins-Bold.ttf"


def _life(seed: int, dur: float) -> str:
    return f"life=s=640x360:seed={seed}:mold=10:r=30:ratio=0.3,scale=1280:720,format=yuv420p,trim=duration={dur}"


@pytest.fixture(scope="module")
def stream_with_vinhetas(tmp_path_factory):
    """jogo 30 s | vinheta 3 s | jogo 30 s | mesma vinheta | jogo 20 s | tela final parada 10 s"""
    d = tmp_path_factory.mktemp("vis")
    card = d / "card.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:d=1",
                    "-frames:v", "1", str(card)], check=True)
    out = d / "live.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", _life(11, 30), "-f", "lavfi", "-i", "mandelbrot=s=1280x720:r=30,format=yuv420p,trim=duration=3",
        "-f", "lavfi", "-i", _life(22, 30), "-f", "lavfi", "-i", "mandelbrot=s=1280x720:r=30,format=yuv420p,trim=duration=3",
        "-f", "lavfi", "-i", _life(33, 20), "-loop", "1", "-t", "10", "-framerate", "30", "-i", str(card),
        "-filter_complex",
        "[0:v]setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[2:v]setpts=PTS-STARTPTS[c];"
        "[3:v]setpts=PTS-STARTPTS[d];[4:v]setpts=PTS-STARTPTS[e];[5:v]scale=1280:720,format=yuv420p,setpts=PTS-STARTPTS[f];"
        "[a][b][c][d][e][f]concat=n=6:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-r", "30", str(out)], check=True)
    return out


def _cats(segs):
    return [(round(s["start"]), round(s["end"]), s["category"]) for s in segs]


def test_finds_repeated_vinhetas_and_end_screen(stream_with_vinhetas):
    from eztractor.pipeline import visual

    vis = visual.extract(stream_with_vinhetas)
    dur = vis.n / visual.FPS
    segs = visual.skip_segments(vis, np.zeros(int(np.ceil(dur))), dur)
    cats = _cats(segs)
    assert (30, 33, "vinheta") in cats and (63, 66, "vinheta") in cats
    assert any(c == "endscreen" and 85 <= a <= 88 and b == 96 for a, b, c in cats)
    # nada marcado dentro dos trechos de jogo
    for a, b, c in cats:
        assert not (a < 29 or 34 < a < 62 or 67 < a < 85), cats
    # a mesma passada também devolve as trocas de cena
    assert [round(t) for t in vis.scene_times][:4] == [30, 33, 63, 66]


def test_speech_protects_repeated_content(stream_with_vinhetas):
    """Se o streamer está falando, não é vinheta (é conteúdo)."""
    from eztractor.pipeline import visual

    vis = visual.extract(stream_with_vinhetas)
    dur = vis.n / visual.FPS
    speech = np.zeros(int(np.ceil(dur)))
    speech[30:34] = 3
    speech[63:67] = 3
    assert not visual.repeated_runs(vis, speech)


def test_continuous_looping_video_is_not_a_vinheta(sample_video):
    """Animação em ciclo sem cortes (ex.: volta 2 de uma corrida) não pode virar vinheta."""
    from eztractor.pipeline import visual

    vis = visual.extract(sample_video)
    assert visual.repeated_runs(vis) == []


# ---------------------------------------------------------------- banners (OCR)
@pytest.fixture(scope="module")
def stream_with_banner(tmp_path_factory):
    out = tmp_path_factory.mktemp("ban") / "banner.mp4"
    f = str(FONT)
    vf = (
        f"drawtext=fontfile={f}:text='twitch.tv/meucanal':x=w-tw-30:y=30:fontsize=30:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=8,"
        f"drawtext=fontfile={f}:text='INSCREVA-SE NO CANAL @OUTROCANAL':x=60:y=h-150:fontsize=44:fontcolor=white:box=1:boxcolor=red@0.9:boxborderw=14:enable='between(t,20,27)',"
        f"drawtext=fontfile={f}:text='Fulano acabou de seguir!':x=(w-tw)/2:y=120:fontsize=40:fontcolor=yellow:box=1:boxcolor=black@0.7:boxborderw=10:enable='between(t,40,44)',"
        f"drawtext=fontfile={f}:text='STORE':x=80:y=300:fontsize=40:fontcolor=white:box=1:boxcolor=blue@0.8:boxborderw=10:enable='between(t,50,55)'"
    )
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", _life(5, 60), "-vf", vf,
                    "-c:v", "libx264", "-preset", "ultrafast", str(out)], check=True)
    return out


def test_banner_found_but_own_overlay_alerts_and_menus_ignored(stream_with_banner):
    pytest.importorskip("rapidocr")
    from eztractor.pipeline import overlays

    segs, stats = overlays.find_banners(stream_with_banner, [(0, 60)], 60.0, 1280, 720, own_names=["meucanal"])
    assert stats["ocr"] and stats["frames"] >= 15
    assert len(segs) == 1, segs
    assert 19 <= segs[0]["start"] <= 21 and 26.5 <= segs[0]["end"] <= 28.5
    assert "OUTROCANAL" in segs[0]["text"].upper()


def test_promo_score():
    from eztractor.pipeline.overlays import promo_score

    assert promo_score("INSCREVA-SE NO CANAL @OUTRO", []) >= 2
    assert promo_score("Use o código GAMER10 e ganhe 10% OFF", []) >= 2
    assert promo_score("youtube.com/@outro", []) >= 2
    assert promo_score("STORE", []) < 2 and promo_score("CANAL", []) < 2
    assert promo_score("Fulano acabou de seguir!", []) == 0
    assert promo_score("Obrigado pelo sub, Ciclano!", []) == 0
    assert promo_score("@meucanal", ["meucanal"]) < 2  # o próprio canal não é propaganda


# ---------------------------------------------------------------- audiência
def _chat_line(t_ms: int, text: str) -> str:
    return json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(t_ms), "actions": [
        {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {"message": {"runs": [{"text": text}]}}}}}]}})


def test_parse_youtube_chat_and_signal(tmp_path):
    from eztractor.pipeline import audience

    lines = [_chat_line(i * 4000, "boa") for i in range(150)]  # ~1 msg a cada 4 s (normal)
    lines += [_chat_line(301_000 + i * 100, "KKKKKKK" if i % 2 else "POG") for i in range(80)]  # explosão em 301-309 s
    lines.append("lixo que não é json")
    p = tmp_path / "chat.live_chat.json"
    p.write_text("\n".join(lines), encoding="utf-8")
    msgs = audience.parse_youtube_chat(p)
    assert len(msgs) == 230
    pc = audience.chat_per_second(msgs, 600)
    assert pc["total"] == 230 and sum(pc["fun"]) == 80
    z, fun = audience.chat_signal(np.array(pc["msgs"]), np.array(pc["fun"]))
    # o lance aconteceu ANTES do chat reagir: o sinal aparece alguns segundos antes de 301 s
    assert int(np.argmax(z)) < 301 and z[295] > 5 and fun[295] > 0.9
    assert z[100] < 1


def test_heatmap():
    from eztractor.pipeline import audience

    hm = [{"start_time": i * 10, "end_time": (i + 1) * 10, "value": 0.2} for i in range(60)]
    hm[42]["value"] = 1.0
    heat = audience.heat_relative(audience.heatmap_per_second(hm, 600))
    assert heat[425] == 1.0 and heat[100] == 0.0
    assert audience.heatmap_per_second(None, 600) is None


def test_chat_spike_picks_the_clip_even_with_flat_audio(tmp_path):
    """O público manda: o pico do chat vira o melhor clipe mesmo sem grito no áudio."""
    from eztractor.pipeline import audience
    from eztractor.pipeline.candidates import generate
    from eztractor.pipeline.signals import Signals

    n = 900
    msgs = np.full(n, 0.3)
    msgs[606:616] = 12  # chat explode em ~606 s (lance em ~600 s)
    fun = np.zeros(n)
    fun[606:616] = 9
    sig = Signals(np.zeros(n, np.float32), np.zeros(n), np.zeros(n), np.zeros(n))
    sig.audio_z[200:205] = 2.5  # um grito comum em outro lugar
    sig.chat_z, sig.chat_fun = audience.chat_signal(msgs, fun)
    best = generate(sig, n, [], 15, 30, limit=3)[0]
    assert best.start <= 600 <= best.end, (best.start, best.end)
    assert best.stats["chat_peak_z"] > 5 and best.stats["chat_fun"] > 0.5


def test_clip_starts_at_sentence_and_ends_after_it():
    from eztractor.pipeline.candidates import refine_bounds

    words = [{"w": "eu", "start": 10.0, "end": 10.3}, {"w": "vou", "start": 10.4, "end": 10.7},
             {"w": "lá", "start": 10.8, "end": 11.0},  # frase 1 (começa em 10 s)
             {"w": "e", "start": 12.5, "end": 12.6}, {"w": "matei", "start": 12.7, "end": 13.2},
             {"w": "todo", "start": 13.3, "end": 13.6}, {"w": "mundo", "start": 31.0, "end": 33.5}]  # termina em 33,5
    s, e = refine_bounds(11.5, 31.5, words, [], 120, 10, 45)
    assert s == pytest.approx(9.75) or s == pytest.approx(12.25)  # começo de frase, não no meio
    assert e == pytest.approx(33.9)  # espera a frase "mundo" acabar (+0,4 s de respiro)


def test_pipeline_never_shows_banner_even_in_the_loudest_moment(client, tmp_path):
    pytest.importorskip("rapidocr")
    f = str(FONT)
    video = tmp_path / "live.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=90",
        "-f", "lavfi", "-i", "aevalsrc='0.02*sin(2*PI*440*t)+if(between(t,40,45),0.9*sin(2*PI*880*t),0)':s=44100:d=90",
        "-vf", f"drawtext=fontfile={f}:text='SIGA @OUTROCANAL NO TIKTOK':x=60:y=h-150:fontsize=44:fontcolor=white:"
               f"box=1:boxcolor=red@0.9:boxborderw=14:enable='between(t,38,47)'",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(video)], check=True)
    with open(video, "rb") as fh:
        p = client.post("/projects/upload", files={"file": ("live.mp4", fh, "video/mp4")},
                        data={"title": "t", "settings": json.dumps({"render_height": 640, "max_clips": 3,
                                                                    "clip_min_s": 10, "clip_max_s": 20})}).json()
    import time
    for _ in range(600):
        p = client.get(f"/projects/{p['id']}").json()
        if p["status"] in ("ready", "failed"):
            break
        time.sleep(0.3)
    assert p["status"] == "ready", p["error"]
    banners = [s for s in p["skip_segments"] if "banner" in s["category"]]
    assert banners and banners[0]["start"] <= 38.6 and banners[0]["end"] >= 46.4, p["skip_segments"]
    assert p["settings"]["analysis"]["ocr_frames"] > 0 and p["settings"]["analysis"]["skips"]["banner"] >= 1
    b0, b1 = banners[0]["start"], banners[0]["end"]
    for c in p["clips"]:
        visible = (min(c["end_s"], b1) - max(c["start_s"], b0)) - sum(
            max(0, min(y, b1) - max(x, b0)) for x, y in c["cuts"])
        assert visible <= 0.5, (c["start_s"], c["end_s"], c["cuts"])
