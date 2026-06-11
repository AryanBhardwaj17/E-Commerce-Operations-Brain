"""Unit tests for repository backend selection and bootstrap wiring."""
from __future__ import annotations

import pytest

from application.repositories import get_repository_registry, reset_repository_registry
from bootstrap.repositories import initialize_repository_registry
from core.settings import reset_settings_cache
from infrastructure.repositories import resolve_repository_backend


@pytest.fixture(autouse=True)
def reset_repository_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REPOSITORY_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_repository_registry()
    reset_settings_cache()
    yield
    reset_repository_registry()
    reset_settings_cache()


def test_resolve_repository_backend_defaults_to_postgres() -> None:
    assert resolve_repository_backend() == "postgres"


def test_initialize_repository_registry_requires_database_url_by_default() -> None:
    with pytest.raises(RuntimeError, match="requires DATABASE_URL"):
        initialize_repository_registry()


def test_get_repository_registry_requires_database_url_by_default() -> None:
    with pytest.raises(RuntimeError, match="requires DATABASE_URL"):
        get_repository_registry()


def test_initialize_repository_registry_uses_mock_backend_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOSITORY_BACKEND", "mock")
    reset_settings_cache()

    registry = initialize_repository_registry()

    assert registry.sales.__class__.__name__ == "MockSalesRepository"
    assert registry.inventory.__class__.__name__ == "MockInventoryRepository"
    assert registry.marketing.__class__.__name__ == "MockMarketingRepository"
    assert registry.support.__class__.__name__ == "MockSupportRepository"


def test_get_repository_registry_lazy_initialises_mock_backend_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REPOSITORY_BACKEND", "mock")
    reset_settings_cache()

    registry = get_repository_registry()

    assert registry.inventory.__class__.__name__ == "MockInventoryRepository"
