import subprocess
import sys


def test_legacy_context_allows_provider_replacement_after_exception() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace import TracerProvider
import pytest_otel_capture as capture

first_trace, first_meter = TracerProvider(), MeterProvider()
trace.set_tracer_provider(first_trace)
metrics.set_meter_provider(first_meter)
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
second_trace, second_meter = TracerProvider(), MeterProvider()
trace.set_tracer_provider(second_trace)
metrics.set_meter_provider(second_meter)
assert trace.get_tracer_provider() is second_trace
assert metrics.get_meter_provider() is second_meter
for provider in [first_trace, first_meter, second_trace, second_meter]:
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
