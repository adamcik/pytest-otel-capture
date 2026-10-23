import subprocess
import sys


def test_legacy_context_allows_provider_replacement_after_exception() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
from opentelemetry import _logs, metrics, trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
import pytest_otel_capture as capture

first_trace, first_meter = TracerProvider(), MeterProvider()
first_logger = LoggerProvider()
trace.set_tracer_provider(first_trace)
metrics.set_meter_provider(first_meter)
_logs.set_logger_provider(first_logger)
first_exporter = capture.InMemorySpanExporter()
first_trace.add_span_processor(SimpleSpanProcessor(first_exporter))
cached_tracer = trace.get_tracer("cached")
collected = capture.OTelMocker(
    capture.InMemoryLogRecordExporter(),
    capture.InMemorySpanExporter(),
    capture.InMemoryMetricReader(),
)
try:
    with collected as active:
        assert active is collected
        raise RuntimeError("test")
except RuntimeError:
    pass
else:
    raise AssertionError("context manager suppressed an exception")
assert trace.get_tracer_provider() is first_trace
assert metrics.get_meter_provider() is first_meter
assert _logs.get_logger_provider() is first_logger
second_trace, second_meter = TracerProvider(), MeterProvider()
second_logger = LoggerProvider()
trace.set_tracer_provider(second_trace)
metrics.set_meter_provider(second_meter)
_logs.set_logger_provider(second_logger)
assert trace.get_tracer_provider() is second_trace
assert metrics.get_meter_provider() is second_meter
# Logging's independent guard is deliberately outside this helper's contract.
assert _logs.get_logger_provider() is first_logger
with cached_tracer.start_as_current_span("still-first"):
    pass
assert first_exporter.get_finished_spans()[0].name == "still-first"
for provider in [first_trace, first_meter, first_logger,
                 second_trace, second_meter, second_logger]:
    provider.shutdown()
collected.span_processor.shutdown()
collected.log_processor.shutdown()
collected.metric_reader.shutdown()
""",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
