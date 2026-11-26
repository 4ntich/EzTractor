"""Ranqueia candidatos e gera título/gancho.

Métodos:
- `heuristic`: grátis. Nota pelos sinais; título e gancho tirados da própria fala (headlines.py).
- `ollama`: grátis, IA rodando no seu computador (https://ollama.com). Mesmo prompt do Claude.
- `claude`: API paga da Anthropic.

Se a IA escolhida falhar (sem chave, Ollama desligado, resposta inválida), cai para `heuristic`.
"""

import json
import logging
from dataclasses import dataclass

from ..config import get_settings
from .candidates import Candidate, words_in
from .headlines import make_headline
from .social import MAX_HASHTAGS, normalize_hashtags

log = logging.getLogger(__name__)

METHODS = ("heuristic", "ollama", "claude")


@dataclass
class RankedClip:
    candidate_id: int
    start: float
    end: float
    score: int
    title: str
    hook: str
    reason: str
    stats: dict
    caption: str = ""
    hashtags: list[str] | None = None


SYSTEM_PROMPT = """Você é um editor de clipes para TikTok, Reels e Shorts especializado em lives de jogos.
Você recebe trechos candidatos de uma gravação longa. Cada um traz a transcrição do streamer e sinais \
automáticos (pico de volume em desvios-padrão, cortes de cena, palavras de empolgação).

Para cada candidato, avalie o potencial de viralizar como clipe vertical curto:
- Momentos fortes: jogada decisiva, eliminação múltipla, falha engraçada, reação exagerada, susto, \
virada, fala marcante ou piada.
- Momentos fracos: menus, loading, conversa monótona, trecho sem clímax.

Regras:
- score: inteiro de 0 a 100 (seja exigente; 80+ só para momentos realmente fortes).
- title: título curto e chamativo (máx. 60 caracteres), no idioma da transcrição.
- hook: frase de gancho para os 3 primeiros segundos (máx. 50 caracteres), no idioma da transcrição.
- reason: 1 frase explicando a nota.
- caption: legenda pronta para postar no TikTok/Reels/Shorts, no idioma da transcrição: 1 a 3 linhas curtas, \
com 1 ou 2 emojis e uma chamada para seguir. Sem hashtags na legenda.
- hashtags: de 5 a 8 hashtags relevantes (com #), misturando o nome do jogo, o tipo de momento e tags \
populares de games no idioma da transcrição.
- start/end: você pode refinar os limites em até 8 segundos para começar no build-up e terminar logo \
após o clímax, mantendo a duração permitida.
- NUNCA escolha como destaque trechos de propaganda, patrocínio, cupom, pedido de inscrição/like ou o final
do vídeo (despedida, tela final mostrando outros canais): dê nota abaixo de 15 a esses candidatos e não
estenda os limites para dentro desses trechos. Candidatos marcados com "skip_nearby" estão perto de um
trecho assim.
- Retorne todos os candidatos recebidos, sem inventar ids."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "integer"},
                    "score": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                    "caption": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                },
                "required": ["candidate_id", "score", "title", "hook", "reason", "caption", "hashtags", "start", "end"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- heurística (grátis)
def heuristic_rank(
    cands: list[Candidate], words: list[dict], game: str = "", language: str | None = None
) -> list[RankedClip]:
    if not cands:
        return []
    hi = max(c.heuristic for c in cands)
    lo = min(c.heuristic for c in cands)
    span = max(hi - lo, 1e-6)
    out = []
    for c in cands:
        norm = (c.heuristic - lo) / span if len(cands) > 1 else 1.0
        title, hook, reason = make_headline(words_in(words, c.start, c.end), c.stats, game, language)
        out.append(RankedClip(c.id, c.start, c.end, int(round(40 + 55 * norm)), title, hook, reason, c.stats))
    return sorted(out, key=lambda r: r.score, reverse=True)


# ---------------------------------------------------------------- partes comuns às IAs
def _build_prompt(cands: list[Candidate], words: list[dict], game: str, min_s: int, max_s: int) -> str:
    items = []
    for c in cands:
        items.append({
            "candidate_id": c.id,
            "start": c.start,
            "end": c.end,
            "signals": {k: v for k, v in c.stats.items() if k != "peak_t"},
            "transcript": " ".join(w["w"] for w in words_in(words, c.start, c.end)) or "(sem fala)",
        })
    header = f"Jogo: {game or 'não informado'}\nDuração permitida por clipe: {min_s}s a {max_s}s\n\nCandidatos:\n"
    return header + json.dumps(items, ensure_ascii=False, indent=1)


def _clamp(rc: RankedClip, cand: Candidate, duration: float, min_s: int, max_s: int) -> RankedClip:
    start = min(max(rc.start, cand.start - 8, 0.0), cand.start + 8)
    end = max(min(rc.end, cand.end + 8, duration), cand.end - 8)
    if end - start > max_s:
        end = start + max_s
    if end - start < min(min_s, duration):
        start, end = cand.start, cand.end
    rc.start, rc.end = round(start, 2), round(end, 2)
    rc.score = max(0, min(100, rc.score))
    rc.title = rc.title.strip()[:200]
    rc.hook = rc.hook.strip()[:200]
    return rc


def _from_ai_json(
    data: dict, cands: list[Candidate], words: list[dict], duration: float, game: str,
    language: str | None, min_s: int, max_s: int,
) -> list[RankedClip]:
    by_id = {c.id: c for c in cands}
    out: list[RankedClip] = []
    seen: set[int] = set()
    for item in data.get("clips", []):
        try:
            cid = int(item["candidate_id"])
            rc = RankedClip(cid, float(item["start"]), float(item["end"]), int(item["score"]),
                            str(item["title"]), str(item["hook"]), str(item["reason"]), {},
                            caption=str(item.get("caption") or "").strip()[:2200],
                            hashtags=normalize_hashtags(item.get("hashtags"))[:MAX_HASHTAGS] or None)
        except (KeyError, TypeError, ValueError):
            continue  # modelos locais às vezes erram um item; ignora só ele
        if cid not in by_id or cid in seen:
            continue
        seen.add(cid)
        rc.stats = by_id[cid].stats
        out.append(_clamp(rc, by_id[cid], duration, min_s, max_s))
    if not out:
        raise ValueError("a IA não devolveu nenhum clipe válido")
    # candidatos que a IA omitiu entram pela heurística, mas sempre abaixo dos avaliados pela IA
    missing = [c for c in cands if c.id not in seen]
    if missing:
        floor = min(r.score for r in out)
        for i, r in enumerate(heuristic_rank(missing, words, game, language)):
            r.score = max(0, floor - 1 - i)
            out.append(r)
    return sorted(out, key=lambda r: r.score, reverse=True)


# ---------------------------------------------------------------- Claude (pago)
def claude_rank(cands, words, duration, game, min_s, max_s, language=None) -> list[RankedClip]:
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=get_settings().claude_model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_prompt(cands, words, game, min_s, max_s)}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _SCHEMA}},
        # Se o modelo principal recusar, a API reexecuta no modelo de fallback adequado.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("modelo recusou a requisição")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("resposta truncada (max_tokens)")
    text = next(b.text for b in response.content if b.type == "text")
    return _from_ai_json(json.loads(text), cands, words, duration, game, language, min_s, max_s)


# ---------------------------------------------------------------- Ollama (IA local, grátis)
def ollama_rank(cands, words, duration, game, min_s, max_s, language=None) -> list[RankedClip]:
    import httpx

    s = get_settings()
    resp = httpx.post(
        f"{s.ollama_url.rstrip('/')}/api/chat",
        json={
            "model": s.ollama_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(cands, words, game, min_s, max_s)},
            ],
            "format": _SCHEMA,  # saída estruturada do Ollama (JSON Schema)
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 16384},
        },
        timeout=s.ollama_timeout_s,
    )
    if resp.status_code == 404:
        raise RuntimeError(f"modelo '{s.ollama_model}' não encontrado no Ollama; rode: ollama pull {s.ollama_model}")
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return _from_ai_json(json.loads(content), cands, words, duration, game, language, min_s, max_s)


def ollama_status() -> dict:
    """Diz se o Ollama está no ar e se o modelo configurado está baixado."""
    import httpx

    s = get_settings()
    try:
        r = httpx.get(f"{s.ollama_url.rstrip('/')}/api/tags", timeout=1.5)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError):
        return {"online": False, "model": s.ollama_model, "model_ready": False}
    wanted = s.ollama_model if ":" in s.ollama_model else f"{s.ollama_model}:latest"
    return {"online": True, "model": s.ollama_model, "model_ready": wanted in names}


# ---------------------------------------------------------------- entrada única
_AI = {"claude": claude_rank, "ollama": ollama_rank}


def rank(
    cands: list[Candidate], words: list[dict], duration: float, game: str, min_s: int, max_s: int,
    method: str | None = None, language: str | None = None,
) -> tuple[list[RankedClip], str]:
    """Retorna (clipes ranqueados, método efetivamente usado)."""
    method = method or get_settings().ranker
    if method in _AI and cands:
        try:
            return _AI[method](cands, words, duration, game, min_s, max_s, language), method
        except Exception as e:  # rede, chave ausente, Ollama desligado, JSON ruim… nunca derruba o pipeline
            log.warning("ranking com %s falhou, usando heurística: %s", method, e)
    return heuristic_rank(cands, words, game, language), "heuristic"
