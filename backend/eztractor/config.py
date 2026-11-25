from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EZT_", extra="ignore")

    database_url: str = "sqlite:///./eztractor.db"
    redis_url: str = "redis://localhost:6379/0"
    # "rq" = fila Redis + worker separado; "inline" = roda o pipeline numa thread da API (dev/testes)
    queue_mode: str = "inline"
    storage_dir: Path = Path("./data")
    # Pasta com o site já compilado (web/out). Se existir, a API também serve o site.
    web_dir: Path | None = None
    # Pasta das fontes dos templates (padrão: web/public/fonts do repositório)
    fonts_dir: Path | None = None
    jwt_secret: str = "dev-only-secret-change-me-in-production-0123456789"
    jwt_ttl_hours: int = 24 * 30
    cors_origins: str = "http://localhost:3000"

    # Senha de acesso. Vazia = sem login (uso só na sua máquina).
    # Defina uma senha se for publicar o app na internet.
    app_password: str = ""

    max_upload_mb: int = 8192
    max_video_minutes: int = 600
    render_height: int = 1920  # 1920 => 1080x1920; 1280 => 720x1280 (mais rápido)

    # IA
    transcriber: str = "faster_whisper"  # faster_whisper | none
    whisper_model: str = "small"
    # Método padrão de análise: heuristic (grátis) | ollama (IA local, grátis) | claude (API paga)
    ranker: str = "heuristic"
    claude_model: str = "claude-opus-5-5"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_s: int = 900


@lru_cache
def get_settings() -> Settings:
    return Settings()
