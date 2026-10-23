"""SDK-version-sensitive imports and legacy global-provider reset support."""

from typing import cast

import opentelemetry.metrics._internal
import opentelemetry.trace
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan
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

    Prefer tests that do not need to replace globals. When that is impractical,
    this private, test-only escape hatch may enable sequential replacement.
    It leaves current providers installed and excludes the logging guard.
    Callers own shutdown, instrumentor/handler removal, and finishing background
    work. Previously acquired tracers, meters, and loggers may remain bound to
    old providers; concurrent use in one process is unsupported.

    Compare upstream's broader test-only reset (provider, proxy, and guard):
    https://github.com/open-telemetry/opentelemetry-python/blob/v1.45.1/tests/opentelemetry-test-utils/src/opentelemetry/test/globals_test.py
    Their utilities disclaim external support; this helper intentionally only
    re-arms the trace/metric guards rather than clearing or restoring globals.
    """
    opentelemetry.trace._TRACER_PROVIDER_SET_ONCE = Once()  # pyright: ignore[reportPrivateUsage]
    opentelemetry.metrics._internal._METER_PROVIDER_SET_ONCE = Once()  # pyright: ignore[reportPrivateUsage]


def drain_spans(exporter: InMemorySpanExporter) -> tuple[ReadableSpan, ...]:
    # SDK getters and clear() lock independently. Use the export lock once so
    # an emission cannot be deleted without belonging to the returned batch.
    with exporter._lock:  # pyright: ignore[reportPrivateUsage]
        spans = tuple(exporter._finished_spans)  # pyright: ignore[reportPrivateUsage]
        exporter._finished_spans.clear()  # pyright: ignore[reportPrivateUsage]
    return spans


def drain_logs(exporter: InMemoryLogRecordExporter) -> tuple[ReadableLogRecord, ...]:
    with exporter._lock:  # pyright: ignore[reportPrivateUsage]
        records = cast(list[ReadableLogRecord], exporter._logs)  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
        logs = tuple(records)
        records.clear()
    return logs
