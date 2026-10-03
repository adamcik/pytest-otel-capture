from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from opentelemetry.sdk import _logs, metrics, trace
from opentelemetry.sdk.resources import Resource

import pytest_otel_capture as capture


@dataclass
class Telemetry:
    capture: capture.OTelMocker
    tracing: trace.TracerProvider
    logging: _logs.LoggerProvider
    metrics: metrics.MeterProvider


@pytest.fixture
def telemetry() -> Iterator[Telemetry]:
    collected = capture.OTelMocker(
        capture.InMemoryLogRecordExporter(),
        capture.InMemorySpanExporter(),
        capture.InMemoryMetricReader(),
    )
    resource = Resource.create({"service.name": "test"})
    tracing = trace.TracerProvider(resource=resource)
    tracing.add_span_processor(collected.span_processor)
    logging = _logs.LoggerProvider(resource=resource)
    logging.add_log_record_processor(collected.log_processor)
    meter = metrics.MeterProvider(
        resource=resource, metric_readers=[collected.metric_reader]
    )
    try:
        yield Telemetry(
            capture=collected, tracing=tracing, logging=logging, metrics=meter
        )
    finally:
        tracing.shutdown()
        logging.shutdown()
        meter.shutdown()
