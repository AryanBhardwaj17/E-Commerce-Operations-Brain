"""OpenTelemetry span context manager for per-node tracing."""
from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


def _get_tracer() -> Any:
    try:
        from opentelemetry import trace  # noqa: PLC0415
        return trace.get_tracer("ops_brain")
    except ImportError:
        return None


@contextmanager
def span(name: str, attributes: dict[str, Any] | None = None) -> Generator[Any, None, None]:
    """
    Context manager that creates an OTel span if OTel is configured.

    Falls back to a no-op context manager if OTel is not available.

    Usage:
        async with span("synthesis_node", {"run_id": run_id}):
            result = await synthesis_agent.run(state)
    """
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return

    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        try:
            yield s
        except Exception as exc:
            s.record_exception(exc)
            s.set_status(
                __import__("opentelemetry.trace", fromlist=["StatusCode"]).StatusCode.ERROR,
                str(exc),
            )
            raise


def configure_otel() -> None:
    """Configure OTel SDK from environment variables."""
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,  # noqa: PLC0415
        )
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

        provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except ImportError:
        pass  # OTel optional
