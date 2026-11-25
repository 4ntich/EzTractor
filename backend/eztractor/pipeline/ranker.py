"""Ranqueia candidatos e gera título/gancho.

- `claude`: envia transcrição + sinais de cada candidato ao Claude e recebe JSON estruturado.
- `heuristic`: usa só a nota dos sinais (fallback sem custo, também usado se a API falhar).
"""

import json
import logging
from dataclasses import dataclass

from ..config import get_settings
from .candidates import Candidate, words_in

log = logging.getLogger(__name__)


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
- start/end: você pode refinar os limites em até 8 segundos para começar no build-up e terminar logo \
após o clímax, mantendo a duração permitida.
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
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                },
                "required": ["candidate_id", "score", "title", "hook", "reason", "start", "end"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def heuristic_rank(cands: list[Candidate], words: list[dict]) -> list[RankedClip]:
    if not cands:
        return []
    hi = max(c.heuristic for c in cands)
    lo = min(c.heuristic for c in cands)
    span = max(hi - lo, 1e-6)
    out = []
    for c in cands:
        norm = (c.heuristic - lo) / span if len(cands) > 1 else 1.0
        text = " ".join(w["w"] for w in words_in(words, c.start, c.end))
        out.append(RankedClip(
            candidate_id=c.id,
            start=c.start,
            end=c.end,
            score=int(round(40 + 55 * norm)),
            title=(text[:57] + "…") if len(text) > 58 else (text or f"Destaque #{c.id + 1}"),
            hook="",
            reason="Nota calculada pelos sinais de áudio, cena e fala.",
            stats=c.stats,
        ))
    return sorted(out, key=lambda r: r.score, reverse=True)


def _build_prompt(cands: list[Candidate], words: list[dict], game: str, min_s: int, max_s: int) -> str:
    items = []
    for c in cands:
        items.append({
            "candidate_id": c.id,
            "start": c.start,
            "end": c.end,
            "signals": c.stats,
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


def claude_rank(
    cands: list[Candidate], words: list[dict], duration: float, game: str, min_s: int, max_s: int
) -> list[RankedClip]:
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
    data = json.loads(text)

    by_id = {c.id: c for c in cands}
    out: list[RankedClip] = []
    seen: set[int] = set()
    for item in data["clips"]:
        cid = item["candidate_id"]
        if cid not in by_id or cid in seen:
            continue
        seen.add(cid)
        rc = RankedClip(cid, float(item["start"]), float(item["end"]), int(item["score"]),
                        item["title"], item["hook"], item["reason"], by_id[cid].stats)
        out.append(_clamp(rc, by_id[cid], duration, min_s, max_s))
    # candidatos que o modelo omitiu entram com a nota heurística
    missing = [c for c in cands if c.id not in seen]
    if missing:
        out.extend(heuristic_rank(missing, words))
    return sorted(out, key=lambda r: r.score, reverse=True)


def rank(
    cands: list[Candidate], words: list[dict], duration: float, game: str, min_s: int, max_s: int
) -> tuple[list[RankedClip], str]:
    """Retorna (clipes ranqueados, método usado)."""
    if get_settings().ranker == "claude" and cands:
        try:
            return claude_rank(cands, words, duration, game, min_s, max_s), "claude"
        except Exception as e:  # rede, chave ausente, recusa… nunca derruba o pipeline
            log.warning("ranking com Claude falhou, usando heurística: %s", e)
    return heuristic_rank(cands, words), "heuristic"
