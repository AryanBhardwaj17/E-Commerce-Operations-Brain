"""Pydantic schemas for the E-Commerce Operations Brain."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ── Enumerations ──────────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(UTC)

class IntentType(StrEnum):
    DIAGNOSE = "diagnose"
    ACTION = "action"
    MEMORY = "memory"
    REPORT = "report"
    HYBRID = "hybrid"
    OUT_OF_SCOPE = "out_of_scope"


class DomainType(StrEnum):
    SALES = "sales"
    INVENTORY = "inventory"
    MARKETING = "marketing"
    SUPPORT = "support"


class ApprovalStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionStatus(StrEnum):
    EXECUTED = "executed"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReportKind(StrEnum):
    ANALYSIS = "analysis"
    INVENTORY_LIST = "inventory_list"
    ACTION_CONFIRMATION = "action_confirmation"
    HISTORY_RESPONSE = "history_response"
    OUT_OF_SCOPE = "out_of_scope"


class ResponseFormat(StrEnum):
    """Response format for query answers (Phase 1)"""
    DIAGNOSIS = "diagnosis"
    SUMMARY = "summary"
    COMPARISON = "comparison"
    LIST = "list"


class GapType(StrEnum):
    """Categorization of data gaps (Phase 1)"""
    MISSING_DATA = "missing_data"
    UNSUPPORTED_METRIC = "unsupported_metric"
    TIMEFRAME_UNAVAILABLE = "timeframe_unavailable"
    DOMAIN_NOT_ANALYZED = "domain_not_analyzed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AnswerQuality(StrEnum):
    """Answer completeness indicator (Phase 1)"""
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


# ── Input ─────────────────────────────────────────────────────────────────────

class BusinessQuery(BaseModel):
    query: str = Field(description="Natural language business question")
    user_id: str = Field(default="ops_team", description="Scopes user-level query history")
    run_id: str | None = Field(default=None, description="Resume a prior run if set")
    timestamp: datetime = Field(default_factory=_utc_now)


# ── Routing ───────────────────────────────────────────────────────────────────

class RoutingDecision(BaseModel):
    intent: IntentType
    active_domains: list[DomainType]
    reasoning: str = Field(description="Why these domains were selected")
    requires_memory_lookup: bool = True
    requires_action: bool = False


# ── Domain Analysis ───────────────────────────────────────────────────────────

class DataPoint(BaseModel):
    metric: str
    value: Any
    unit: str = ""
    period: str = ""  # Legacy - kept for backward compatibility
    change_pct: float | None = None  # Legacy - single comparison
    # Phase 1 additions - optional for backward compatibility
    time_range: dict[str, Any] | None = None  # Structured time metadata
    baselines: dict[str, Any] | None = None  # Multi-period comparisons


class InventoryItem(BaseModel):
    product_id: str
    product_name: str
    quantity_available: int
    reorder_point: int
    status: str
    days_until_stockout: float | None = None
    unit_price: float | None = None
    currency: str | None = None
    effective_price: float | None = None
    active_discount: dict[str, Any] | None = None


class DomainFinding(BaseModel):
    domain: DomainType
    summary: str
    data_points: list[DataPoint] = Field(default_factory=list)
    anomalies: list[str] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    tools_called: list[str] = Field(default_factory=list)


# ── Synthesis ─────────────────────────────────────────────────────────────────

class AnalysisResult(BaseModel):
    findings: list[DomainFinding]
    primary_root_cause: str
    contributing_factors: list[str]
    confidence_score: float = Field(ge=0.0, le=1.0)
    is_new_pattern: bool = Field(
        default=False,
        description="True if this incident has no matching KEDB entry",
    )
    recommended_actions: list[str] = Field(default_factory=list)
    cross_domain_correlations: list[str] = Field(
        default_factory=list,
        description="Observed correlations across domains (e.g. stockout + campaign active)",
    )
    # Phase 1 additions - optional for backward compatibility
    addressed_metrics: dict[str, Any] = Field(default_factory=dict)  # metric_name -> value/analysis
    covered_timeframes: list[dict[str, Any]] = Field(default_factory=list)  # periods analyzed
    response_format: ResponseFormat | None = None  # How answer is structured
    comparison_data: dict[str, Any] | None = None  # When comparison_intent present


# ── Completeness & Data Gaps (Phase 1) ───────────────────────────────────────

class CompletenessCheck(BaseModel):
    """Structured completeness validation (Phase 1)"""
    requested_metrics: list[str] = Field(default_factory=list)
    addressed_metrics: list[str] = Field(default_factory=list)
    missing_metrics: list[str] = Field(default_factory=list)
    requested_timeframes: list[dict[str, Any]] = Field(default_factory=list)
    covered_timeframes: list[dict[str, Any]] = Field(default_factory=list)


class DataGap(BaseModel):
    """Structured data gap representation (Phase 1)"""
    gap_type: GapType
    description: str
    affected_domains: list[DomainType] = Field(default_factory=list)
    severity: str = Field(default="moderate")  # "critical" | "moderate" | "minor"


# ── Reflection ────────────────────────────────────────────────────────────────

class ReflectionResult(BaseModel):
    missing_domains: list[DomainType] = Field(default_factory=list)
    confidence_ok: bool = True
    action_needed: bool = False
    gaps: list[str] = Field(default_factory=list)  # Legacy - kept for backward compatibility
    notes: str = ""
    # Phase 1 additions - optional for backward compatibility
    structured_gaps: list[DataGap] = Field(default_factory=list)
    completeness_check: CompletenessCheck | None = None
    answer_quality: AnswerQuality | None = None


# ── Actions / HITL ────────────────────────────────────────────────────────────

class ActionProposal(BaseModel):
    action_name: str
    tool_name: str
    tool_args: dict[str, Any]
    rationale: str
    estimated_impact: str
    risk_level: RiskLevel


class ActionRecord(BaseModel):
    action_name: str
    tool_name: str
    status: ActionStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    idempotency_key: str | None = None
    execution_id: str | None = None
    executed_at: datetime | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None


class ApprovalRequest(BaseModel):
    run_id: str
    proposals: list[ActionProposal]
    context_summary: str
    requested_at: datetime = Field(default_factory=_utc_now)


class ApprovalResponse(BaseModel):
    run_id: str
    approved: bool
    approved_action_names: list[str] = Field(default_factory=list)
    rejected_action_names: list[str] = Field(default_factory=list)
    reviewer_notes: str = ""
    reviewed_at: datetime = Field(default_factory=_utc_now)


# ── Memory ────────────────────────────────────────────────────────────────────

class MemoryContext(BaseModel):
    kedb_matches: list[dict[str, Any]] = Field(default_factory=list)
    kadb_matches: list[dict[str, Any]] = Field(default_factory=list)


# ── Final Report ──────────────────────────────────────────────────────────────

class FinalReport(BaseModel):
    run_id: str
    query: str
    report_kind: ReportKind = ReportKind.ANALYSIS
    intent: IntentType | None = None
    analysis: AnalysisResult | None = None
    inventory_items: list[InventoryItem] = Field(default_factory=list)
    actions_taken: list[ActionRecord] = Field(default_factory=list)
    actions_pending_approval: list[ActionProposal] = Field(default_factory=list)
    memory_context_used: bool = False
    executive_summary: str
    recommendations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utc_now)
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.5)
    data_gaps: list[str] = Field(default_factory=list)  # Legacy - kept for backward compatibility
    # Phase 1 additions - optional for backward compatibility
    response_format: ResponseFormat | None = None
    answer_quality: AnswerQuality | None = None
    structured_data_gaps: list[DataGap] = Field(default_factory=list)
    completeness_summary: str | None = None
