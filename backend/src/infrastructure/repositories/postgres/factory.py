"""Factory for Postgres-backed repository adapters."""
from __future__ import annotations

import hashlib

from application.repositories import RepositoryRegistry
from core.settings import AppSettings
from infrastructure.repositories.postgres.database import PostgresRepositoryDatabase
from infrastructure.repositories.postgres.inventory import PostgresInventoryRepository
from infrastructure.repositories.postgres.marketing import PostgresMarketingRepository
from infrastructure.repositories.postgres.migrations import apply_repository_migrations
from infrastructure.repositories.postgres.sales import PostgresSalesRepository
from infrastructure.repositories.postgres.seeding import seed_repository_data
from infrastructure.repositories.postgres.support import PostgresSupportRepository


def _bootstrap_lock_keys(schema: str) -> tuple[int, int]:
    digest = hashlib.blake2s(f"repository-bootstrap:{schema}".encode(), digest_size=8).digest()
    return (
        int.from_bytes(digest[:4], byteorder="big", signed=True),
        int.from_bytes(digest[4:], byteorder="big", signed=True),
    )


def _acquire_repository_bootstrap_lock(database: PostgresRepositoryDatabase, connection: object) -> None:
    lock_key_one, lock_key_two = _bootstrap_lock_keys(database.schema)
    connection.execute("SELECT pg_advisory_xact_lock(%s, %s)", (lock_key_one, lock_key_two))


def initialize_postgres_repository_storage(
    settings: AppSettings,
    *,
    include_seed_data: bool = True,
) -> PostgresRepositoryDatabase:
    database = PostgresRepositoryDatabase.from_settings(settings)
    with database.connection() as connection:
        # App and worker can start together under Docker Compose, so bootstrap must be serialized.
        _acquire_repository_bootstrap_lock(database, connection)
        apply_repository_migrations(database, connection=connection)
        if include_seed_data:
            seed_repository_data(database, connection=connection)
    return database


def build_postgres_repository_registry(settings: AppSettings) -> RepositoryRegistry:
    database = initialize_postgres_repository_storage(settings)
    return RepositoryRegistry(
        sales=PostgresSalesRepository(database),
        inventory=PostgresInventoryRepository(database),
        marketing=PostgresMarketingRepository(database),
        support=PostgresSupportRepository(database),
    )
