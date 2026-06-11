"""Unit tests for campaign pause/resume and support ticket creation actions."""
from __future__ import annotations

import pytest

from infrastructure.repositories.mock.factory import build_mock_repository_registry
from application.repositories import configure_repository_registry, reset_repository_registry


@pytest.fixture(autouse=True)
def setup_mock_repositories():
    """Ensure each test uses fresh mock repositories."""
    reset_repository_registry()
    registry = build_mock_repository_registry()
    configure_repository_registry(registry)
    yield
    reset_repository_registry()


class TestCampaignActions:
    """Test campaign pause and resume functionality."""

    def test_pause_campaign_success(self, setup_mock_repositories):
        """Test pausing an active campaign."""
        from application.repositories import get_marketing_repository

        marketing_repo = get_marketing_repository()

        # Pause a campaign
        result = marketing_repo.pause_campaign(
            campaign_id="CMP-001",
            reason="Testing pause functionality",
        )

        assert result["status"] == "success"
        assert result["campaign_id"] == "CMP-001"
        assert result["action"] == "pause_campaign"
        assert "action_id" in result
        assert result["reason"] == "Testing pause functionality"

    def test_pause_already_paused_campaign(self, setup_mock_repositories):
        """Test pausing a campaign that's already paused."""
        from application.repositories import get_marketing_repository

        marketing_repo = get_marketing_repository()

        # Pause once
        marketing_repo.pause_campaign(campaign_id="CMP-001", reason="First pause")

        # Try to pause again
        result = marketing_repo.pause_campaign(campaign_id="CMP-001", reason="Second pause")

        assert result["status"] == "error"
        assert "already paused" in result["message"].lower()

    def test_resume_campaign_success(self, setup_mock_repositories):
        """Test resuming a paused campaign."""
        from application.repositories import get_marketing_repository

        marketing_repo = get_marketing_repository()

        # Pause first
        marketing_repo.pause_campaign(campaign_id="CMP-002", reason="Test pause")

        # Then resume
        result = marketing_repo.resume_campaign(campaign_id="CMP-002")

        assert result["status"] == "success"
        assert result["campaign_id"] == "CMP-002"
        assert result["action"] == "resume_campaign"
        assert "action_id" in result

    def test_resume_non_paused_campaign(self, setup_mock_repositories):
        """Test resuming a campaign that's not paused."""
        from application.repositories import get_marketing_repository

        marketing_repo = get_marketing_repository()

        # Try to resume without pausing first
        result = marketing_repo.resume_campaign(campaign_id="CMP-003")

        assert result["status"] == "error"
        assert "not paused" in result["message"].lower()

    def test_pause_nonexistent_campaign(self, setup_mock_repositories):
        """Test pausing a campaign that doesn't exist."""
        from application.repositories import get_marketing_repository

        marketing_repo = get_marketing_repository()

        result = marketing_repo.pause_campaign(
            campaign_id="CMP-NONEXISTENT",
            reason="Testing",
        )

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_get_campaign_status(self, setup_mock_repositories):
        """Test getting campaign status."""
        from application.repositories import get_marketing_repository

        marketing_repo = get_marketing_repository()

        # Get status for active campaign
        result = marketing_repo.get_campaign_status(campaign_id="CMP-001")

        assert "campaign_id" in result
        assert "status" in result
        assert result["status"] == "active"

        # Pause and check status
        marketing_repo.pause_campaign(campaign_id="CMP-001", reason="Test")
        result = marketing_repo.get_campaign_status(campaign_id="CMP-001")

        assert result["status"] == "paused"


class TestSupportTicketActions:
    """Test support ticket creation functionality."""

    def test_create_support_ticket_success(self, setup_mock_repositories):
        """Test creating a new support ticket."""
        from application.repositories import get_support_repository

        support_repo = get_support_repository()

        result = support_repo.create_support_ticket(
            title="Test Issue",
            description="This is a test issue description",
            priority="high",
            category="technical",
            assigned_to="support_team",
        )

        assert result["status"] == "success"
        assert result["action"] == "create_support_ticket"
        assert "ticket" in result
        ticket = result["ticket"]
        assert ticket["title"] == "Test Issue"
        assert ticket["description"] == "This is a test issue description"
        assert ticket["priority"] == "high"
        assert ticket["category"] == "technical"
        assert ticket["assigned_to"] == "support_team"
        assert ticket["status"] == "open"
        assert "ticket_id" in ticket
        assert ticket["ticket_id"].startswith("TICKET-")

    def test_create_support_ticket_with_defaults(self, setup_mock_repositories):
        """Test creating a support ticket with default values."""
        from application.repositories import get_support_repository

        support_repo = get_support_repository()

        result = support_repo.create_support_ticket(
            title="Minimal Ticket",
            description="Only required fields",
        )

        assert result["status"] == "success"
        ticket = result["ticket"]
        assert ticket["priority"] == "medium"  # default
        assert ticket["category"] == "general"  # default
        assert ticket["assigned_to"] == "unassigned"  # default

    def test_get_ticket_status(self, setup_mock_repositories):
        """Test getting support ticket status."""
        from application.repositories import get_support_repository

        support_repo = get_support_repository()

        # Create a ticket
        create_result = support_repo.create_support_ticket(
            title="Test Ticket",
            description="Test description",
        )
        ticket_id = create_result["ticket"]["ticket_id"]

        # Get status
        status_result = support_repo.get_ticket_status(ticket_id=ticket_id)

        assert status_result["status"] == "success"
        assert "ticket" in status_result
        ticket = status_result["ticket"]
        assert ticket["ticket_id"] == ticket_id
        assert ticket["title"] == "Test Ticket"
        assert ticket["status"] == "open"

    def test_get_nonexistent_ticket_status(self, setup_mock_repositories):
        """Test getting status for a ticket that doesn't exist."""
        from application.repositories import get_support_repository

        support_repo = get_support_repository()

        result = support_repo.get_ticket_status(ticket_id="TICKET-NONEXISTENT")

        assert result["status"] == "error"
        assert "not found" in result["message"].lower()


class TestActionTools:
    """Test that action tools properly call repository methods."""

    def test_pause_campaign_tool(self, setup_mock_repositories):
        """Test pause_campaign action tool."""
        from tools.action_tools import pause_campaign

        result = pause_campaign(campaign_id="CMP-001", reason="Tool test")

        assert result["status"] == "success"
        assert result["action"] == "pause_campaign"

    def test_resume_campaign_tool(self, setup_mock_repositories):
        """Test resume_campaign action tool."""
        from tools.action_tools import pause_campaign, resume_campaign

        # Pause first
        pause_campaign(campaign_id="CMP-002", reason="Setup")

        # Then resume
        result = resume_campaign(campaign_id="CMP-002")

        assert result["status"] == "success"
        assert result["action"] == "resume_campaign"

    def test_create_support_ticket_tool(self, setup_mock_repositories):
        """Test create_support_ticket action tool."""
        from tools.action_tools import create_support_ticket

        result = create_support_ticket(
            title="Tool Test Ticket",
            description="Testing the tool wrapper",
            priority="low",
        )

        assert result["status"] == "success"
        assert result["action"] == "create_support_ticket"
        assert result["ticket"]["title"] == "Tool Test Ticket"


class TestActionExecutorNormalization:
    """Test action executor normalizes campaign and support tool arguments."""

    def test_pause_campaign_normalization(self, setup_mock_repositories):
        """Test normalizing pause_campaign arguments."""
        from unittest.mock import Mock
        from agents.action_executor import ActionExecutorAgent
        from bootstrap.tools import initialize_tool_registry

        # Register all tools
        initialize_tool_registry()

        # Create executor with mock LLM client
        mock_llm_client = Mock()
        executor = ActionExecutorAgent(mock_llm_client)

        # Test with various input formats
        normalized = executor._normalize_tool_args(
            "pause_campaign",
            {"campaign_id": "CMP-001", "reason": "Test reason"},
        )

        assert normalized["campaign_id"] == "CMP-001"
        assert normalized["reason"] == "Test reason"

        # Test with alternate field names
        normalized = executor._normalize_tool_args(
            "pause_campaign",
            {"id": "CMP-002", "notes": "Different field names"},
        )

        assert normalized["campaign_id"] == "CMP-002"
        assert normalized["reason"] == "Different field names"

    def test_create_support_ticket_normalization(self, setup_mock_repositories):
        """Test normalizing create_support_ticket arguments."""
        from unittest.mock import Mock
        from agents.action_executor import ActionExecutorAgent
        from bootstrap.tools import initialize_tool_registry

        # Register all tools
        initialize_tool_registry()

        # Create executor with mock LLM client
        mock_llm_client = Mock()
        executor = ActionExecutorAgent(mock_llm_client)

        # Test with various input formats
        normalized = executor._normalize_tool_args(
            "create_support_ticket",
            {
                "title": "Test Ticket",
                "description": "Test description",
                "priority": "high",
                "category": "bug",
            },
        )

        assert normalized["title"] == "Test Ticket"
        assert normalized["description"] == "Test description"
        assert normalized["priority"] == "high"
        assert normalized["category"] == "bug"

        # Test with alternate field names
        normalized = executor._normalize_tool_args(
            "create_support_ticket",
            {
                "subject": "Alternate Title",
                "details": "Alternate description",
                "issue_category": "technical",
            },
        )

        assert normalized["title"] == "Alternate Title"
        assert normalized["description"] == "Alternate description"
        assert normalized["category"] == "technical"
