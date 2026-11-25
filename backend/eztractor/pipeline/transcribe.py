"""Transcrição com marcação de tempo por palavra.

Formato de saída: [{"w": "palavra", "start": 1.23, "end": 1.50}, ...]
"""

import logging
import wave
from pathlib import Path

import numpy as np

from ..config import get_settings

log = logging.getLogger(__name__)

_model = None


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(get_settings().whisper_model, device="auto", compute_type="int8")
    return _model


def load_wav(wav: Path) -> np.ndarray:
    """Lê o WAV mono 16 kHz (gerado por media.extract_audio) como float32 em [-1, 1].

    Entregar o áudio já decodificado ao faster-whisper evita o leitor interno dele (PyAV),
    que quebra em versões novas do PyAV ("unexpected keyword argument 'metadata_errors'").
    """
    with wave.open(str(wav), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != 16000:
            raise ValueError("áudio precisa ser WAV mono 16 kHz PCM16")
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(wav: Path, language: str | None = None) -> tuple[list[dict], str | None]:
    """Retorna (palavras, idioma_detectado). Lista vazia se a transcrição estiver desligada."""
    if get_settings().transcriber == "none":
        return [], language
    try:
        model = _load_model()
    except ImportError:
        log.warning("faster-whisper não instalado; seguindo sem transcrição")
        return [], language

    segments, info = model.transcribe(load_wav(wav), language=language, word_timestamps=True, vad_filter=True)
    words: list[dict] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"w": text, "start": round(w.start, 2), "end": round(w.end, 2)})
    return words, info.language
