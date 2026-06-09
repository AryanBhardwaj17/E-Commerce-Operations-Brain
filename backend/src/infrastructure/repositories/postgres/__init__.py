"""Postgres-backed repository adapters."""
from infrastructure.repositories.postgres.factory import (
    build_postgres_repository_registry,
    initialize_postgres_repository_storage,
)

__all__ = [
    "build_postgres_repository_registry",
    "initialize_postgres_repository_storage",
]
