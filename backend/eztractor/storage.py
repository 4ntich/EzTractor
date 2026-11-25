"""Armazenamento de arquivos. MVP: disco local. Trocar por S3/R2 mantendo esta interface."""

from pathlib import Path

from .config import get_settings


def root() -> Path:
    p = get_settings().storage_dir.resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def path_for(key: str) -> Path:
    p = (root() / key).resolve()
    if root() not in p.parents and p != root():
        raise ValueError("chave de storage inválida")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def project_dir(project_id: str) -> str:
    return f"projects/{project_id}"
