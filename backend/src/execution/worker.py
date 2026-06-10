"""Queued execution worker entrypoint."""
from __future__ import annotations

import asyncio
import signal

import structlog

from bootstrap.startup import initialize_application, shutdown_application
from core.settings import get_settings
from execution.query_runner import QueuedRunWorker

logger = structlog.get_logger(__name__)


async def _run_worker() -> None:
    settings = get_settings()
    initialize_application(settings)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(handled_signal, stop_event.set)
        except NotImplementedError:
            continue

    worker = QueuedRunWorker()
    logger.info(
        "Queued worker started",
        worker_id=worker.worker_id,
        poll_interval_seconds=worker.poll_interval_seconds,
    )

    try:
        await worker.run_forever(stop_event=stop_event)
    finally:
        logger.info("Queued worker shutting down", worker_id=worker.worker_id)
        await shutdown_application()


def run() -> None:
    try:
        asyncio.run(_run_worker())
    except KeyboardInterrupt:
        logger.info("Queued worker interrupted")


if __name__ == "__main__":
    run()
