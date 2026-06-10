"""LangSmith observability bootstrap."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.settings import AppSettings

_langsmith_client: Any = None


def configure_langsmith(settings: AppSettings) -> None:
    """Initialise LangSmith tracing using settings-backed environment values."""
    if not settings.langsmith_api_key:
        return

    try:
        from langsmith import Client  # noqa: PLC0415

        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
        os.environ["LANGSMITH_TRACING"] = "true" if settings.langsmith_tracing else "false"

        if settings.langsmith_project:
            os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project

        _client = Client(
            api_url=settings.langsmith_endpoint,
            api_key=settings.langsmith_api_key,
        )

        import observability.langsmith as _self  # noqa: PLC0415
        _self._langsmith_client = _client
    except ImportError:
        pass
