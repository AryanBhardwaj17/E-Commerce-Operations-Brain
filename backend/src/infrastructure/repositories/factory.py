"""Select and construct repository adapters for the current runtime."""
from __future__ import annotations

from application.repositories import RepositoryRegistry
from core.settings import AppSettings, RepositoryBackend, get_settings
from infrastructure.repositories.mock import build_mock_repository_registry


def resolve_repository_backend(settings: AppSettings | None = None) -> RepositoryBackend:
    active_settings = settings or get_settings()
    return active_settings.repository_backend


def _validate_repository_backend(settings: AppSettings, backend: RepositoryBackend) -> None:
    if backend == "postgres" and not settings.normalized_database_url():
        raise RuntimeError("REPOSITORY_BACKEND=postgres requires DATABASE_URL to be configured.")


def build_repository_registry(settings: AppSettings | None = None) -> RepositoryRegistry:
    active_settings = settings or get_settings()
    backend = resolve_repository_backend(active_settings)
    _validate_repository_backend(active_settings, backend)
    if backend == "postgres":
        from infrastructure.repositories.postgres import (
            build_postgres_repository_registry,  # noqa: PLC0415
        )

        return build_postgres_repository_registry(active_settings)
    return build_mock_repository_registry()
