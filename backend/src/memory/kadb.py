"""Knowledge Artifact Database — ChromaDB-backed runbook and SOP store."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import chromadb
import structlog
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

logger = structlog.get_logger(__name__)

_COLLECTION_NAME = "kadb"


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
    return OpenAIEmbeddingFunction(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model_name="text-embedding-3-small",
    )


class KADBStore:
    """
    Knowledge Artifact Database.

    Stores runbooks, SOPs, playbooks, and escalation guides.
    Supports full-text + semantic search by artifact_type filter.
    """

    _instance: KADBStore | None = None

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

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> KADBStore:
        if cls._instance is None:
            raise RuntimeError(
                "KADBStore not initialised. Call KADBStore.initialise() first."
            )
        return cls._instance

    @classmethod
    def initialise(cls, host: str, port: int, openai_api_key: str) -> KADBStore:
        cls._instance = cls(host=host, port=port, openai_api_key=openai_api_key)
        return cls._instance

    # ── Public API ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        artifact_type: str | None = None,
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Semantic search with optional artifact_type filter."""
        try:
            count = self._collection.count()
            if count == 0:
                return []

            where = {"artifact_type": artifact_type} if artifact_type else None
            kwargs: dict[str, Any] = {
                "query_texts": [query],
                "n_results": min(top_k, count),
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where

            results = self._collection.query(**kwargs)
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
                        "id": meta.get("artifact_id"),
                        "title": meta.get("title"),
                        "artifact_type": meta.get("artifact_type"),
                        "content": doc,
                        "tags": meta.get("tags", ""),
                        "similarity_score": round(1.0 - dist, 4),
                    }
                )
            return sorted(hits, key=lambda x: x["similarity_score"], reverse=True)
        except Exception as exc:
            logger.error("KADB search failed", error=str(exc))
            return []

    def add_artifact(self, artifact: dict[str, Any]) -> str:
        """Add a new artifact. Returns artifact ID."""
        artifact_id = artifact.get("artifact_id") or str(uuid4())
        artifact.setdefault("artifact_id", artifact_id)
        artifact.setdefault("created_at", datetime.now(UTC).isoformat())

        content = artifact.pop("content", artifact.get("title", ""))

        self._collection.upsert(
            ids=[artifact_id],
            documents=[content],
            metadatas={
                k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                for k, v in artifact.items()
            },
        )
        logger.info("KADB artifact added", artifact_id=artifact_id, title=artifact.get("title"))
        return artifact_id

    def ingest_from_yaml(self, path: str) -> int:
        """Bulk-ingest artifacts from a YAML file. Returns count of artifacts added."""
        import yaml  # noqa: PLC0415

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        artifacts = data.get("artifacts", [])
        for artifact in artifacts:
            self.add_artifact(dict(artifact))

        logger.info("KADB ingested artifacts from YAML", count=len(artifacts), path=path)
        return len(artifacts)
