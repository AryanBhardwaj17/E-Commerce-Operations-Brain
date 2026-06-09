"""Shared Postgres access helpers for repository adapters."""
from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from core.settings import AppSettings

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str, *, field_name: str) -> str:
    normalized = name.strip()
    if not _IDENTIFIER_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a valid SQL identifier")
    return normalized


@dataclass(frozen=True, slots=True)
class PostgresRepositoryDatabase:
    database_url: str
    schema: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema", _validate_identifier(self.schema, field_name="schema"))

    @classmethod
    def from_settings(cls, settings: AppSettings) -> PostgresRepositoryDatabase:
        database_url = settings.normalized_database_url()
        if not database_url:
            raise RuntimeError("REPOSITORY_BACKEND=postgres requires DATABASE_URL to be configured.")
        return cls(database_url=database_url, schema=settings.repository_schema)

    @contextmanager
    def connection(self) -> Iterator[Any]:
        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            yield connection

    def qualified(self, table_name: str) -> str:
        normalized_table = _validate_identifier(table_name, field_name="table_name")
        return f"{self.schema}.{normalized_table}"
