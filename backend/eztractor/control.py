"""Pausar / continuar / cancelar um processamento em andamento.

O pedido fica na coluna `projects.control` ("run" | "pause" | "cancel"). O pipeline consulta esse valor
em pontos de checagem (entre etapas, entre trechos da transcrição, no progresso do download) e também
enquanto o ffmpeg roda: na pausa o processo do ffmpeg é suspenso, no cancelamento ele é encerrado.
"""

import contextvars
import subprocess
import sys
import time
from collections.abc import Callable

POLL_S = 0.5


class Cancelled(Exception):
    """O usuário cancelou o processamento."""


class Control:
    def __init__(self, project_id: str, on_pause: Callable[[bool], None] | None = None):
        self.project_id = project_id
        self.on_pause = on_pause  # avisa o pipeline para marcar o status "paused"/"processing"
        self._cached = "run"
        self._read_at = 0.0

    def state(self, fresh: bool = False) -> str:
        now = time.monotonic()
        if fresh or now - self._read_at >= POLL_S:
            from .db import session_factory
            from .models import Project

            with session_factory()() as db:
                p = db.get(Project, self.project_id)
                self._cached = (p.control if p is not None else "cancel") or "run"
            self._read_at = now
        return self._cached

    def check(self, proc: subprocess.Popen | None = None) -> None:
        """Sai na hora se cancelado; se pausado, espera aqui até continuar (suspendendo `proc`)."""
        s = self.state()
        if s == "cancel":
            raise Cancelled()
        if s != "pause":
            return
        if proc is not None:
            suspend(proc)
        if self.on_pause:
            self.on_pause(True)
        try:
            while True:
                time.sleep(POLL_S)
                s = self.state(fresh=True)
                if s == "cancel":
                    raise Cancelled()
                if s != "pause":
                    break
        finally:
            if proc is not None and proc.poll() is None:
                resume(proc)
        if self.on_pause:
            self.on_pause(False)


_current: contextvars.ContextVar[Control | None] = contextvars.ContextVar("ezt_control", default=None)


def current() -> Control | None:
    return _current.get()


def activate(ctrl: Control | None):
    return _current.set(ctrl)


def checkpoint() -> None:
    ctrl = current()
    if ctrl is not None:
        ctrl.check()


# ---------------------------------------------------------------- suspender processos (ffmpeg)
def suspend(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.ntdll.NtSuspendProcess(int(proc._handle))  # type: ignore[attr-defined]
    else:
        import signal

        proc.send_signal(signal.SIGSTOP)


def resume(proc: subprocess.Popen) -> None:
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.ntdll.NtResumeProcess(int(proc._handle))  # type: ignore[attr-defined]
    else:
        import signal

        proc.send_signal(signal.SIGCONT)
