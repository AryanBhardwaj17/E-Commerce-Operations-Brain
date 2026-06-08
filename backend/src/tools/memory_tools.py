"""Memory tools — search KEDB and KADB — registered with ToolRegistry."""
from __future__ import annotations

from typing import Any

from tools.registry import ToolDefinition, ToolRegistry


def search_kedb(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Search the Known Error Database for semantically similar past incidents."""
    # Import lazily to avoid circular deps and allow unit testing without ChromaDB
    from memory.kedb import KEDBStore  # noqa: PLC0415
    store = KEDBStore.get_instance()
    return store.search_semantic(query, top_k=top_k)


def lookup_kedb_by_code(error_code: str) -> dict[str, Any] | None:
    """Look up a KEDB entry by its structured error code."""
    from memory.kedb import KEDBStore  # noqa: PLC0415
    store = KEDBStore.get_instance()
    return store.lookup_by_error_code(error_code)


def search_kadb(query: str, artifact_type: str | None = None, top_k: int = 3) -> list[dict[str, Any]]:
    """Search the Knowledge Artifact Database for relevant runbooks/SOPs."""
    from memory.kadb import KADBStore  # noqa: PLC0415
    store = KADBStore.get_instance()
    return store.search(query, artifact_type=artifact_type, top_k=top_k)


# ── Registration ──────────────────────────────────────────────────────────────
def register_memory_tools() -> None:
    registry = ToolRegistry.get_instance()
    for fn, name, desc in [
        (search_kedb, "search_kedb", "Search KEDB for similar past incidents"),
        (lookup_kedb_by_code, "lookup_kedb_by_code", "Lookup KEDB entry by error code"),
        (search_kadb, "search_kadb", "Search KADB for runbooks and SOPs"),
    ]:
        registry.register(ToolDefinition(name=name, description=desc, function=fn))
