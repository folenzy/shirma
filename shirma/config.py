from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHIRMA_", env_file=".env", extra="ignore")

    # Куда пересылать запросы: любой OpenAI-совместимый адрес
    # (OpenAI, OpenRouter, Ollama, LM Studio, vLLM). «mock» — встроенная
    # учебная модель, чтобы всё работало без ключей и сети.
    upstream_url: str = "mock"
    # Если задан — подставляется вместо ключа клиента. Если нет — ключ
    # клиента из Authorization уходит наверх как есть.
    upstream_api_key: str | None = None
    timeout: float = 120.0
    policy: Path | None = None
    # Демо-страница и /api/* показывают таблицу «метка → значение».
    # В боевом развёртывании выключайте.
    demo: bool = True
