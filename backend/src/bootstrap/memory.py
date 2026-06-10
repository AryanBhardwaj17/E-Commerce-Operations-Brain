"""Memory store composition helpers."""
from __future__ import annotations

from core.settings import AppSettings
from memory.kadb import KADBStore
from memory.kedb import KEDBStore


def initialize_memory_stores(settings: AppSettings) -> None:
    """Initialise Chroma-backed memory stores for the current process."""
    openai_api_key = settings.openai_api_key or ""
    KEDBStore.initialise(
        host=settings.chromadb_host,
        port=settings.chromadb_port,
        openai_api_key=openai_api_key,
    )
    KADBStore.initialise(
        host=settings.chromadb_host,
        port=settings.chromadb_port,
        openai_api_key=openai_api_key,
    )
