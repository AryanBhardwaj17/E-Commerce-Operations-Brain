"""Observability composition helpers."""
from __future__ import annotations

from core.settings import AppSettings


def initialize_observability(settings: AppSettings) -> None:
    """Configure optional observability backends for the current process."""
    if settings.langsmith_api_key:
        from observability.langsmith import configure_langsmith  # noqa: PLC0415

        configure_langsmith(settings)
