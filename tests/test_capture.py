import json
from collections.abc import Mapping
from typing import Any

import pytest
from conftest import Telemetry
from opentelemetry import trace
from opentelemetry.sdk import resources
from opentelemetry.sdk.metrics import export as metrics
from opentelemetry.sdk.util.instrumentation import InstrumentationScope

import pytest_otel_capture as capture


def test_spans_and_trace_context(telemetry: Telemetry) -> None:
    tracer = telemetry.tracing.get_tracer("example")
    with tracer.start_as_current_span("parent", attributes={"request": "42"}) as parent:
        with tracer.start_as_current_span("child") as child:
            child.add_event("finished")
    spans = telemetry.capture.get_finished_spans()
    collected = capture.get_span(spans, "child", scope="example")
    assert collected is not None
    assert collected.name == "child"
    assert collected.scope.name == "example"
    assert collected.resource.attributes["service.name"] == "test"
    assert collected.events[0].name == "finished"
    assert collected.span_id == child.get_span_context().span_id
    capture.assert_trace_id(collected, parent)
    capture.assert_trace_id(collected, parent.get_span_context().trace_id)
    capture.assert_trace_header(
        f"00-{collected.trace_id:032x}-{collected.span_id:016x}-01", parent
    )
    assert json.loads(str(collected))["name"] == "child"
    assert capture.get_span(spans, "missing") is None
    assert len(capture.find_spans(spans, "parent", attributes={"request": "42"})) == 1
    assert capture.find_spans(spans, "parent", attributes={"request": "other"}) == []
    assert capture.find_spans(spans, "child", scope="other") == []
    assert telemetry.capture.get_finished_spans() == []
    with pytest.raises(AssertionError):
        capture.assert_trace_id(collected, collected.trace_id + 1)
    with pytest.raises(AssertionError):
        capture.assert_trace_header("00-wrong", parent)
    with pytest.raises(ValueError, match="more than one"):
        capture.get_span([collected, collected], "child")


def test_logs_are_drained_and_filtered(telemetry: Telemetry) -> None:
    logger = telemetry.logging.get_logger("example")
    logger.emit(body="hello", attributes={"request": "42"})
    logs = telemetry.capture.get_finished_logs()
    collected = capture.get_log(logs, attributes={"request": "42"}, scope="example")
    assert collected is not None
    assert collected.body == "hello"
    assert collected.resource.attributes["service.name"] == "test"
    assert json.loads(str(collected))["body"] == "hello"
    assert capture.get_log(logs, attributes={"request": "other"}) is None
    assert capture.find_logs(logs, scope="other") == []
    assert telemetry.capture.get_finished_logs() == []
    with pytest.raises(ValueError, match="more than one"):
        capture.get_log([collected, collected])


def test_metric_snapshot_and_data_points(telemetry: Telemetry) -> None:
    counter = telemetry.metrics.get_meter("example").create_counter("requests")
    counter.add(2, {"route": "/"})
    data = telemetry.capture.get_metrics_data()
    metric = capture.get_metric(
        data, "requests", attributes={"route": "/"}, scope="example"
    )
    assert metric is not None
    assert metric.resource.attributes["service.name"] == "test"
    assert metric.scope.name == "example"
    assert json.loads(str(metric))["name"] == "requests"
    point = capture.latest_metric_data(data, "requests", metrics.NumberDataPoint)
    assert point.value == 2
    assert capture.get_metric(data, "missing") is None
    assert capture.find_metrics(data, "requests", attributes={"route": "/other"}) == []
    assert capture.find_metrics(data, "requests", scope="other") == []
    assert (
        capture.latest_metric_data(
            telemetry.capture.get_metrics_data(), "requests", metrics.NumberDataPoint
        ).value
        == 2
    )
    with pytest.raises(ValueError, match="more than one"):
        capture.get_metric([metric, metric], "requests")
    with pytest.raises(AssertionError):
        capture.latest_metric_data(data, "requests", metrics.HistogramDataPoint)
    with pytest.raises(AssertionError):
        capture.latest_metric_data(data, "missing", metrics.NumberDataPoint)


def test_local_providers_do_not_replace_global_providers(telemetry: Telemetry) -> None:
    global_provider = trace.get_tracer_provider()
    with telemetry.tracing.get_tracer("example").start_as_current_span("local"):
        pass
    assert trace.get_tracer_provider() is global_provider
    assert capture.get_span(telemetry.capture.get_finished_spans(), "local") is not None


@pytest.mark.parametrize("iteration", range(2))
def test_each_capture_is_empty(iteration: int, telemetry: Telemetry) -> None:
    assert telemetry.capture.get_finished_spans() == []
    assert telemetry.capture.get_finished_logs() == []
    with telemetry.tracing.get_tracer("example").start_as_current_span(str(iteration)):
        pass
    assert len(telemetry.capture.get_finished_spans()) == 1


def test_log_wrapper_accepts_structural_records() -> None:
    class Record:
        attributes: Mapping[str, Any] | None = {"key": "value"}
        body: Any = "hello"

    class Log:
        instrumentation_scope = InstrumentationScope("example")
        resource = resources.Resource.create()
        log_record = Record()

        def to_json(self) -> str:
            return "{}"

    collected = capture.CollectedLog(Log())
    assert collected.attributes == {"key": "value"}
    assert collected.body == "hello"
    assert str(collected) == "{}"
