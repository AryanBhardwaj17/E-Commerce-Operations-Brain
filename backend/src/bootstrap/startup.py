"""Application startup and shutdown composition root."""
from __future__ import annotations

import structlog

from bootstrap.memory import initialize_memory_stores
from bootstrap.observability import initialize_observability
from bootstrap.repositories import initialize_repository_registry
from bootstrap.tools import initialize_tool_registry
from core.orchestrator import close_runtime_resources
from core.settings import AppSettings
from execution.query_runner import get_query_runner, reset_query_runner_cache
from infrastructure.repositories import resolve_repository_backend
from observability.logging import configure_logging

logger = structlog.get_logger(__name__)


def initialize_application(settings: AppSettings) -> None:
    """Initialise logging, tools, memory stores, and observability."""
    configure_logging()

    backend = resolve_repository_backend(settings)
    repositories = initialize_repository_registry(settings)
    logger.info(
        "Repository registry initialised",
        backend=backend,
        schema=settings.repository_schema if backend == "postgres" else None,
        sales=repositories.sales.__class__.__name__,
        inventory=repositories.inventory.__class__.__name__,
        marketing=repositories.marketing.__class__.__name__,
        support=repositories.support.__class__.__name__,
    )

    registry = initialize_tool_registry()
    logger.info("Tool registry initialised", tools=registry.all_names())

    initialize_memory_stores(settings)
    logger.info(
        "ChromaDB stores initialised",
        provider=settings.llm_provider,
        embedding_deployment=settings.azure_embedding_deployment,
    )

    initialize_observability(settings)


async def shutdown_application() -> None:
    """Clean up runtime services and in-process execution backends."""
    await get_query_runner().shutdown()
    reset_query_runner_cache()
    await close_runtime_resources()
