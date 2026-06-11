#!/usr/bin/env python
"""Seed the KADB (Knowledge Artifact Database) with initial artifacts from YAML."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import structlog

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logger = structlog.get_logger(__name__)

SEED_FILE = BACKEND_ROOT / "src" / "data" / "seeds" / "kadb_artifacts.yaml"


def main() -> None:
    from src.core.settings import load_env_files  # noqa: PLC0415
    from src.memory.kadb import KADBStore  # noqa: PLC0415

    load_env_files()  # populate os.environ from .env for the embedding function

    host = os.getenv("CHROMADB_HOST", "localhost")
    port = int(os.getenv("CHROMADB_PORT", "8001"))
    api_key = os.getenv("OPENAI_API_KEY", "")

    store = KADBStore.initialise(host=host, port=port, openai_api_key=api_key)
    count = store.ingest_from_yaml(str(SEED_FILE))
    print(f"Seeded {count} KADB artifacts.")


if __name__ == "__main__":
    main()
