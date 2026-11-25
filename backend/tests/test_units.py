import numpy as np

from eztractor.pipeline.candidates import generate, snap_to_words
from eztractor.pipeline.captions import build_ass, chunk_words
from eztractor.pipeline.ranker import heuristic_rank
from eztractor.pipeline.render import RenderSpec, build_filter
from eztractor.pipeline.signals import Signals, word_counts


def test_word_counts_detects_hype_and_multiword():
    words = [{"w": "Meu", "start": 1.0, "end": 1.2}, {"w": "Deus!", "start": 1.3, "end": 1.6},
             {"w": "CLUTCH", "start": 3.1, "end": 3.5}, {"w": "normal", "start": 5.0, "end": 5.2}]
    hype, speech = word_counts(words, 6)
    assert hype[1] == 1 and hype[3] == 1 and hype[5] == 0
    assert speech.sum() == 4


def test_candidates_find_peak_without_overlap():
    n = 300
    audio = np.zeros(n, dtype=np.float32)
    audio[200:205] = 4.0
    audio[60:63] = 2.5
    sig = Signals(audio, np.zeros(n), np.zeros(n), np.zeros(n))
    cands = generate(sig, n, [], 15, 45, limit=4)
    assert cands[0].start <= 200 and cands[0].end >= 204
    assert all(15 <= c.duration <= 45 for c in cands)
    for i, a in enumerate(cands):
        for b in cands[i + 1:]:
            inter = max(0, min(a.end, b.end) - max(a.start, b.start))
            assert inter / min(a.duration, b.duration) < 0.15


def test_short_video_single_candidate():
    sig = Signals(np.zeros(10), np.zeros(10), np.zeros(10), np.zeros(10))
    cands = generate(sig, 10.0, [], 15, 45, limit=5)
    assert len(cands) == 1 and cands[0].end == 10.0


def test_snap_to_words_extends_to_sentence_edges():
    words = [{"w": "a", "start": 9.0, "end": 10.5}, {"w": "b", "start": 29.5, "end": 31.0}]
    assert snap_to_words(10.0, 30.0, words) == (9.0, 31.0)


def test_heuristic_rank_scores_in_range():
    sig = Signals(np.r_[np.zeros(100), np.full(10, 3.0), np.zeros(100)], np.zeros(210), np.zeros(210), np.zeros(210))
    ranked = heuristic_rank(generate(sig, 210, [], 15, 30, limit=4), [])
    assert ranked[0].score == 95
    assert all(0 <= r.score <= 100 for r in ranked)


def test_ass_highlights_current_word_and_uses_relative_times():
    words = [{"w": "olha", "start": 10.0, "end": 10.4}, {"w": "isso", "start": 10.5, "end": 10.9}]
    ass = build_ass(words, 10.0, 20.0, 1080, 1920, hook="Que jogada!", watermark="wm")
    assert "Dialogue: 0,0:00:00.00" in ass
    assert "{\\c&H00FFFF&}OLHA" in ass and "{\\c&H00FFFF&}ISSO" in ass
    assert "Hook,,0,0,0,,Que jogada!" in ass and "Watermark" in ass
    assert len(chunk_words(words * 3)) >= 2


def test_filters_for_each_layout():
    for layout in ("crop", "fit"):
        g = build_filter(RenderSpec(0, 10, layout=layout), 1920, 1080)
        assert g.endswith("[v]")
    g = build_filter(RenderSpec(0, 10, layout="split", facecam={"x": 0, "y": 0, "w": 0.25, "h": 0.25}), 1920, 1080)
    assert "vstack" in g and "crop=480:270:0:0" in g


def test_claude_rank_parses_and_clamps(monkeypatch):
    import json as _json
    from types import SimpleNamespace

    import anthropic

    from eztractor.pipeline import ranker
    from eztractor.pipeline.candidates import Candidate

    payload = {"clips": [
        {"candidate_id": 1, "score": 130, "title": " Ace! ", "hook": "olha isso", "reason": "r",
         "start": 0.0, "end": 500.0},
        {"candidate_id": 99, "score": 50, "title": "x", "hook": "", "reason": "", "start": 0, "end": 1},
    ]}
    captured = {}

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=_json.dumps(payload))])

    monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages())))
    cands = [Candidate(0, 10, 30, 1.0, {}), Candidate(1, 100, 130, 2.0, {})]
    out = ranker.claude_rank(cands, [], 600, "Valorant", 15, 45)

    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    top = out[0]
    assert (top.candidate_id, top.score, top.title) == (1, 100, "Ace!")
    assert top.start == 92 and top.end - top.start <= 45  # limites refinados em até ±8s e duração máx.
    assert {r.candidate_id for r in out} == {0, 1}  # id inventado ignorado; omitido volta pela heurística


def test_rank_falls_back_to_heuristic_on_error(monkeypatch):
    from eztractor.pipeline import ranker
    from eztractor.pipeline.candidates import Candidate

    def boom(*a, **k):
        raise RuntimeError("sem rede")

    monkeypatch.setattr(ranker, "claude_rank", boom)
    out, method = ranker.rank([Candidate(0, 0, 20, 1.0, {})], [], 60, "", 15, 45)
    assert method == "heuristic" and len(out) == 1


def test_render_split_and_fit_with_captions(sample_video, tmp_path):
    from eztractor.pipeline.captions import write_ass
    from eztractor.pipeline.media import probe
    from eztractor.pipeline.render import render_clip

    words = [{"w": "bora", "start": 1.0, "end": 1.4}]
    for layout, fc in (("split", {"x": 0.0, "y": 0.0, "w": 0.3, "h": 0.3}), ("fit", None)):
        spec = RenderSpec(0.5, 3.0, height=640, layout=layout, facecam=fc)
        spec.ass_path = write_ass(tmp_path / f"{layout}.ass", build_ass(words, 0.5, 3.0, spec.width, 640, hook="gg"))
        out = render_clip(sample_video, tmp_path / f"{layout}.mp4", spec, 1280, 720, True)
        info = probe(out)
        assert (info.width, info.height) == (360, 640) and 2.0 < info.duration_s < 3.2


def test_candidate_extends_to_cover_whole_climax():
    n = 120
    audio = np.zeros(n, dtype=np.float32)
    audio[40:47] = 4.0  # clímax de 7s
    sig = Signals(audio, np.zeros(n), np.zeros(n), np.zeros(n))
    top = generate(sig, n, [], 8, 15, limit=3)[0]
    assert top.start <= 40 and top.end >= 47 and top.duration <= 15


# ---------------------------------------------------------------- títulos/ganchos sem IA
def test_headline_uses_hype_phrase_near_peak():
    from eztractor.pipeline.headlines import make_headline

    words = [
        {"w": "vou", "start": 10.0, "end": 10.2}, {"w": "entrar", "start": 10.3, "end": 10.6},
        {"w": "no", "start": 10.7, "end": 10.8}, {"w": "bomb", "start": 10.9, "end": 11.2},
        {"w": "meu", "start": 14.0, "end": 14.2}, {"w": "deus", "start": 14.3, "end": 14.6},
        {"w": "que", "start": 14.7, "end": 14.8}, {"w": "clutch", "start": 14.9, "end": 15.4},
    ]
    stats = {"audio_peak_z": 3.1, "scene_cuts": 2, "hype_words": 2, "words": 8, "peak_t": 15.0}
    title, hook, reason = make_headline(words, stats, game="CS2", language="pt")
    assert hook == "Meu deus que clutch!"
    assert title == "Meu deus que clutch | CS2"
    assert "3.1σ" in reason and len(hook) <= 51 and len(title) <= 60


def test_headline_templates_without_speech_by_language():
    from eztractor.pipeline.headlines import make_headline

    loud = {"audio_peak_z": 3.0, "scene_cuts": 0, "hype_words": 0, "words": 0}
    assert make_headline([], loud, language="pt")[:2] == ("Reação explosiva", "Espera o final…")
    assert make_headline([], loud, language="en")[:2] == ("Explosive reaction", "Wait for the end…")
    busy = {"audio_peak_z": 0.5, "scene_cuts": 5, "hype_words": 0, "words": 0}
    assert make_headline([], busy, game="Valorant", language="es")[0] == "Acción sin parar | Valorant"


def test_headline_truncates_long_speech():
    from eztractor.pipeline.headlines import make_headline

    words = [{"w": f"palavra{i}!", "start": i * 0.3, "end": i * 0.3 + 0.2} for i in range(1)] + [
        {"w": "x" * 20, "start": 1 + i * 0.3, "end": 1.2 + i * 0.3} for i in range(10)]
    title, hook, _ = make_headline(words, {"peak_t": 2.0, "words": 11}, language="pt")
    assert len(title) <= 60 and len(hook) <= 51


# ---------------------------------------------------------------- Ollama
def _fake_cands():
    from eztractor.pipeline.candidates import Candidate

    return [Candidate(0, 10, 30, 1.0, {"peak_t": 20.0}), Candidate(1, 100, 130, 2.0, {"peak_t": 120.0})]


def test_ollama_rank_sends_schema_and_parses(monkeypatch):
    import httpx

    from eztractor.pipeline import ranker

    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, body=json)
        content = '{"clips":[{"candidate_id":0,"score":88,"title":"Ace","hook":"OLHA","reason":"r","start":10,"end":30},' \
                  '{"candidate_id":1,"score":"ruim","title":"x","hook":"","reason":"","start":0,"end":1}]}'
        return httpx.Response(200, json={"message": {"content": content}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    out, method = ranker.rank(_fake_cands(), [], 600, "", 15, 45, method="ollama")
    assert method == "ollama"
    assert sent["url"].endswith("/api/chat") and sent["body"]["format"]["type"] == "object"
    assert sent["body"]["stream"] is False
    assert out[0].candidate_id == 0 and out[0].score == 88 and out[0].hook == "OLHA"
    assert {r.candidate_id for r in out} == {0, 1}  # item inválido volta pela heurística


def test_ollama_offline_falls_back(monkeypatch):
    import httpx

    from eztractor.pipeline import ranker

    def down(*a, **k):
        raise httpx.ConnectError("recusado")

    monkeypatch.setattr(httpx, "post", down)
    monkeypatch.setattr(httpx, "get", down)
    out, method = ranker.rank(_fake_cands(), [], 600, "", 15, 45, method="ollama")
    assert method == "heuristic" and len(out) == 2 and out[0].title
    assert ranker.ollama_status()["online"] is False
