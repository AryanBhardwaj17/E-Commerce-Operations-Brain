"""Memory routes — search KEDB and KADB."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Query

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/kedb/search")
async def search_kedb(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, ge=1, le=20),
) -> dict:
    from memory.kedb import KEDBStore  # noqa: PLC0415
    results = KEDBStore.get_instance().search_semantic(q, top_k=top_k)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/kedb/{error_code}")
async def get_kedb_entry(error_code: str) -> dict:
    from memory.kedb import KEDBStore  # noqa: PLC0415
    entry = KEDBStore.get_instance().lookup_by_error_code(error_code)
    if entry is None:
        from fastapi import HTTPException  # noqa: PLC0415
        raise HTTPException(status_code=404, detail=f"Error code '{error_code}' not found.")
    return entry


@router.get("/kadb/search")
async def search_kadb(
    q: str = Query(..., description="Search query"),
    artifact_type: str | None = Query(None, description="Filter by artifact type"),
    top_k: int = Query(3, ge=1, le=10),
) -> dict:
    from memory.kadb import KADBStore  # noqa: PLC0415
    results = KADBStore.get_instance().search(q, artifact_type=artifact_type, top_k=top_k)
    return {"query": q, "results": results, "count": len(results)}
