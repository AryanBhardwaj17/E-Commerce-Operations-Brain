"""Mock repository adapters backed by deterministic fixture modules."""
from infrastructure.repositories.mock.factory import build_mock_repository_registry
from infrastructure.repositories.mock.inventory import MockInventoryRepository
from infrastructure.repositories.mock.marketing import MockMarketingRepository
from infrastructure.repositories.mock.sales import MockSalesRepository
from infrastructure.repositories.mock.support import MockSupportRepository

__all__ = [
    "MockSalesRepository",
    "MockInventoryRepository",
    "MockMarketingRepository",
    "MockSupportRepository",
    "build_mock_repository_registry",
]