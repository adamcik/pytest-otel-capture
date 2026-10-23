# Behavioral telemetry tests

These examples test what reaches an in-memory exporter or reader. They do not test OTLP
serialization, collector transforms, remote delivery, or backend storage. Use an
integration test with the real export path for those contracts. The Python examples
below run together in the project's test suite.

## Application-owned local fixture

Put a fixture like this in your application's `conftest.py`. Nothing is auto-installed
by this library. Pass these providers to your application or its instrumentors instead
of installing global providers. Your application must expose a suitable injection seam.

```python
import pytest
from opentelemetry.sdk import _logs, metrics, trace
from opentelemetry.sdk.resources import Resource

import pytest_otel_capture as capture


@pytest.fixture
def telemetry():
    collected = capture.OTelMocker(
        capture.InMemoryLogRecordExporter(),
        capture.InMemorySpanExporter(),
        capture.InMemoryMetricReader(),
    )
    resource = Resource.create({"service.name": "behavior-test"})
    tracing = trace.TracerProvider(resource=resource)
    tracing.add_span_processor(collected.span_processor)
    logging = _logs.LoggerProvider(resource=resource)
    logging.add_log_record_processor(collected.log_processor)
    metering = metrics.MeterProvider(
        resource=resource, metric_readers=[collected.metric_reader]
    )
    try:
        yield collected, tracing, logging, metering
    finally:
        # Tests finish their work and assert capture before fixture teardown.
        tracing.shutdown()
        logging.shutdown()
        metering.shutdown()
```

If your application starts tasks or threads, join them before teardown. If it installs
handlers or instrumentors, remove those too. With batching, force-flush the providers
before final assertions and check the result; flush is not a substitute for waiting for
application work to finish. See the README's lifecycle guidance for global-state escape
hatches and their limitations.

## Capture SDK-emitted telemetry

The fixture's simple processors immediately forward ended, sampled spans and emitted
OTel logs. A provider's sampler can drop spans before they reach any processor.

```python
def test_sdk_emission(telemetry):
    collected, tracing, logging, metering = telemetry
    with tracing.get_tracer("application").start_as_current_span("checkout"):
        logging.get_logger("application").emit(body="checkout complete")
        metering.get_meter("application").create_counter("checkouts").add(1)

    span = capture.get_span(collected.get_finished_spans(), "checkout")
    log = capture.get_log(collected.get_finished_logs(), scope="application")
    point = capture.get_metric_point(collected.get_metrics_data(), "checkouts")
    assert span is not None and log is not None and point is not None
    assert log.trace_id == span.trace_id
    assert log.span_id == span.span_id
    assert point.value == 1
```

Attaching this capture processor **alongside** an application's filtering/redaction
processor captures a separate branch, potentially including data that the application's
export chain would discard. Python's span processors run independently; their
registration order does not turn them into a filtering chain. Collector-side tail
sampling is also outside this capture boundary.

## Capture what an application processor forwards

Instead, place the capture downstream of the processor under test. This small
application-owned processor forwards only explicitly approved spans. Replace it with
your own forwarding/redaction policy, preserving that downstream relationship.

```python
class ForwardApprovedSpans(trace.SpanProcessor):
    def __init__(self, downstream):
        self.downstream = downstream

    def on_end(self, span):
        if (span.attributes or {}).get("export.allowed") is True:
            self.downstream.on_end(span)

    def force_flush(self, timeout_millis=30000):
        return self.downstream.force_flush(timeout_millis)

    def shutdown(self):
        self.downstream.shutdown()


def test_application_forwarding_policy():
    collected = capture.OTelMocker(
        capture.InMemoryLogRecordExporter(),
        capture.InMemorySpanExporter(),
        capture.InMemoryMetricReader(),
    )
    provider = trace.TracerProvider()
    # Do not also attach collected.span_processor directly to the provider.
    provider.add_span_processor(ForwardApprovedSpans(collected.span_processor))
    try:
        tracer = provider.get_tracer("application")
        with tracer.start_as_current_span("discarded"):
            pass
        with tracer.start_as_current_span(
            "approved", attributes={"export.allowed": True}
        ):
            pass
        assert [span.name for span in collected.get_finished_spans()] == ["approved"]
    finally:
        provider.shutdown()
        collected.log_processor.shutdown()
        collected.metric_reader.shutdown()
```

This verifies the local forwarding policy—not serialization, a collector's policies, or
remote receipt. Logs need the equivalent placement in their log-processing chain;
metrics use readers and views, not span/log processors.

## Sensitive-marker assertions must not pass on empty capture

Replace this toy login operation with your application's entry point and inject the
providers above. Supply a synthetic credential, assert that the expected operation and
telemetry occurred, then inspect the fields covered by your privacy contract. The toy
operation deliberately emits only a fixed summary, never the credential.

```python
from opentelemetry.trace import Status, StatusCode


def reject_login(request, tracing, logging, metering):
    if not request.get("password"):
        raise ValueError("test requires a credential")
    with tracing.get_tracer("application").start_as_current_span(
        "login.rejected", attributes={"route": "/login"}
    ) as span:
        span.add_event("credential.rejected", {"reason": "invalid"})
        span.set_status(Status(StatusCode.ERROR, "invalid credential"))
        logging.get_logger("application").emit(
            body="login rejected", attributes={"route": "/login"}
        )
        metering.get_meter("application").create_counter("login.rejections").add(
            1, {"route": "/login"}
        )
    return False


def test_sensitive_marker_is_not_emitted(telemetry):
    collected, tracing, logging, metering = telemetry
    marker = "SENSITIVE_TEST_MARKER"
    assert reject_login({"password": marker}, tracing, logging, metering) is False
    spans = collected.get_finished_spans()
    logs = collected.get_finished_logs()
    metric_data = collected.get_metrics_data()
    assert len(spans) == len(logs) == 1
    assert spans[0].name == "login.rejected"
    assert logs[0].body == "login rejected"
    point = capture.get_metric_point(
        metric_data, "login.rejections", {"route": "/login"}
    )
    assert point is not None and point.value == 1
    assert spans[0].events

    for log in logs:
        assert marker not in str(log.body)
        assert marker not in str(log.attributes)
        assert marker not in str(log.resource.attributes)
    for span in spans:
        assert marker not in span.name
        assert marker not in str(span.attributes)
        assert marker not in str(span.status.description)
        assert marker not in str(span.resource.attributes)
        for event in span.events:
            assert marker not in event.name
            assert marker not in str(event.attributes)
    for metric in metric_data:
        assert marker not in str(metric.resource.attributes)
        for point in metric.data.data_points:
            assert marker not in str(point.attributes)
```

This checks one synthetic marker in named fields at this capture boundary. It is not a
general privacy audit, does not cover dropped/truncated telemetry, and does not prove a
remote sink is safe. Add assertions for links, scopes, or other fields if your
application can place sensitive values there. Do not infer safety from an empty capture.

## Standard-library and structlog logging

`logging.info(...)` and structlog calls do not automatically become OTel log records.
Deliberately configure an OTel logging bridge, or test your application's existing sink.
For the compatible logging-instrumentation versions in the README, an application
fixture can attach `opentelemetry.instrumentation.logging.handler.LoggingHandler` with
`logger_provider=your_local_logger_provider`, removing and closing it on teardown.
Structlog must route through that bridged standard-library logger, or have its own
explicit OTel integration. This package installs neither a bridge nor an instrumentor.
