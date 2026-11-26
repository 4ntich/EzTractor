"""Análise visual barata, sem IA: miniaturas 64x36 em cinza a 2 quadros/s (uma passada do ffmpeg).

Serve para achar o que NÃO é destaque, mesmo quando ninguém fala nada:
- vinhetas/transições: trechos de imagem que se repetem em outro ponto do vídeo;
- telas paradas sem fala: "starting soon", "volto já", pausas;
- tela final: o fim do vídeo com imagem parada (ou preta) e sem fala.
Também mede o movimento da imagem (ação) por segundo, usado como sinal de destaque.
"""

import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .media import run

FPS = 2
W, H = 64, 36
STATIC_MOTION = 0.6  # diferença média (0-255) abaixo disso = imagem parada (tela parada real ~0,0; jogo lento ~1,2+)
MIN_DETAIL = 10.0  # desvio da imagem abaixo disso = quadro liso/preto (não serve para achar repetição)


@dataclass
class Visual:
    frames: np.ndarray  # (n, H, W) uint8
    fps: int = FPS
    scene_times: list[float] | None = None  # trocas de cena (s), da mesma passada do ffmpeg

    @property
    def n(self) -> int:
        return len(self.frames)

    def frame_motion(self) -> np.ndarray:
        """Diferença média entre quadros seguidos (0-255); o 1º quadro repete o 2º."""
        if self.n < 2:
            return np.zeros(self.n, dtype=np.float32)
        f = self.frames.astype(np.int16)
        d = np.abs(f[1:] - f[:-1]).mean(axis=(1, 2)).astype(np.float32)
        return np.concatenate([d[:1], d])

    def per_second(self, values: np.ndarray, n_seconds: int, how=np.mean) -> np.ndarray:
        out = np.zeros(n_seconds, dtype=np.float32)
        for s in range(n_seconds):
            chunk = values[s * self.fps:(s + 1) * self.fps]
            if chunk.size:
                out[s] = how(chunk)
        return out

    def motion_z(self, n_seconds: int) -> np.ndarray:
        """Movimento por segundo em z-score (quanto acima do normal do vídeo)."""
        m = self.per_second(self.frame_motion(), n_seconds)
        if m.size == 0:
            return m
        med = float(np.median(m))
        mad = float(np.median(np.abs(m - med))) * 1.4826
        return (m - med) / max(mad, 0.5)


def extract(video_path: Path, scene_threshold: float = 0.35) -> Visual:
    """Uma única decodificação do vídeo: trocas de cena (como antes) + miniaturas para a análise visual."""
    import re

    with tempfile.TemporaryDirectory(prefix="ezt-vis-", ignore_cleanup_errors=True) as tmp:
        raw = Path(tmp) / "frames.gray"
        proc = run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(video_path), "-an", "-sn",
                    "-filter_complex",
                    f"[0:v]scale=160:-2,split=2[a][b];"
                    # eq(n,0): a saída de cenas sempre recebe o 1º quadro (descartado abaixo); sem isso, num vídeo
                    # sem troca de cena ela fica vazia e o ffmpeg mais novo (Windows) falha com "Nothing was written"
                    f"[a]select='eq(n\\,0)+gt(scene\\,{scene_threshold})',showinfo[s];"
                    f"[b]fps={FPS},scale={W}:{H}:flags=area,format=gray[g]",
                    "-map", "[s]", "-f", "null", "-",
                    "-map", "[g]", "-f", "rawvideo", str(raw)])
        data = np.fromfile(raw, dtype=np.uint8)
    n = data.size // (W * H)
    scenes = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)][1:]  # [0] = 1º quadro (não é corte)
    return Visual(data[: n * W * H].reshape(n, H, W), scene_times=scenes)


# ---------------------------------------------------------------- impressão digital dos quadros
def dhash(frames: np.ndarray) -> np.ndarray:
    """Hash de diferença de 64 bits por quadro (robusto a pequenas mudanças de cor/compressão)."""
    n = len(frames)
    if n == 0:
        return np.zeros(0, dtype=np.uint64)
    ys = np.linspace(0, H, 9).astype(int)
    xs = np.linspace(0, W, 10).astype(int)
    small = np.empty((n, 8, 9), dtype=np.float32)
    for i in range(8):
        for j in range(9):
            small[:, i, j] = frames[:, ys[i]:ys[i + 1], xs[j]:xs[j + 1]].mean(axis=(1, 2))
    bits = (small[:, :, 1:] > small[:, :, :-1]).reshape(n, 64).astype(np.uint64)
    weights = np.left_shift(np.uint64(1), np.arange(64, dtype=np.uint64))
    return (bits * weights).sum(axis=1, dtype=np.uint64)


def _popcount(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.uint64)
    c = np.zeros(x.shape, dtype=np.uint8)
    for _ in range(64):
        c += (x & np.uint64(1)).astype(np.uint8)
        x = x >> np.uint64(1)
    return c


def repeated_runs(vis: Visual, speech_per_s: np.ndarray | None = None, min_s: float = 2.0, max_s: float = 20.0,
                  min_gap_s: float = 15.0, max_dist: int = 6) -> list[tuple[float, float]]:
    """Trechos (início, fim em s) cuja imagem em movimento aparece de novo em outro ponto do vídeo
    (vinheta, transição, abertura). Não contam: trechos com fala, imagem parada, ou repetição sem
    corte de cena/fade nas pontas (isso é um ciclo contínuo, ex.: volta 2 de uma corrida)."""
    n = vis.n
    if n < 4:
        return []
    detail = vis.frames.reshape(n, -1).std(axis=1)
    hashes = dhash(vis.frames)
    motion = vis.frame_motion()
    ok = detail >= MIN_DETAIL
    min_gap = int(min_gap_s * vis.fps)
    # candidatos a par: mesmo valor em alguma das 4 faixas de 16 bits (LSH), sem comparar tudo com tudo
    found: list[np.ndarray] = []
    for band in range(4):
        key = ((hashes >> np.uint64(16 * band)) & np.uint64(0xFFFF)).astype(np.int64)
        buckets: dict[int, list[int]] = defaultdict(list)
        for i in np.nonzero(ok)[0]:
            buckets[int(key[i])].append(int(i))
        for idx in buckets.values():
            if not 2 <= len(idx) <= 300:  # balde enorme = imagem genérica demais para provar repetição
                continue
            arr = np.array(idx)
            a_, b_ = np.triu_indices(len(arr), k=1)
            pr = np.stack([arr[a_], arr[b_]], axis=1)
            found.append(pr[pr[:, 1] - pr[:, 0] >= min_gap])
    if not found:
        return []
    pairs = np.unique(np.concatenate(found), axis=0)
    if pairs.size == 0:
        return []
    dist = _popcount(hashes[pairs[:, 0]] ^ hashes[pairs[:, 1]])
    good = pairs[dist <= max_dist]
    # uma repetição de verdade é uma sequência de quadros com o mesmo atraso entre as duas aparições
    by_offset: dict[int, list[int]] = defaultdict(list)
    for i, j in good:
        by_offset[int(j - i)].append(int(i))
    talking = np.zeros(n, dtype=bool)
    if speech_per_s is not None and speech_per_s.size:
        t = np.repeat(speech_per_s > 0, vis.fps)[:n]
        talking[: t.size] = t
    min_len, max_len = int(min_s * vis.fps), int(max_s * vis.fps)
    cuts = np.array(sorted(vis.scene_times or []), dtype=np.float64)
    dark = (vis.frames.reshape(n, -1).mean(axis=1) < 20) | (detail < MIN_DETAIL)

    def edge(i: int) -> bool:  # corte de cena ou quadro preto/liso (fade) a até 1 s
        t = i / vis.fps
        if cuts.size and np.min(np.abs(cuts - t)) <= 1.0:
            return True
        return bool(dark[max(0, i - vis.fps):min(n, i + vis.fps + 1)].any())

    def bounded(a: int, b: int) -> bool:
        return edge(a) or edge(b)

    # total de quadros repetidos em cada distância (agrupando distâncias vizinhas): se passar do tamanho
    # de uma vinheta, é uma reprise/replay longo, não vinheta, e essa distância é ignorada por inteiro
    near_total: dict[int, int] = defaultdict(int)
    for off, starts in by_offset.items():
        near_total[off // 4] += len(set(starts))
    long_repeat = {off for off in by_offset
                   if near_total[off // 4] + near_total[off // 4 - 1] + near_total[off // 4 + 1] > max_len}

    # distâncias quase iguais (±4 quadros) são a mesma repetição vista com um atraso: fica só a mais forte
    strength = {off: len(set(st)) for off, st in by_offset.items()}
    best_near = {off for off in by_offset
                 if all(strength[off] >= strength.get(o, 0) for o in range(off - 4, off + 5) if o != off)}

    marked = np.zeros(n, dtype=bool)
    for off, starts in by_offset.items():
        if off in long_repeat or off not in best_near:
            continue
        starts = sorted(set(starts))
        run_start = prev = starts[0]
        for i in starts[1:] + [None]:
            if i is not None and i - prev <= 2:  # tolera 1 quadro perdido
                prev = i
                continue
            a0, a1, b0, b1 = run_start, prev + 1, run_start + off, prev + off + 1
            length = a1 - a0
            moving = motion[a0:a1].mean() >= STATIC_MOTION * 2 and motion[b0:b1].mean() >= STATIC_MOTION * 2
            silent = talking[a0:a1].mean() < 0.3 and talking[b0:b1].mean() < 0.3
            if min_len <= length <= max_len and moving and silent and bounded(a0, a1) and bounded(b0, b1):
                marked[a0:a1] = True
                marked[b0:b1] = True
            if i is not None:
                run_start = prev = i
    return _runs(marked, vis.fps)


def _runs(mask: np.ndarray, fps: int, min_len: int = 1) -> list[tuple[float, float]]:
    out = []
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            if j - i + 1 >= min_len:
                out.append((i / fps, (j + 1) / fps))
            i = j + 1
        else:
            i += 1
    return out


def static_runs(vis: Visual, speech_per_s: np.ndarray, min_s: float = 8.0) -> list[tuple[float, float]]:
    """Trechos de imagem praticamente parada e sem fala (tela de espera, pausa, cartela)."""
    motion = vis.frame_motion()
    talking = np.repeat(speech_per_s > 0, vis.fps)[: vis.n]
    if talking.size < vis.n:
        talking = np.concatenate([talking, np.zeros(vis.n - talking.size, dtype=bool)])
    still = (motion < STATIC_MOTION) & ~talking
    return _runs(still, vis.fps, int(min_s * vis.fps))


def end_screen(vis: Visual, speech_per_s: np.ndarray, duration: float) -> tuple[float, float] | None:
    """Tela final: do fim para trás, imagem parada ou preta e sem fala (>= 3 s, no máx. 60 s)."""
    if vis.n < 6:
        return None
    motion = vis.frame_motion()
    bright = vis.frames.reshape(vis.n, -1).mean(axis=1)
    last_word = float(np.nonzero(speech_per_s)[0].max() + 1) if np.any(speech_per_s) else 0.0
    i = vis.n - 1
    limit = max(int(last_word * vis.fps), vis.n - 60 * vis.fps)
    while i > limit and (motion[i] < STATIC_MOTION * 1.5 or bright[i] < 16):
        i -= 1
    start = (i + 1) / vis.fps
    if duration - start >= 3.0:
        return round(start, 2), round(duration, 2)
    return None


def skip_segments(vis: Visual, speech_per_s: np.ndarray, duration: float) -> list[dict]:
    """Trechos a pular achados pela imagem (mesmo formato de ads.py)."""
    segs = []
    for a, b in repeated_runs(vis, speech_per_s):
        segs.append({"start": a, "end": min(duration, b), "category": "vinheta",
                     "reason": "Vinheta/transição (imagem repetida)", "source": "imagem"})
    for a, b in static_runs(vis, speech_per_s):
        segs.append({"start": a, "end": min(duration, b), "category": "parado",
                     "reason": "Tela parada sem fala", "source": "imagem"})
    end = end_screen(vis, speech_per_s, duration)
    if end:
        segs.append({"start": end[0], "end": end[1], "category": "endscreen",
                     "reason": "Tela final", "source": "imagem"})
    return segs
