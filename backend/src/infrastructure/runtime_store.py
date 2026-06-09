"""Persistent runtime state storage for run status and HITL approvals."""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any

from core.settings import get_settings
from models.schemas import ApprovalRequest, ApprovalResponse


class LocalRuntimeStore:
    """File-backed runtime store used for local durability and simple deployments."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.runs_dir = self.root_dir / "runs"
        self.approvals_dir = self.root_dir / "approvals"
        self.responses_dir = self.root_dir / "responses"
        self.action_executions_dir = self.root_dir / "action-executions"
        self.events_dir = self.root_dir / "events"
        self.queue_dir = self.root_dir / "queue"
        self.inflight_queue_dir = self.root_dir / "queue-inflight"
        self.query_history_dir = self.root_dir / "query-history"
        self._lock = RLock()

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.approvals_dir.mkdir(parents=True, exist_ok=True)
        self.responses_dir.mkdir(parents=True, exist_ok=True)
        self.action_executions_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.inflight_queue_dir.mkdir(parents=True, exist_ok=True)
        self.query_history_dir.mkdir(parents=True, exist_ok=True)

    def save_run_status(self, run_id: str, payload: dict[str, Any]) -> None:
        self._write_json(self.runs_dir / f"{run_id}.json", payload)

    def get_run_status(self, run_id: str) -> dict[str, Any] | None:
        return self._read_json(self.runs_dir / f"{run_id}.json")

    def save_approval_request(self, request: ApprovalRequest) -> None:
        self._write_json(
            self.approvals_dir / f"{request.run_id}.json",
            request.model_dump(mode="json"),
        )

    def get_approval_request(self, run_id: str) -> ApprovalRequest | None:
        data = self._read_json(self.approvals_dir / f"{run_id}.json")
        if data is None:
            return None
        return ApprovalRequest.model_validate(data)

    def save_approval_response(self, response: ApprovalResponse) -> None:
        self._write_json(
            self.responses_dir / f"{response.run_id}.json",
            response.model_dump(mode="json"),
        )

    def get_approval_response(self, run_id: str) -> ApprovalResponse | None:
        data = self._read_json(self.responses_dir / f"{run_id}.json")
        if data is None:
            return None
        return ApprovalResponse.model_validate(data)

    def clear_approval(self, run_id: str) -> None:
        for path in (
            self.approvals_dir / f"{run_id}.json",
            self.responses_dir / f"{run_id}.json",
        ):
            path.unlink(missing_ok=True)

    def save_action_execution(self, run_id: str, idempotency_key: str, payload: dict[str, Any]) -> None:
        self._write_json(self._action_execution_path(run_id, idempotency_key), payload)

    def get_action_execution(self, run_id: str, idempotency_key: str) -> dict[str, Any] | None:
        data = self._read_json(self._action_execution_path(run_id, idempotency_key))
        if isinstance(data, dict):
            return data
        return None

    def append_run_event(self, run_id: str, event: dict[str, Any]) -> None:
        path = self.events_dir / f"{run_id}.json"
        with self._lock:
            events = self._read_json_unlocked(path)
            if not isinstance(events, list):
                events = []
            events.append(event)
            self._write_json_unlocked(path, events)

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        data = self._read_json(self.events_dir / f"{run_id}.json")
        if isinstance(data, list):
            return data
        return []

    def append_user_query(self, user_id: str, entry: dict[str, Any]) -> None:
        path = self.query_history_dir / f"{self._safe_key(user_id)}.json"
        with self._lock:
            history = self._read_json_unlocked(path)
            if not isinstance(history, list):
                history = []
            history.append(entry)
            self._write_json_unlocked(path, history)

    def list_user_queries(self, user_id: str) -> list[dict[str, Any]]:
        data = self._read_json(self.query_history_dir / f"{self._safe_key(user_id)}.json")
        if isinstance(data, list):
            return data
        return []

    def enqueue_run(self, run_id: str, state: dict[str, Any]) -> None:
        self._write_json(
            self.queue_dir / f"{run_id}.json",
            {
                "run_id": run_id,
                "state": state,
                "queued_at": self._timestamp(),
            },
        )

    def claim_next_run(
        self,
        worker_id: str,
        *,
        stale_after_seconds: float = 60.0,
    ) -> dict[str, Any] | None:
        with self._lock:
            self._requeue_stale_claims_unlocked(stale_after_seconds)

            for path in sorted(self.queue_dir.glob("*.json"), key=lambda candidate: candidate.name):
                claim_path = self.inflight_queue_dir / path.name
                try:
                    path.replace(claim_path)
                except FileNotFoundError:
                    continue

                payload = self._read_json_unlocked(claim_path)
                if not isinstance(payload, dict):
                    claim_path.unlink(missing_ok=True)
                    continue

                payload["claimed_by"] = worker_id
                payload["claimed_at"] = self._timestamp()
                self._write_json_unlocked(claim_path, payload)
                return payload

        return None

    def complete_queued_run(self, run_id: str) -> None:
        for path in (
            self.inflight_queue_dir / f"{run_id}.json",
            self.queue_dir / f"{run_id}.json",
        ):
            path.unlink(missing_ok=True)

    def list_queued_runs(self) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for directory in (self.queue_dir, self.inflight_queue_dir):
            for path in sorted(directory.glob("*.json"), key=lambda candidate: candidate.name):
                payload = self._read_json(path)
                if isinstance(payload, dict):
                    payloads.append(payload)
        return payloads

    def _write_json(self, path: Path, payload: Any) -> None:
        with self._lock:
            self._write_json_unlocked(path, payload)

    def _write_json_unlocked(self, path: Path, payload: Any) -> None:
        serialised = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)

        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            delete=False,
            dir=path.parent,
            prefix=path.stem,
            suffix=".tmp",
        ) as tmp:
            tmp.write(serialised)
            tmp_path = Path(tmp.name)

        tmp_path.replace(path)

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None

        with self._lock:
            return self._read_json_unlocked(path)

    def _read_json_unlocked(self, path: Path) -> Any:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _requeue_stale_claims_unlocked(self, stale_after_seconds: float) -> None:
        if stale_after_seconds <= 0:
            return

        now = time.time()
        for path in self.inflight_queue_dir.glob("*.json"):
            try:
                age_seconds = now - path.stat().st_mtime
            except FileNotFoundError:
                continue

            if age_seconds < stale_after_seconds:
                continue

            try:
                path.replace(self.queue_dir / path.name)
            except FileNotFoundError:
                continue

    @staticmethod
    def _timestamp() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _safe_key(value: str) -> str:
        safe_value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
        return safe_value or "default"

    def _action_execution_path(self, run_id: str, idempotency_key: str) -> Path:
        return self.action_executions_dir / (
            f"{self._safe_key(run_id)}__{self._safe_key(idempotency_key)}.json"
        )


@lru_cache(maxsize=1)
def get_runtime_store() -> LocalRuntimeStore:
    return LocalRuntimeStore(get_settings().resolved_runtime_store_dir())


def reset_runtime_store_cache() -> None:
    get_runtime_store.cache_clear()
