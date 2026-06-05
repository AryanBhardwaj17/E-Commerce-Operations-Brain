"""Central application settings loaded from environment variables and .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["azure", "openai", "ollama"]
CheckpointBackend = Literal["auto", "memory", "postgres"]
ExecutionBackend = Literal["in_process", "queued"]
RepositoryBackend = Literal["mock", "postgres"]


def _discover_backend_root() -> Path:
    settings_file = Path(__file__).resolve()
    for candidate in settings_file.parents:
        if (candidate / "pyproject.toml").exists():
            return candidate
    return settings_file.parents[2]


_BACKEND_ROOT = _discover_backend_root()
_REPO_ROOT = _BACKEND_ROOT.parent if _BACKEND_ROOT.name == "backend" else _BACKEND_ROOT


def _candidate_env_files() -> tuple[str, ...]:
    candidates: list[str] = []
    for env_path in (_BACKEND_ROOT / ".env", _REPO_ROOT / ".env"):
        env_text = str(env_path)
        if env_text not in candidates:
            candidates.append(env_text)
    return tuple(candidates)


def load_env_files() -> None:
    """Load the candidate .env files into ``os.environ``.

    The FastAPI app reads configuration through pydantic-settings, which loads these
    files into the settings object only. Standalone scripts (and the ChromaDB embedding
    functions, which read ``os.environ`` directly) need the values pushed into the
    process environment explicitly. Earlier candidates win, matching pydantic precedence.
    """
    from dotenv import load_dotenv  # noqa: PLC0415 — only needed by entrypoint scripts

    for env_file in _candidate_env_files():
        load_dotenv(env_file, override=False)


def get_backend_root() -> Path:
    return _BACKEND_ROOT


def get_repo_root() -> Path:
    return _REPO_ROOT


def get_config_dir() -> Path:
    config_dir = _BACKEND_ROOT / "config"
    if config_dir.exists():
        return config_dir
    return _BACKEND_ROOT / "configs"


def get_agents_dir() -> Path:
    agents_dir = get_config_dir() / "agents"
    if agents_dir.exists():
        return agents_dir
    return _BACKEND_ROOT / "agents"


def resolve_config_path(*parts: str) -> Path:
    return get_config_dir().joinpath(*parts)


def resolve_agent_config_path(name: str) -> Path:
    return get_agents_dir() / name


class AppSettings(BaseSettings):
    """Typed runtime configuration for the current process."""

    model_config = SettingsConfigDict(
        env_file=_candidate_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: LLMProvider = "azure"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    openai_api_version: str = "2025-04-01-preview"
    azure_openai_deployment: str = "gpt-4"
    azure_embedding_deployment: str = "text-embedding-005"
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.2"
    default_model: str | None = None
    fallback_model: str | None = None

    chromadb_host: str = "localhost"
    chromadb_port: int = 8001
    database_url: str | None = None
    checkpoint_backend: CheckpointBackend = "auto"
    repository_backend: RepositoryBackend = "postgres"
    repository_schema: str = "commerce"
    execution_backend: ExecutionBackend = "in_process"
    worker_poll_interval_seconds: float = 1.0
    worker_claim_timeout_seconds: float = 60.0
    runtime_store_dir: str = ".runtime"

    api_key: str = "dev-secret"
    cors_allowed_origins: str = "http://localhost:3000"

    langsmith_api_key: str | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_project: str = "ecommerce-ops-brain"
    langsmith_tracing: bool = True
    otel_exporter_otlp_endpoint: str | None = None

    def resolved_default_model(self) -> str:
        if self.default_model:
            return self.default_model
        if self.llm_provider == "azure":
            return self.azure_openai_deployment
        if self.llm_provider == "ollama":
            return self.ollama_model
        return "gpt-4o"

    def resolved_fallback_model(self) -> str:
        if self.fallback_model:
            return self.fallback_model
        if self.llm_provider == "azure":
            return self.azure_openai_deployment
        if self.llm_provider == "ollama":
            return self.ollama_model
        return "gpt-4o-mini"

    def resolve_model_for_provider(self, requested_model: str | None = None) -> str:
        if self.llm_provider == "azure":
            return self.azure_openai_deployment
        if self.llm_provider == "ollama":
            return requested_model or self.ollama_model
        return requested_model or self.resolved_default_model()

    def normalized_database_url(self) -> str | None:
        if not self.database_url:
            return None
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    def resolved_runtime_store_dir(self) -> Path:
        runtime_dir = Path(self.runtime_store_dir)
        if runtime_dir.is_absolute():
            return runtime_dir
        return get_backend_root() / runtime_dir

    def resolved_cors_allowed_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
