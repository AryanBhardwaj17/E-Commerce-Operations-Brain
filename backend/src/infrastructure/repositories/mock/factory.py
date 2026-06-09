"""Factory for mock-backed repository adapters."""
from __future__ import annotations

from application.repositories import RepositoryRegistry
from infrastructure.repositories.mock.inventory import MockInventoryRepository
from infrastructure.repositories.mock.marketing import MockMarketingRepository
from infrastructure.repositories.mock.sales import MockSalesRepository
from infrastructure.repositories.mock.support import MockSupportRepository


def build_mock_repository_registry() -> RepositoryRegistry:
    return RepositoryRegistry(
        sales=MockSalesRepository(),
        inventory=MockInventoryRepository(),
        marketing=MockMarketingRepository(),
        support=MockSupportRepository(),
    )