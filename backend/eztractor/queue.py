import importlib
import logging
import queue
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


log = logging.getLogger(__name__)
_projects: "queue.Queue[str] | None" = None
_projects_lock = threading.Lock()


def _project_worker() -> None:
    run = _resolve("eztractor.pipeline.run.process_project")
    while True:
        project_id = _projects.get()
        try:
            run(project_id)
        except Exception:  # process_project já registra o erro no projeto; nunca derruba a fila
            log.exception("falha ao processar %s", project_id)
        finally:
            _projects.task_done()


def enqueue_project(project_id: str) -> None:
    """No app (modo inline) os projetos são processados UM DE CADA VEZ, na ordem em que entraram:
    um lote de 20 vídeos não pode rodar 20 transcrições/renders ao mesmo tempo e travar o PC.
    (Edições de clipe e re-render continuam imediatos, fora desta fila.)"""
    global _projects
    if get_settings().queue_mode != "inline":
        enqueue("eztractor.pipeline.run.process_project", project_id)
        return
    with _projects_lock:
        if _projects is None:
            _projects = queue.Queue()
            threading.Thread(target=_project_worker, daemon=True, name="ezt-fila-projetos").start()
    _projects.put(project_id)


def enqueue_render(clip_id: str) -> None:
    enqueue("eztractor.pipeline.run.render_one", clip_id)


def enqueue_project_render(project_id: str) -> None:
    """Renderiza de novo todos os clipes de um projeto, um por vez."""
    enqueue("eztractor.pipeline.run.render_all", project_id)
