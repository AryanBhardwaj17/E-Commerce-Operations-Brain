"""Load backend-neutral application seed data from JSON files."""
from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

_SEED_DIR = Path(__file__).resolve().parent / "application"


def _load_seed_file(name: str) -> dict[str, Any]:
    payload = json.loads((_SEED_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Seed file {name} must contain a JSON object.")
    return payload


@lru_cache(maxsize=1)
def _cached_seed_payloads() -> dict[str, dict[str, Any]]:
    return {
        "inventory": _load_seed_file("inventory.json"),
        "sales": _load_seed_file("sales.json"),
        "marketing": _load_seed_file("marketing.json"),
        "support": _load_seed_file("support.json"),
    }


def get_inventory_seed() -> dict[str, Any]:
    return deepcopy(_cached_seed_payloads()["inventory"])


def get_sales_seed() -> dict[str, Any]:
    return deepcopy(_cached_seed_payloads()["sales"])


def get_marketing_seed() -> dict[str, Any]:
    return deepcopy(_cached_seed_payloads()["marketing"])


def get_support_seed() -> dict[str, Any]:
    return deepcopy(_cached_seed_payloads()["support"])