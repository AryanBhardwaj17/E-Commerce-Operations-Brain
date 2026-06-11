"""DeepEval evaluation tests for agent response quality."""
from __future__ import annotations

import pytest
from deepeval.metrics import (
    AnswerCorrectnessMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase

# Minimum acceptable thresholds
CORRECTNESS_THRESHOLD = 0.7
FAITHFULNESS_THRESHOLD = 0.7
RELEVANCY_THRESHOLD = 0.7


@pytest.mark.eval
def test_sales_drop_diagnosis_correctness():
    """The system should correctly identify stockout as primary cause."""
    test_case = LLMTestCase(
        input="Why did sales drop on 2026-05-31?",
        actual_output=(
            "Revenue dropped 35% on 2026-05-31 primarily due to stockouts of "
            "SKU-001, SKU-003, and SKU-007, which together account for ~30% of "
            "total revenue. Additionally, two key marketing campaigns (CMP-002 "
            "paid search, CMP-003 social retargeting) were paused, reducing "
            "paid traffic. Customer complaints spiked 2.8x baseline, largely "
            "driven by out-of-stock complaints."
        ),
        expected_output=(
            "The primary root cause is stockout of high-demand SKUs (SKU-001, "
            "SKU-003, SKU-007) correlated with paused marketing campaigns."
        ),
        retrieval_context=[
            "KEDB: SALES-DROP-STOCKOUT — Stockout of high-demand SKUs due to "
            "inventory replenishment lag",
            "KEDB: SALES-DROP-CAMPAIGN-PAUSE — Key acquisition campaigns paused",
        ],
    )

    metric = AnswerCorrectnessMetric(threshold=CORRECTNESS_THRESHOLD)
    metric.measure(test_case)
    assert metric.score >= CORRECTNESS_THRESHOLD, (
        f"Correctness {metric.score:.2f} < threshold {CORRECTNESS_THRESHOLD}. "
        f"Reason: {metric.reason}"
    )


@pytest.mark.eval
def test_response_faithfulness_to_data():
    """Agent responses should be grounded in retrieved data, not hallucinated."""
    test_case = LLMTestCase(
        input="What products are out of stock?",
        actual_output=(
            "Three products are currently out of stock: SKU-001 (Wireless "
            "Headphones), SKU-003 (USB-C Hub), and SKU-007 (Desk Mat XL). "
            "Estimated lost revenue from these stockouts is approximately "
            "$17,700 per day."
        ),
        retrieval_context=[
            "Inventory data 2026-05-31: SKU-001 quantity=0 (stockout), "
            "SKU-003 quantity=0 (stockout), SKU-007 quantity=0 (stockout). "
            "Estimated lost revenue: $17,700.",
        ],
    )

    metric = FaithfulnessMetric(threshold=FAITHFULNESS_THRESHOLD)
    metric.measure(test_case)
    assert metric.score >= FAITHFULNESS_THRESHOLD, (
        f"Faithfulness {metric.score:.2f} < threshold {FAITHFULNESS_THRESHOLD}. "
        f"Reason: {metric.reason}"
    )


@pytest.mark.eval
def test_contextual_relevancy():
    """Retrieved context should be relevant to the query."""
    test_case = LLMTestCase(
        input="What marketing issues contributed to the sales drop?",
        actual_output=(
            "Two campaigns were paused on 2026-05-31: CMP-002 (Google Search "
            "Ads) and CMP-003 (Instagram Retargeting). These are typically "
            "responsible for 40% of daily paid traffic. ROAS dropped to near "
            "zero for these channels on the affected date."
        ),
        retrieval_context=[
            "Marketing data 2026-05-31: CMP-002 status=paused, "
            "CMP-003 status=paused. Channel: paid_search and social. "
            "Historical ROAS when active: 3.2.",
        ],
    )

    metric = ContextualRelevancyMetric(threshold=RELEVANCY_THRESHOLD)
    metric.measure(test_case)
    assert metric.score >= RELEVANCY_THRESHOLD, (
        f"Relevancy {metric.score:.2f} < threshold {RELEVANCY_THRESHOLD}. "
        f"Reason: {metric.reason}"
    )
