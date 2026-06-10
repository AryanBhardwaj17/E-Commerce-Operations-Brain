"""Execution backends for submitted queries."""
from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any, Protocol, cast
from uuid import uuid4

import structlog

from core.orchestrator import get_runtime_graph
from core.run_state import append_run_event, mark_run_failed, store_run_result, store_run_status
from core.settings import get_settings
from infrastructure.runtime_store import get_runtime_store

logger = structlog.get_logger(__name__)

_MAX_GRAPH_EXECUTION_ATTEMPTS = 2


class QueryRunner(Protocol):
    """Execution backend contract for submitted runs."""

    def submit(self, run_id: str, state: dict[str, Any]) -> None:
        ...

    async def shutdown(self) -> None:
        ...


async def execute_submitted_run(run_id: str, state: dict[str, Any]) -> None:
    for attempt in range(1, _MAX_GRAPH_EXECUTION_ATTEMPTS + 1):
        append_run_event(run_id, "runner_started", attempt=attempt)
        try:
            graph = await get_runtime_graph()
            result = await graph.ainvoke(state, config={"configurable": {"thread_id": run_id}})
            store_run_result(run_id, result)
            return
        except Exception as exc:
            retryable = _is_retryable_execution_error(exc)
            if attempt < _MAX_GRAPH_EXECUTION_ATTEMPTS and retryable:
                append_run_event(
                    run_id,
                    "runner_retry_scheduled",
                    attempt=attempt + 1,
                    error=str(exc) or exc.__class__.__name__,
                )
                store_run_status(
                    run_id,
                    {
                        "status": "running",
                        "execution_attempt": attempt + 1,
                        "last_retry_error": str(exc) or exc.__class__.__name__,
                    },
                    event_type="retrying",
                )
                continue

            logger.exception("Query execution failed", run_id=run_id, error=repr(exc))
            mark_run_failed(run_id, str(exc) or exc.__class__.__name__)
            return


def _is_retryable_execution_error(exc: Exception) -> bool:
    if isinstance(exc, (ValueError, TypeError, KeyError, AssertionError)):
        return False
    message = (str(exc) or exc.__class__.__name__).lower()
    return any(
        token in message
        for token in (
            "temporary",
            "timeout",
            "timed out",
            "connection",
            "unavailable",
            "reset",
            "retry",
            "rate limit",
            "transport",
        )
    )


class InProcessQueryRunner:
    """Local execution backend using in-process background tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def submit(self, run_id: str, state: dict[str, Any]) -> None:
        append_run_event(run_id, "runner_submitted", backend="in_process")
        task = asyncio.create_task(self._run(run_id, state), name=f"query-runner:{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))

    async def _run(self, run_id: str, state: dict[str, Any]) -> None:
        await execute_submitted_run(run_id, state)

    async def shutdown(self) -> None:
        if not self._tasks:
            return

        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


class QueuedQueryRunner:
    """Execution backend that persists submitted runs for a separate worker process."""

    def submit(self, run_id: str, state: dict[str, Any]) -> None:
        get_runtime_store().enqueue_run(run_id, state)
        append_run_event(run_id, "runner_submitted", backend="queued")
        store_run_status(
            run_id,
            {"status": "queued", "execution_backend": "queued"},
            event_type="queued",
        )

    async def shutdown(self) -> None:
        return None


class QueuedRunWorker:
    """Background worker that claims queued runs from the runtime store and executes them."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        poll_interval_seconds: float | None = None,
        claim_timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.worker_id = worker_id or f"queue-worker-{uuid4().hex[:12]}"
        self.poll_interval_seconds = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else settings.worker_poll_interval_seconds
        )
        self.claim_timeout_seconds = (
            claim_timeout_seconds
            if claim_timeout_seconds is not None
            else settings.worker_claim_timeout_seconds
        )

    async def run_once(self) -> bool:
        payload = get_runtime_store().claim_next_run(
            self.worker_id,
            stale_after_seconds=self.claim_timeout_seconds,
        )
        if payload is None:
            return False

        run_id_value = payload.get("run_id")
        state_value = payload.get("state")
        if not isinstance(run_id_value, str) or not isinstance(state_value, dict):
            logger.warning("Discarding malformed queued run", payload=payload)
            if isinstance(run_id_value, str):
                get_runtime_store().complete_queued_run(run_id_value)
            return False

        run_id = run_id_value
        state = cast(dict[str, Any], state_value)

        append_run_event(run_id, "worker_claimed", worker_id=self.worker_id)
        store_run_status(
            run_id,
            {
                "status": "running",
                "execution_backend": "queued",
                "worker_id": self.worker_id,
            },
            event_type="worker_started",
        )

        try:
            await execute_submitted_run(run_id, state)
        finally:
            get_runtime_store().complete_queued_run(run_id)

        return True

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        while True:
            if stop_event is not None and stop_event.is_set():
                return

            processed = await self.run_once()
            if processed:
                continue

            await asyncio.sleep(self.poll_interval_seconds)


@lru_cache(maxsize=1)
def get_query_runner() -> QueryRunner:
    settings = get_settings()
    if settings.execution_backend == "queued":
        return QueuedQueryRunner()
    return InProcessQueryRunner()


def reset_query_runner_cache() -> None:
    get_query_runner.cache_clear()
