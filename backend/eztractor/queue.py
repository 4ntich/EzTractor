import importlib
import threading

from .config import get_settings


def _resolve(func_path: str):
    module, name = func_path.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)


def enqueue(func_path: str, *args) -> None:
    """Agenda `func_path(*args)` conforme EZT_QUEUE_MODE (rq | inline | sync)."""
    mode = get_settings().queue_mode
    if mode == "rq":
        from redis import Redis
        from rq import Queue

        q = Queue("eztractor", connection=Redis.from_url(get_settings().redis_url))
        q.enqueue(func_path, *args, job_timeout=6 * 3600)
    elif mode == "inline":
        threading.Thread(target=_resolve(func_path), args=args, daemon=True).start()
    elif mode == "sync":  # testes
        _resolve(func_path)(*args)
    else:
        raise ValueError(f"queue_mode desconhecido: {mode}")


def enqueue_project(project_id: str) -> None:
    enqueue("eztractor.pipeline.run.process_project", project_id)


def enqueue_render(clip_id: str) -> None:
    enqueue("eztractor.pipeline.run.render_one", clip_id)
