"""Gera janelas candidatas a clipe a partir dos sinais por segundo."""

from dataclasses import dataclass, field

import numpy as np

from .signals import Signals


@dataclass
class Candidate:
    id: int
    start: float
    end: float
    heuristic: float  # nota bruta (não normalizada)
    stats: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start


def _smooth(x: np.ndarray, k: int = 3) -> np.ndarray:
    if len(x) < k:
        return x.copy()
    kernel = np.ones(k) / k
    return np.convolve(x, kernel, mode="same")


def _overlap(a: Candidate, b: Candidate) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    return inter / max(1e-6, min(a.duration, b.duration))


def snap_to_words(start: float, end: float, words: list[dict], slack: float = 2.0) -> tuple[float, float]:
    """Evita cortar no meio de uma frase: recua o início e avança o fim até um silêncio próximo."""
    if not words:
        return start, end
    for w in words:  # primeira palavra que termina após o início
        if w["end"] > start:
            if w["start"] < start and start - w["start"] <= slack:
                start = w["start"]
            break
    for w in reversed(words):  # última palavra que começa antes do fim
        if w["start"] < end:
            if w["end"] > end and w["end"] - end <= slack:
                end = w["end"]
            break
    return start, end


def generate(
    sig: Signals,
    duration_s: float,
    words: list[dict],
    clip_min_s: int,
    clip_max_s: int,
    limit: int,
) -> list[Candidate]:
    """Retorna até `limit` candidatos sem sobreposição, ordenados pela nota heurística."""
    duration_s = float(duration_s)
    if duration_s <= clip_min_s:
        return [Candidate(0, 0.0, duration_s, float(sig.score().mean()) if len(sig) else 0.0)]

    per_sec = _smooth(sig.score())
    target = (clip_min_s + clip_max_s) / 2
    lengths = sorted({clip_min_s, int(round(target)), clip_max_s})

    # Picos locais da curva suavizada = âncoras dos clipes
    order = np.argsort(per_sec)[::-1]
    anchors: list[int] = []
    for idx in order:
        if all(abs(int(idx) - a) >= clip_min_s / 2 for a in anchors):
            anchors.append(int(idx))
        if len(anchors) >= limit * 4:
            break

    raw: list[Candidate] = []
    for a in anchors:
        for L in lengths:
            # O clímax costuma vir depois do "build-up": mais contexto antes do pico.
            start = max(0.0, a - 0.65 * L)
            end = min(duration_s, start + L)
            start = max(0.0, end - L)
            s, e = int(start), max(int(start) + 1, int(np.ceil(end)))
            window = per_sec[s:e]
            top = np.sort(window)[::-1][: max(1, len(window) // 3)]
            # média dos melhores segundos + pico, com leve penalidade para janelas longas sem conteúdo
            value = float(top.mean() + 0.5 * window.max() - 0.01 * (L - clip_min_s))
            raw.append(Candidate(0, start, end, value))

    # Não cortar o clímax: estende o fim (até clip_max_s) enquanto o momento continua "quente".
    n = len(per_sec)
    for c in raw:
        s = int(c.start)
        e = int(np.ceil(c.end))
        hot = 0.5 * float(per_sec[s:e].max()) if e > s else 0.0
        extended = False
        while hot > 0 and e < n and e - s < clip_max_s and per_sec[e] >= hot:
            e += 1
            extended = True
        if extended:
            e = min(n, e + 1, s + clip_max_s)  # 1s de respiro após o clímax
        c.end = min(duration_s, max(c.end, float(e)))

    raw.sort(key=lambda c: c.heuristic, reverse=True)
    picked: list[Candidate] = []
    for c in raw:
        if all(_overlap(c, p) < 0.15 for p in picked):
            picked.append(c)
        if len(picked) >= limit:
            break

    for i, c in enumerate(picked):
        c.id = i
        c.start, c.end = snap_to_words(c.start, c.end, words)
        c.start, c.end = round(max(0.0, c.start), 2), round(min(duration_s, c.end), 2)
        s, e = int(c.start), max(int(c.start) + 1, int(np.ceil(c.end)))
        c.stats = {
            "audio_peak_z": round(float(sig.audio_z[s:e].max()), 2),
            "scene_cuts": int(sig.scene[s:e].sum()),
            "hype_words": int(sig.hype[s:e].sum()),
            "words": int(sig.speech[s:e].sum()),
        }
    return picked


def words_in(words: list[dict], start: float, end: float) -> list[dict]:
    return [w for w in words if w["end"] > start and w["start"] < end]
