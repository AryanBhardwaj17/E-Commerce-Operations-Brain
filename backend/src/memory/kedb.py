"""Known Error Database — ChromaDB semantic + JSON structured lookup."""
from __future__ import annotations

import ast
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import chromadb
import structlog
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

logger = structlog.get_logger(__name__)

_KEDB_JSON_PATH = Path(__file__).parent.parent / "data" / "kedb.json"
_COLLECTION_NAME = "kedb"


def _coerce_list(value: Any) -> list[str]:
    """Coerce a metadata field into a list of strings.

    List values are stored in ChromaDB metadata as ``str(list)`` (a Python repr),
    so reconstruct them here; tolerate plain comma-delimited strings too.
    """
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip() if value is not None else ""
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except (ValueError, SyntaxError):
        pass
    return [part.strip() for part in text.split(",") if part.strip()]


def _build_embedding_fn():
    """Return an embedding function matching the configured LLM_PROVIDER."""
    provider = os.getenv("LLM_PROVIDER", "azure").lower()
    if provider == "azure":
        return OpenAIEmbeddingFunction(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_base=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_type="azure",
            api_version=os.getenv("OPENAI_API_VERSION", "2025-04-01-preview"),
            deployment_id=os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-005"),
            model_name="text-embedding-3-small",
        )
    # openai or ollama (ollama doesn't have a native embedding fn — fall back to OpenAI)
    return OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model_name="text-embedding-3-small",
    )


class KEDBStore:
    """
    Dual-store Known Error Database.

    - ChromaDB collection for semantic similarity search
    - JSON file for structured lookup by error_code
    """

    _instance: KEDBStore | None = None

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8001,
        openai_api_key: str = "",  # kept for backward-compat; provider detection is env-based
    ) -> None:
        self._client = chromadb.HttpClient(host=host, port=port)
        embedding_fn = _build_embedding_fn()
        self._collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self._json_store: dict[str, Any] = self._load_json()

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> KEDBStore:
        if cls._instance is None:
            raise RuntimeError(
                "KEDBStore not initialised. Call KEDBStore.initialise() first."
            )
        return cls._instance

    @classmethod
    def initialise(cls, host: str, port: int, openai_api_key: str) -> KEDBStore:
        cls._instance = cls(host=host, port=port, openai_api_key=openai_api_key)
        return cls._instance

    # ── JSON persistence ──────────────────────────────────────────────────────

    def _load_json(self) -> dict[str, Any]:
        if _KEDB_JSON_PATH.exists():
            with open(_KEDB_JSON_PATH, encoding="utf-8") as f:
                data = json.load(f)
                return {entry["error_code"]: entry for entry in data.get("entries", [])}
        return {}

    def _save_json(self) -> None:
        _KEDB_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_KEDB_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"entries": list(self._json_store.values())}, f, indent=2, default=str)

    # ── Public API ────────────────────────────────────────────────────────────

    def search_semantic(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic similarity search across KEDB entries."""
        try:
            count = self._collection.count()
            if count == 0:
                return []

            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )

            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])
            distances = results.get("distances", [])
            if not documents or not metadatas or not distances:
                return []

            hits = []
            for doc, meta, dist in zip(
                documents[0],
                metadatas[0],
                distances[0],
                strict=True,
            ):
                hits.append(
                    {
                        "error_code": meta.get("error_code"),
                        "title": meta.get("title"),
                        "root_cause": meta.get("root_cause"),
                        "resolution": meta.get("resolution"),
                        "outcome": meta.get("outcome"),
                        "recommended_actions": _coerce_list(meta.get("recommended_actions")),
                        "affected_domains": _coerce_list(meta.get("affected_domains")),
                        "similarity_score": round(1.0 - dist, 4),
                        "document": doc,
                        "occurrence_count": meta.get("occurrence_count", 1),
                    }
                )
            return sorted(hits, key=lambda x: x["similarity_score"], reverse=True)
        except Exception as exc:
            logger.error("KEDB semantic search failed", error=str(exc))
            return []

    def lookup_by_error_code(self, error_code: str) -> dict[str, Any] | None:
        return self._json_store.get(error_code)

    def add_entry(self, entry: dict[str, Any]) -> str:
        """Add a new KEDB entry. Returns the entry ID."""
        entry_id = entry.get("id") or str(uuid4())
        entry.setdefault("id", entry_id)
        entry.setdefault("created_at", datetime.now(UTC).isoformat())
        entry.setdefault("occurrence_count", 1)

        # Add to ChromaDB
        self._collection.upsert(
            ids=[entry_id],
            documents=[entry.get("description", entry.get("title", ""))],
            metadatas={
                k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                for k, v in entry.items()
                if k != "id"
            },
        )

        # Add to JSON store
        if entry.get("error_code"):
            self._json_store[entry["error_code"]] = entry
            self._save_json()

        logger.info("KEDB entry added", entry_id=entry_id, error_code=entry.get("error_code"))
        return entry_id

    def increment_occurrence(self, entry_id: str) -> None:
        """Increment the occurrence count for a known error."""
        result = self._collection.get(ids=[entry_id], include=["metadatas"])
        if not result["ids"]:
            logger.warning("KEDB entry not found for increment", entry_id=entry_id)
            return
        metadatas = result.get("metadatas") or []
        if not metadatas:
            logger.warning("KEDB metadata missing for increment", entry_id=entry_id)
            return
        meta = dict(metadatas[0])
        occurrence_value = meta.get("occurrence_count", 1)
        if isinstance(occurrence_value, (int, float, str)):
            occurrence_count = int(occurrence_value)
        else:
            occurrence_count = 1
        meta["occurrence_count"] = occurrence_count + 1
        self._collection.update(ids=[entry_id], metadatas=[meta])

        # Update JSON store
        for entry in self._json_store.values():
            if entry.get("id") == entry_id:
                entry["occurrence_count"] = meta["occurrence_count"]
                break
        self._save_json()
