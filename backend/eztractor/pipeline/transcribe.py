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
_model_device: str | None = None


def _cuda_model(name: str):
    """Tenta a placa de vídeo NVIDIA. Roda um trecho curto de teste porque as DLLs do CUDA
    (cublas/cudnn) só são carregadas na hora de transcrever — se faltarem, o erro aparece aqui."""
    import ctranslate2
    from faster_whisper import WhisperModel

    if ctranslate2.get_cuda_device_count() <= 0:
        return None
    model = WhisperModel(name, device="cuda", compute_type="float16")
    segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language="en")
    list(segments)
    return model


def _load_model():
    """device: EZT_WHISPER_DEVICE = auto (padrão: placa de vídeo se funcionar, senão processador) | cpu | cuda."""
    global _model, _model_device
    if _model is not None:
        return _model
    from faster_whisper import WhisperModel

    s = get_settings()
    if s.whisper_device in ("auto", "cuda"):
        try:
            m = _cuda_model(s.whisper_model)
            if m is not None:
                _model, _model_device = m, "cuda"
                log.info("Whisper usando a placa de vídeo (CUDA)")
                return _model
        except Exception as e:  # DLL do CUDA ausente, driver antigo, pouca memória de vídeo…
            if s.whisper_device == "cuda":
                raise
            log.warning("placa de vídeo indisponível para o Whisper (%s); usando o processador", e)
    _model, _model_device = WhisperModel(s.whisper_model, device="cpu", compute_type="int8"), "cpu"
    return _model


def _is_gpu_error(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("cublas", "cudnn", "cuda", "cudart"))


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


def transcribe(
    wav: Path, language: str | None = None, on_progress=None,
) -> tuple[list[dict], str | None]:
    """Retorna (palavras, idioma_detectado). Lista vazia se a transcrição estiver desligada."""
    if get_settings().transcriber == "none":
        return [], language
    try:
        model = _load_model()
    except ImportError:
        log.warning("faster-whisper não instalado; seguindo sem transcrição")
        return [], language

    audio = load_wav(wav)
    try:
        segments, info = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=True)
    except RuntimeError as e:
        global _model, _model_device
        if _model_device != "cuda" or not _is_gpu_error(e) or get_settings().whisper_device == "cuda":
            raise
        log.warning("erro na placa de vídeo (%s); refazendo no processador", e)
        from faster_whisper import WhisperModel

        _model, _model_device = WhisperModel(get_settings().whisper_model, device="cpu", compute_type="int8"), "cpu"
        model = _model
        segments, info = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=True)
    from ..control import checkpoint

    words: list[dict] = []
    total = float(getattr(info, "duration", 0) or 0)
    for seg in segments:
        checkpoint()  # pausar/cancelar entre trechos da fala
        if on_progress and total:
            on_progress(min(1.0, seg.end / total))
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"w": text, "start": round(w.start, 2), "end": round(w.end, 2)})
    return words, info.language
