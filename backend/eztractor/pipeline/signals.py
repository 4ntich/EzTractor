"""Extração de sinais por segundo: energia do áudio, cortes de cena, palavras de empolgação e fala."""

import re
import unicodedata
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .media import run

# Palavras que costumam marcar momentos de destaque em lives de jogos (pt/en/es).
HYPE_WORDS = {
    "caralho", "porra", "nossa", "meu deus", "mds", "vamo", "vamos", "bora", "clutch", "ace", "headshot",
    "matei", "morri", "insano", "absurdo", "irado", "gg", "ez", "pqp", "socorro", "corre", "cuidado",
    "what", "omg", "oh my god", "no way", "lets go", "let's go", "insane", "wtf", "holy", "clip that",
    "clipa", "clipa isso", "kill", "killed", "dead", "win", "won", "victory", "vitória", "booyah",
    "dios", "vamos", "increíble",
}
_MULTI = [h for h in HYPE_WORDS if " " in h]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w' ]+", "", text).strip()


_HYPE_NORM = {_norm(h) for h in HYPE_WORDS}
_MULTI_NORM = [_norm(h) for h in _MULTI]


@dataclass
class Signals:
    """Arrays alinhados por segundo (índice = segundo do vídeo)."""

    audio_z: np.ndarray  # z-score da energia (dB) por segundo
    scene: np.ndarray  # nº de cortes de cena no segundo
    hype: np.ndarray  # nº de palavras de empolgação no segundo
    speech: np.ndarray  # nº de palavras faladas no segundo
    # sinais extras (zeros quando não disponíveis)
    audio_local_z: np.ndarray | None = None  # volume comparado aos ~2 min em volta (grito numa parte calma)
    motion_z: np.ndarray | None = None  # movimento da imagem (ação)
    chat_z: np.ndarray | None = None  # pico de mensagens no chat da live (já adiantado para o lance)
    chat_fun: np.ndarray | None = None  # fração de risadas/empolgação no chat (0-1)
    heat: np.ndarray | None = None  # "mais repetidos" do YouTube, 0 = normal, 1 = o mais reassistido

    def __len__(self) -> int:
        return len(self.audio_z)

    def _arr(self, name: str) -> np.ndarray:
        v = getattr(self, name)
        return v if v is not None and len(v) == len(self) else np.zeros(len(self), dtype=np.float32)

    def score(self) -> np.ndarray:
        """Nota heurística por segundo. Sinais da audiência (chat, mais repetidos) pesam mais:
        são o público dizendo o que achou bom."""
        return (
            1.0 * np.clip(self.audio_z, 0, 4)
            + 0.6 * np.minimum(self.scene, 2)
            + 1.5 * np.minimum(self.hype, 3)
            + 0.08 * np.minimum(self.speech, 6)
            + 0.6 * np.clip(self._arr("audio_local_z"), 0, 4)
            + 0.35 * np.clip(self._arr("motion_z"), 0, 4)
            + 1.6 * np.clip(self._arr("chat_z"), 0, 5)
            + 2.0 * self._arr("chat_fun") * (self._arr("chat_z") > 1)
            + 4.0 * self._arr("heat")
        )


def audio_energy_z(wav_path: Path, n_seconds: int) -> np.ndarray:
    with wave.open(str(wav_path), "rb") as w:
        sr = w.getframerate()
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    out = np.full(n_seconds, -90.0, dtype=np.float32)
    for i in range(n_seconds):
        chunk = samples[i * sr:(i + 1) * sr]
        if chunk.size:
            rms = float(np.sqrt(np.mean(chunk**2)))
            out[i] = 20 * np.log10(max(rms, 1e-5))
    std = float(out.std())
    if std < 1e-6:
        return np.zeros(n_seconds, dtype=np.float32)
    return (out - float(np.median(out))) / std


def scene_cuts(video_path: Path, threshold: float = 0.35) -> list[float]:
    """Instantes (s) de troca de cena, analisando o vídeo em baixa resolução."""
    proc = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(video_path), "-an",
        "-vf", f"scale=160:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-",
    ])
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]


def word_counts(words: list[dict], n_seconds: int) -> tuple[np.ndarray, np.ndarray]:
    hype = np.zeros(n_seconds, dtype=np.float32)
    speech = np.zeros(n_seconds, dtype=np.float32)
    normed = [_norm(w["w"]) for w in words]
    for i, w in enumerate(words):
        sec = min(int(w["start"]), n_seconds - 1)
        if sec < 0:
            continue
        speech[sec] += 1
        token = normed[i]
        if token in _HYPE_NORM:
            hype[sec] += 1
        elif i + 1 < len(words):
            pair = f"{token} {normed[i + 1]}"
            if pair in _MULTI_NORM:
                hype[sec] += 1
    return hype, speech


def local_z(x: np.ndarray, half: int = 60) -> np.ndarray:
    """z-score de cada segundo em relação aos ~2 min em volta (mediana/MAD móveis)."""
    from .audience import _rolling_median

    base = _rolling_median(x, half)
    spread = _rolling_median(np.abs(x - base), half) * 1.4826
    return ((x - base) / np.maximum(spread, 0.25)).astype(np.float32)


def compute(video_path: Path, wav_path: Path | None, duration_s: float, words: list[dict],
            vis=None, audience: dict | None = None) -> Signals:
    """`vis` (visual.Visual) traz as trocas de cena e o movimento numa só passada; `audience` traz
    chat/mais repetidos quando o vídeo veio do YouTube."""
    from . import audience as aud

    n = max(1, int(np.ceil(duration_s)))
    audio = audio_energy_z(wav_path, n) if wav_path else np.zeros(n, dtype=np.float32)
    scene = np.zeros(n, dtype=np.float32)
    for t in (vis.scene_times if vis is not None and vis.scene_times is not None else scene_cuts(video_path)):
        scene[min(int(t), n - 1)] += 1
    hype, speech = word_counts(words, n)
    sig = Signals(audio, scene, hype, speech)
    if wav_path:
        sig.audio_local_z = local_z(audio)
    if vis is not None and vis.n:
        sig.motion_z = vis.motion_z(n)
    audience = audience or {}
    chat = audience.get("chat")
    if chat and chat.get("total", 0) >= 50:  # chat quase vazio não diz nada
        msgs = np.zeros(n, dtype=np.float32)
        fun = np.zeros(n, dtype=np.float32)
        m, f = np.asarray(chat["msgs"], dtype=np.float32)[:n], np.asarray(chat["fun"], dtype=np.float32)[:n]
        msgs[: m.size], fun[: f.size] = m, f
        sig.chat_z, sig.chat_fun = aud.chat_signal(msgs, fun)
    heat = aud.heatmap_per_second(audience.get("heatmap"), n)
    if heat is not None:
        sig.heat = aud.heat_relative(heat)
    return sig
