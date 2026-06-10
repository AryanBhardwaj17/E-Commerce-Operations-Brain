"""Repository registry composition helpers."""
from __future__ import annotations

from application.repositories import RepositoryRegistry, configure_repository_registry
from core.settings import AppSettings
from infrastructure.repositories import build_repository_registry


def initialize_repository_registry(settings: AppSettings | None = None) -> RepositoryRegistry:
    """Bind the application's repository ports to the current infrastructure adapters."""
    return configure_repository_registry(build_repository_registry(settings))
