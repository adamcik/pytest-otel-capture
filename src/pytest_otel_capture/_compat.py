"""SDK-version-sensitive imports and legacy global-provider reset support."""

import opentelemetry.metrics._internal
import opentelemetry.trace
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.util._once import Once

__all__ = [
    "InMemoryLogRecordExporter",
    "InMemoryMetricReader",
    "InMemorySpanExporter",
    "SimpleLogRecordProcessor",
    "reset_otel_once",
]


def reset_otel_once() -> None:
    """Permit replacing global trace/metric providers; not a provider teardown.

    This compatibility helper uses SDK internals. Prefer local SDK providers in
    new tests. Callers own shutting down old providers and replacing them before
    creating instruments; concurrent use in one process is unsupported.
    """
    opentelemetry.trace._TRACER_PROVIDER_SET_ONCE = Once()  # pyright: ignore[reportPrivateUsage]
    opentelemetry.metrics._internal._METER_PROVIDER_SET_ONCE = Once()  # pyright: ignore[reportPrivateUsage]
