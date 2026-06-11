#!/usr/bin/env python
"""Seed the KEDB (Known Error Database) with initial entries from YAML."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import structlog
import yaml

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logger = structlog.get_logger(__name__)

SEED_FILE = BACKEND_ROOT / "src" / "data" / "seeds" / "kedb_entries.yaml"


def main() -> None:
    from src.core.settings import load_env_files  # noqa: PLC0415
    from src.memory.kedb import KEDBStore  # noqa: PLC0415

    load_env_files()  # populate os.environ from .env for the embedding function

    host = os.getenv("CHROMADB_HOST", "localhost")
    port = int(os.getenv("CHROMADB_PORT", "8001"))
    api_key = os.getenv("OPENAI_API_KEY", "")

    store = KEDBStore.initialise(host=host, port=port, openai_api_key=api_key)

    with open(SEED_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = data.get("entries", [])
    seeded = 0
    for entry in entries:
        store.add_entry(dict(entry))
        seeded += 1
        print(f"  ✓ {entry['error_code']}: {entry['title']}")

    print(f"\nSeeded {seeded} KEDB entries.")


if __name__ == "__main__":
    main()
