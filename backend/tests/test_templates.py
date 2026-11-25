import json
import subprocess

import pytest

from eztractor.fonts import FONTS, font_file
from eztractor.pipeline.template_render import (
    ass_color, build_template_ass, fill_vars, frame_bars, normalize, output_size, wrap_text,
)
from eztractor.presets import PRESETS
from eztractor.schemas import TemplateConfig


def _probe_video(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")


def _cfg(**kw) -> dict:
    return TemplateConfig(**kw).model_dump()


def _layer(**kw) -> dict:
    base = {"id": "l1", "text": "Olá"}
    base.update(kw)
    return base


# ---------------------------------------------------------------- unidades
def test_all_font_files_exist():
    for key in FONTS:
        assert font_file(key, False) is not None, key


def test_fill_vars():
    ctx = {"titulo": "Ace", "numero": 2, "jogo": ""}
    assert fill_vars("TOP {numero}: {titulo}", ctx) == "TOP 2: Ace"
    assert fill_vars("{jogo} parte {numero}", ctx) == "parte 2"  # variável vazia não deixa espaço sobrando
    assert fill_vars("{desconhecida} ok", ctx) == "{desconhecida} ok"
    assert fill_vars("{TITULO}", ctx) == "Ace"


def test_ass_color_and_alpha():
    assert ass_color("#FF8000") == "&H000080FF"
    assert ass_color("#FFFFFF", 0) == "&HFFFFFFFF"
    assert ass_color("#000000", 50) == "&H80000000"


def test_wrap_respects_width_and_manual_breaks():
    lines = wrap_text("um texto bem comprido que precisa quebrar em varias linhas", "anton", False, 80, 500)
    assert len(lines) > 1
    assert wrap_text("linha um\nlinha dois", "sans", False, 20, 2000) == ["linha um", "linha dois"]


def test_layer_style_box_outline_and_animations():
    cfg = _cfg(layers=[
        _layer(id="a", text="{titulo}", x=10, y=80, align="left", backgroundEnabled=True,
               backgroundColor="#E11D48", backgroundPadding=12, animation="slide-left"),
        _layer(id="b", text="tipo", outlineWidth=5, glow=True, animation="typewriter"),
        _layer(id="c", text="FIM", showMode="end", showSeconds=3, animation="pop"),
        _layer(id="d", text="{jogo}"),  # vazio => sem evento
    ])
    ass = build_template_ass(cfg, [], 100.0, 120.0, {"titulo": "Clutch", "jogo": ""})
    styles = [ln for ln in ass.splitlines() if ln.startswith("Style: L")]
    assert ",3,12.0," in styles[0]  # caixa: BorderStyle 3 com padding 12
    assert ",1,5.0," in styles[1]  # contorno 5
    events = [ln for ln in ass.splitlines() if ln.startswith("Dialogue")]
    assert len(events) == 3
    assert "\\move(" in events[0] and "Clutch" in events[0] and ",4,0,0,0,1" in styles[0]  # \an4 = esquerda
    assert "\\ko" in events[1] and "\\blur6" in events[1]
    assert events[2].startswith("Dialogue: 12,0:00:17.00,0:00:20.00")  # só nos últimos 3 s


def test_preview_mode_shows_every_layer_full_time():
    cfg = _cfg(layers=[_layer(text="FIM", showMode="end", showSeconds=2, animation="typewriter")])
    ass = build_template_ass(cfg, [], 0, 10, {}, preview=True)
    ev = next(ln for ln in ass.splitlines() if ln.startswith("Dialogue"))
    assert ev.startswith("Dialogue: 10,0:00:00.00,0:00:10.00") and "\\ko" not in ev


def test_template_captions_highlight_current_word():
    cfg = _cfg(captions={"highlightColor": "#00FF00", "wordsPerLine": 2, "uppercase": True})
    words = [{"w": "bora", "start": 1.0, "end": 1.3}, {"w": "time", "start": 1.4, "end": 1.7},
             {"w": "fora", "start": 50.0, "end": 50.2}]
    ass = build_template_ass(cfg, words, 0.0, 10.0, {}, captions=True)
    caps = [ln for ln in ass.splitlines() if ",Cap," in ln and ln.startswith("Dialogue")]
    assert len(caps) == 2 and "\\1c&H0000FF00" in caps[0] and "BORA" in caps[0]
    assert "fora" not in ass.lower().split("[events]")[1]


def test_frame_bars_and_output_size():
    cfg = _cfg(frame={"headerBorder": True, "footerBorder": True, "sideBorders": True, "color": "#123456",
                      "headerHeightPercent": 10, "footerHeightPercent": 5, "sideWidthPercent": 2})
    bars = frame_bars(cfg, 1080, 1920)
    assert {(b["y"], b["h"]) for b in bars[:2]} == {(0, 192), (1824, 96)} and bars[2]["w"] == 22
    assert output_size(_cfg(), 1920) == (1080, 1920)
    assert output_size(_cfg(width=1920, height=1080), 1280) == (1280, 720)
    assert output_size(_cfg(width=1080, height=1080), 1920) == (1080, 1080)  # não aumenta além do template


def test_normalize_fills_new_fields_for_old_templates():
    old = {"width": 1080, "height": 1920, "layers": [{"id": "x", "text": "a", "fontFamily": "serif"}]}
    n = normalize(old)
    assert n["captions"]["fontFamily"] == "anton" and n["layers"][0]["animation"] == "none"


def test_rejects_unknown_font():
    with pytest.raises(Exception):
        TemplateConfig(layers=[{"id": "x", "fontFamily": "comic-sans"}])


@pytest.mark.parametrize("preset", PRESETS, ids=[p["key"] for p in PRESETS])
def test_every_preset_renders(preset, tmp_path, sample_video):
    from eztractor.pipeline.template_render import render_preview

    out = render_preview(preset["config"], tmp_path / "p.jpg", tmp_path, src=sample_video, at_s=5,
                         src_w=1280, src_h=720, max_side=640)
    assert out.exists() and out.stat().st_size > 5000


# ---------------------------------------------------------------- API
def test_template_crud_default_and_options(client):
    opts = client.get("/template-options").json()
    assert len(opts["fonts"]) == len(FONTS) and "titulo" in opts["variables"]
    presets = client.get("/template-presets").json()
    assert len(presets) == len(PRESETS)

    a = client.post("/templates", json={"name": "Meu", "config": presets[0]["config"], "is_default": True}).json()
    b = client.post("/templates", json={"name": "Outro", "config": presets[1]["config"], "is_default": True}).json()
    rows = client.get("/templates").json()
    assert [r["is_default"] for r in rows if r["id"] == a["id"]] == [False]  # só um padrão
    assert rows[0]["id"] == b["id"]

    upd = client.put(f"/templates/{a['id']}", json={"name": "Renomeado", "config": a["config"]}).json()
    assert upd["name"] == "Renomeado"
    assert client.post("/templates", json={"name": " ", "config": {}}).status_code == 422
    assert client.post("/templates", json={"name": "x" * 61, "config": {}}).status_code == 422
    assert client.delete(f"/templates/{a['id']}").status_code == 204
    assert client.put(f"/templates/{a['id']}", json={"name": "x", "config": {}}).status_code == 404


def test_preview_endpoint_returns_jpeg(client):
    r = client.post("/templates/preview", json={"config": PRESETS[0]["config"]})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"


def test_project_uses_default_template_and_apply_to_all(client, sample_video):
    square = next(p for p in PRESETS if p["key"] == "feed-quadrado")["config"]
    tpl = client.post("/templates", json={"name": "Quadrado", "config": square, "is_default": True}).json()

    with open(sample_video, "rb") as f:
        r = client.post("/projects/upload", files={"file": ("x.mp4", f)}, data={"settings": json.dumps(
            {"max_clips": 2, "clip_min_s": 5, "clip_max_s": 10})})
    p = client.get(f"/projects/{r.json()['id']}").json()
    assert p["status"] == "ready" and p["settings"]["template_id"] == tpl["id"]  # padrão aplicado sozinho

    from eztractor import storage
    from eztractor.db import session_factory
    from eztractor.models import Clip

    def clip_size(cid):
        with session_factory()() as db:
            s = _probe_video(storage.path_for(db.get(Clip, cid).render_key))
        return s["width"], s["height"]

    assert clip_size(p["clips"][0]["id"]) == (1080, 1080)

    # trocar para "sem template" re-renderiza todos no formato vertical padrão (720x1280 nos testes)
    r = client.post(f"/projects/{p['id']}/apply-template", json={"template_id": None})
    assert r.status_code == 200
    p = client.get(f"/projects/{p['id']}").json()
    assert p["settings"]["template_id"] is None
    assert all(c["render_status"] == "ready" for c in p["clips"])
    assert clip_size(p["clips"][0]["id"]) == (720, 1280)

    assert client.post(f"/projects/{p['id']}/apply-template", json={"template_id": "nao-existe"}).status_code == 404


def test_explicit_no_template_and_invalid_template(client, sample_video):
    client.post("/templates", json={"name": "Padrão", "config": PRESETS[0]["config"], "is_default": True})
    bad = client.post("/projects/url", json={"url": "https://x.invalid/v", "settings": {"template_id": "zzz"}})
    assert bad.status_code == 422
    r = client.post("/projects/url", json={"url": "https://x.invalid/v", "settings": {"template_id": None}})
    assert r.json()["settings"]["template_id"] is None


def test_template_render_has_progress_bar_and_frame(tmp_path, sample_video):
    """Render real de um clipe com moldura + barra de progresso + legendas: confere pixels."""
    from PIL import Image

    from eztractor.pipeline.captions import write_ass
    from eztractor.pipeline.render import render_clip
    from eztractor.pipeline.template_render import template_spec

    cfg = _cfg(frame={"headerBorder": True, "color": "#FF0000", "headerHeightPercent": 10},
               progressBar={"enabled": True, "color": "#00FF00", "heightPercent": 2, "position": "bottom"},
               layers=[_layer(text="{titulo}", y=5, color="#FFFFFF", fontFamily="anton", fontSize=60)])
    spec = template_spec(cfg, 2.0, 6.0, 640)
    spec.ass_path = write_ass(tmp_path / "t.ass", build_template_ass(cfg, [], 2.0, 6.0, {"titulo": "OI"}))
    out = render_clip(sample_video, tmp_path / "o.mp4", spec, 1280, 720, True)
    s = _probe_video(out)
    assert (s["width"], s["height"]) == (360, 640)
    frame = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "1.0", "-i", str(out), "-frames:v", "1", str(frame)], check=True)
    im = Image.open(frame).convert("RGB")
    r, g, b = im.getpixel((5, 5))
    assert r > 200 and g < 60 and b < 60  # cabeçalho vermelho
    r, g, b = im.getpixel((20, 636))  # barra de progresso em ~25% no segundo 1 de 4
    assert g > 180 and r < 90
    r, g, b = im.getpixel((200, 636))
    assert not (g > 180 and r < 90)  # ...mas ainda não chegou ao fim


@pytest.mark.parametrize("key", ["sans", "anton", "pixel", "bungee", "pacifico"])
def test_font_size_matches_browser(key, tmp_path):
    """A letra no vídeo (libass) deve ter a mesma altura que no navegador/PIL com o mesmo tamanho CSS."""
    import numpy as np
    from PIL import Image, ImageFont

    from eztractor.fonts import ass_size_ratio, fonts_dir, get_font

    css = 120
    fam = get_font(key).family
    ass = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1000\nPlayResY: 1000\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: S,{fam},{css * ass_size_ratio(key):.1f},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,"
        "100,100,0,0,1,0,0,5,0,0,0,1\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:05.00,S,,0,0,0,,{\\pos(500,500)}H\n"
    )
    (tmp_path / "c.ass").write_text(ass)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=black:s=1000x1000:d=1", "-vf",
                    f"ass=filename={tmp_path}/c.ass:fontsdir={fonts_dir()}", "-frames:v", "1",
                    str(tmp_path / "c.png")], check=True)
    a = np.asarray(Image.open(tmp_path / "c.png").convert("L")) > 128
    rows = np.where(a.any(axis=1))[0]
    ass_h = rows[-1] - rows[0] + 1
    bbox = ImageFont.truetype(str(font_file(key, False)), css).getbbox("H")
    css_h = bbox[3] - bbox[1]
    assert abs(ass_h - css_h) / css_h < 0.06, (ass_h, css_h)


def test_numero_and_total_are_per_clip(client, sample_video, monkeypatch):
    """Regressão: todos os clipes saíam como "TOP 1" (posição calculada antes dos clipes existirem)."""
    from eztractor.pipeline import run as run_mod

    seen = []
    real = run_mod.build_template_ass

    def spy(cfg, words, start, end, ctx, **kw):
        seen.append((ctx["numero"], ctx["total"]))
        return real(cfg, words, start, end, ctx, **kw)

    monkeypatch.setattr(run_mod, "build_template_ass", spy)
    tpl = client.post("/templates", json={"name": "Rank", "config": PRESETS[5]["config"]}).json()
    with open(sample_video, "rb") as f:
        r = client.post("/projects/upload", files={"file": ("x.mp4", f)}, data={"settings": json.dumps(
            {"max_clips": 3, "clip_min_s": 5, "clip_max_s": 8, "template_id": tpl["id"]})})
    p = client.get(f"/projects/{r.json()['id']}").json()
    n = len(p["clips"])
    assert n >= 2 and sorted(seen) == [(i, n) for i in range(1, n + 1)]
