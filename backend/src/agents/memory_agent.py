"""Memory agent — retrieves KEDB and KADB context before specialist analysis."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agents.base import BaseAgent
from core.settings import resolve_agent_config_path
from models.schemas import MemoryContext

if TYPE_CHECKING:
    from core.state import OpsState

_CONFIG = resolve_agent_config_path("memory_agent.yaml")

# Cap free-text fields so retrieved playbooks/descriptions don't bloat downstream prompts.
_TEXT_FIELD_LIMIT = 800


def _trim_text(value: Any, limit: int = _TEXT_FIELD_LIMIT) -> Any:
    """Truncate long free-text values; leave non-strings untouched."""
    if not isinstance(value, str) or len(value) <= limit:
        return value
    return value[:limit].rstrip() + "…"


def _trim_match(match: Any, text_keys: tuple[str, ...]) -> dict[str, Any]:
    """Return a copy of a search hit with long text fields truncated."""
    if not isinstance(match, dict):
        return {}
    return {
        key: _trim_text(value) if key in text_keys else value
        for key, value in match.items()
    }


class MemoryAgent(BaseAgent):
    def __init__(self, llm_client: Any) -> None:
        super().__init__(_CONFIG, llm_client)

    async def run(self, state: OpsState) -> dict[str, Any]:
        query = state["query"]
        self.logger.info("Memory agent retrieving context", query=query)

        # The memory tools already return ranked, structured matches. Build the
        # MemoryContext deterministically rather than asking an LLM to re-serialise
        # potentially large documents into JSON — that round-trip is slow, costly,
        # and overflows max_tokens on rich entries, producing invalid/truncated JSON.
        kedb_hits = self.call_tool("search_kedb", query=query, top_k=5)
        kadb_hits = self.call_tool("search_kadb", query=query, top_k=3)

        kedb_matches = [
            _trim_match(hit, text_keys=("document", "resolution", "outcome"))
            for hit in (kedb_hits or [])
            if isinstance(hit, dict)
        ]
        kadb_matches = [
            _trim_match(hit, text_keys=("content",))
            for hit in (kadb_hits or [])
            if isinstance(hit, dict)
        ]

        memory_ctx = MemoryContext(kedb_matches=kedb_matches, kadb_matches=kadb_matches)

        self.logger.info(
            "Memory context retrieved",
            kedb_matches=len(memory_ctx.kedb_matches),
            kadb_matches=len(memory_ctx.kadb_matches),
        )

        return {"memory_context": memory_ctx}
