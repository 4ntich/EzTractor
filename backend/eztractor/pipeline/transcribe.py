"""Transcrição com marcação de tempo por palavra.

Formato de saída: [{"w": "palavra", "start": 1.23, "end": 1.50}, ...]
"""

import logging
from pathlib import Path

from ..config import get_settings

log = logging.getLogger(__name__)

_model = None


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(get_settings().whisper_model, device="auto", compute_type="int8")
    return _model


def transcribe(wav: Path, language: str | None = None) -> tuple[list[dict], str | None]:
    """Retorna (palavras, idioma_detectado). Lista vazia se a transcrição estiver desligada."""
    if get_settings().transcriber == "none":
        return [], language
    try:
        model = _load_model()
    except ImportError:
        log.warning("faster-whisper não instalado; seguindo sem transcrição")
        return [], language

    segments, info = model.transcribe(str(wav), language=language, word_timestamps=True, vad_filter=True)
    words: list[dict] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"w": text, "start": round(w.start, 2), "end": round(w.end, 2)})
    return words, info.language
