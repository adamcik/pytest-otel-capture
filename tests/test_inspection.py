from conftest import Telemetry
from opentelemetry import trace

import pytest_otel_capture as capture


def test_span_relationships_and_sdk_escape_hatch(telemetry: Telemetry) -> None:
    tracer = telemetry.tracing.get_tracer("example")
    with tracer.start_as_current_span("parent") as parent:
        with tracer.start_as_current_span(
            "child", links=[trace.Link(parent.get_span_context(), {"reason": "retry"})]
        ) as child:
            child.record_exception(ValueError("synthetic-error"))
    spans = telemetry.capture.get_finished_spans()
    root = capture.get_span(spans, "parent")
    collected = capture.get_span(spans, "child")
    assert root is not None and collected is not None
    assert root.parent_span_id is None
    assert collected.parent_span_id == parent.get_span_context().span_id
    assert collected.links[0].context.span_id == parent.get_span_context().span_id
    assert collected.events[0].attributes["exception.message"] == "synthetic-error"
    assert collected.readable_span.get_span_context().span_id == collected.span_id


def test_logs_expose_span_correlation_and_sdk_record(telemetry: Telemetry) -> None:
    logger = telemetry.logging.get_logger("example")
    with telemetry.tracing.get_tracer("example").start_as_current_span("work") as span:
        logger.emit(body="correlated")
    logger.emit(body="uncorrelated")
    correlated, uncorrelated = telemetry.capture.get_finished_logs()
    context = span.get_span_context()
    assert correlated.trace_id == context.trace_id
    assert correlated.span_id == context.span_id
    assert correlated.log_data.log_record.body == "correlated"
    assert uncorrelated.trace_id == 0
    assert uncorrelated.span_id == 0


def test_trace_header_assertion_only_checks_version_00_trace_prefix() -> None:
    # Intentionally malformed: this helper is not a traceparent validator.
    capture.assert_trace_header(f"00-{42:032x}-not-a-span-id", 42)
