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
    jwt_secret: str = "dev-only-secret-change-me-in-production-0123456789"
    jwt_ttl_hours: int = 24 * 7
    cors_origins: str = "http://localhost:3000"

    # Créditos: 1 crédito por minuto de vídeo processado (arredondado para cima)
    signup_bonus_credits: int = 120
    max_upload_mb: int = 4096

    # IA
    transcriber: str = "faster_whisper"  # faster_whisper | none
    whisper_model: str = "small"
    ranker: str = "claude"  # claude | heuristic
    claude_model: str = "claude-opus-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
