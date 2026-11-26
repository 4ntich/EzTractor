"""Legenda e hashtags prontas para postar."""

from eztractor.pipeline.social import make_caption, make_hashtags, normalize_hashtags, social_text


def test_caption_uses_title_hook_game_and_language():
    c = make_caption("Que clutch insano", "Ninguém acreditou nisso!", "Valorant", "pt", "audio")
    assert c.splitlines() == ["Que clutch insano 😱", "Ninguém acreditou nisso!", "Segue pra mais clipes de Valorant! 🎮"]
    assert make_caption("Insane clutch", "", "", "en").splitlines() == ["Insane clutch 🎮", "Follow for more clips! 🎮"]
    assert "más clips de CS2" in make_caption("Increíble", "", "CS2", "es-419")
    # gancho igual ao título não repete
    assert make_caption("Olha isso!", "olha isso", "", "pt").count("lha isso") == 1


def test_hashtags_for_known_and_unknown_games():
    assert make_hashtags("Free Fire", "pt")[:2] == ["#freefire", "#ff"]
    assert make_hashtags("Counter-Strike 2", "pt")[:2] == ["#cs2", "#counterstrike"]
    assert make_hashtags("Hollow Knight", "en")[0] == "#hollowknight"
    tags = make_hashtags("", "pt")
    assert "#parati" in tags and "#gaming" in tags and len(tags) <= 8
    assert len(set(t.lower() for t in tags)) == len(tags)


def test_normalize_hashtags_accepts_text_or_list():
    assert normalize_hashtags("#Valorant clutch, #FYP #fyp  ##ace!") == ["#Valorant", "#clutch", "#FYP", "#ace"]
    assert normalize_hashtags(["jogos", "#ação"]) == ["#jogos", "#ação"]
    assert normalize_hashtags(None) == [] and normalize_hashtags("  ,  ") == []


def test_social_text():
    assert social_text("Legenda\n", ["#a", "#b"]) == "Legenda\n\n#a #b"
    assert social_text("Só legenda", []) == "Só legenda"


def test_ai_caption_is_used_and_falls_back(monkeypatch):
    """A legenda vem da IA; se ela não mandar, o clipe usa a gerada sem IA."""
    from eztractor.pipeline.candidates import Candidate
    from eztractor.pipeline.ranker import _from_ai_json

    cands = [Candidate(id=0, start=10, end=30, heuristic=1.0, stats={}),
             Candidate(id=1, start=50, end=70, heuristic=0.5, stats={})]
    data = {"clips": [
        {"candidate_id": 0, "score": 90, "title": "T", "hook": "H", "reason": "r", "start": 10, "end": 30,
         "caption": "Que jogada 🔥", "hashtags": ["valorant", "#ace", "#ace"]},
        {"candidate_id": 1, "score": 50, "title": "T2", "hook": "H2", "reason": "r", "start": 50, "end": 70},
    ]}
    out = _from_ai_json(data, cands, [], 100.0, "Valorant", "pt", 10, 60)
    assert out[0].caption == "Que jogada 🔥" and out[0].hashtags == ["#valorant", "#ace"]
    assert out[1].caption == "" and out[1].hashtags is None  # o pipeline completa com o gerador grátis


def test_edit_caption_and_hashtags_via_api(client, sample_video):
    import json

    with open(sample_video, "rb") as f:
        p = client.post("/projects/upload", files={"file": ("live.mp4", f, "video/mp4")},
                        data={"title": "Live", "settings": json.dumps({"render_height": 640, "max_clips": 2, "game": "Free Fire"})}).json()
    import time
    for _ in range(300):
        p = client.get(f"/projects/{p['id']}").json()
        if p["status"] in ("ready", "failed"):
            break
        time.sleep(0.2)
    assert p["status"] == "ready", p["error"]
    c = p["clips"][0]
    assert c["caption"] and c["hashtags"][:2] == ["#freefire", "#ff"]
    assert c["social_text"] == c["caption"] + "\n\n" + " ".join(c["hashtags"])

    r = client.patch(f"/clips/{c['id']}", json={"caption": "Minha legenda 😎 ", "hashtags": "#ff garena, #booyah"})
    assert r.status_code == 200, r.text
    c2 = r.json()
    assert c2["caption"] == "Minha legenda 😎" and c2["hashtags"] == ["#ff", "#garena", "#booyah"]
    assert c2["social_text"] == "Minha legenda 😎\n\n#ff #garena #booyah"
    assert c2["render_status"] == "ready"  # mudar só a legenda não renderiza de novo
