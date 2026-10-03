"""Read-only views and selectors over SDK-collected telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypeVar, assert_never, override

from opentelemetry import trace
from opentelemetry.sdk.metrics import export as metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.util.instrumentation import InstrumentationScope

DataPointType = TypeVar(
    "DataPointType",
    bound=metrics.NumberDataPoint
    | metrics.HistogramDataPoint
    | metrics.ExponentialHistogramDataPoint,
)


class CollectedSpan:
    def __init__(self, readable_span: ReadableSpan) -> None:
        context = readable_span.get_span_context()
        assert context is not None
        self._readable_span = readable_span
        self._context = context

    @property
    def name(self) -> str:
        return self._readable_span.name

    @property
    def attributes(self) -> Mapping[str, Any] | None:
        return self._readable_span.attributes

    @property
    def resource(self) -> Resource:
        return self._readable_span.resource

    @property
    def scope(self) -> InstrumentationScope | None:
        return self._readable_span.instrumentation_scope

    @property
    def status(self) -> trace.Status:
        return self._readable_span.status

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._readable_span.events)

    @property
    def span_id(self) -> int:
        return self._context.span_id

    @property
    def trace_id(self) -> int:
        return self._context.trace_id

    @override
    def __str__(self) -> str:
        return self._readable_span.to_json()


class CollectedLog:
    def __init__(self, log_data: _LogDataLike) -> None:
        self._log_data = log_data

    @property
    def scope(self) -> InstrumentationScope | None:
        return self._log_data.instrumentation_scope

    @property
    def resource(self) -> Resource:
        return self._log_data.resource

    @property
    def attributes(self) -> Mapping[str, Any] | None:
        return self._log_data.log_record.attributes

    @property
    def body(self) -> Any:
        return self._log_data.log_record.body

    @override
    def __str__(self) -> str:
        return self._log_data.to_json()


class CollectedMetric:
    def __init__(
        self, resource: Resource, scope: InstrumentationScope, metric: metrics.Metric
    ) -> None:
        self._resource = resource
        self._scope = scope
        self._metric = metric

    @property
    def resource(self) -> Resource:
        return self._resource

    @property
    def scope(self) -> InstrumentationScope:
        return self._scope

    @property
    def metric(self) -> metrics.Metric:
        return self._metric

    @property
    def name(self) -> str:
        return self._metric.name

    @property
    def data(
        self,
    ) -> metrics.Sum | metrics.Gauge | metrics.Histogram | metrics.ExponentialHistogram:
        return self._metric.data

    @override
    def __str__(self) -> str:
        return self._metric.to_json()


def find_spans(
    spans: list[CollectedSpan],
    name: str,
    attributes: Mapping[str, Any] | None = None,
    scope: str | None = None,
) -> list[CollectedSpan]:
    return [
        span
        for span in spans
        if span.name == name
        and _matches_attributes(span.attributes, attributes)
        and _matches_scope(span.scope, scope)
    ]


def get_span(
    spans: list[CollectedSpan],
    name: str,
    attributes: Mapping[str, Any] | None = None,
    scope: str | None = None,
) -> CollectedSpan | None:
    return _one_or_none(find_spans(spans, name, attributes, scope), "span")


def find_logs(
    logs: list[CollectedLog],
    attributes: Mapping[str, Any] | None = None,
    scope: str | None = None,
) -> list[CollectedLog]:
    return [
        log
        for log in logs
        if _matches_attributes(log.attributes, attributes)
        and _matches_scope(log.scope, scope)
    ]


def get_log(
    logs: list[CollectedLog],
    attributes: Mapping[str, Any] | None = None,
    scope: str | None = None,
) -> CollectedLog | None:
    return _one_or_none(find_logs(logs, attributes, scope), "log")


def find_metrics(
    metrics_data: list[CollectedMetric],
    metric_name: str,
    attributes: Mapping[str, Any] | None = None,
    scope: str | None = None,
) -> list[CollectedMetric]:
    return [
        item
        for item in metrics_data
        if item.name == metric_name
        and _matches_scope(item.scope, scope)
        and (
            attributes is None
            or any(
                _matches_attributes(point.attributes, attributes)
                for point in item.data.data_points
            )
        )
    ]


def get_metric(
    metrics_data: list[CollectedMetric],
    metric_name: str,
    attributes: Mapping[str, Any] | None = None,
    scope: str | None = None,
) -> CollectedMetric | None:
    return _one_or_none(
        find_metrics(metrics_data, metric_name, attributes, scope), "metric"
    )


def assert_trace_id(
    collected_span: CollectedSpan, expected_trace_id: int | trace.Span
) -> None:
    assert _extract_trace_id(expected_trace_id) == collected_span.trace_id


def assert_trace_header(header: str, expected_trace: int | trace.Span) -> None:
    assert header.startswith(f"00-{_extract_trace_id(expected_trace):032x}-")


def latest_metric_data[
    DataPointType: metrics.NumberDataPoint
    | metrics.HistogramDataPoint
    | metrics.ExponentialHistogramDataPoint
](
    metrics_data: list[CollectedMetric],
    metric_name: str,
    data_point_type: type[DataPointType],
    attributes: Mapping[str, Any] | None = None,
    scope: str | None = None,
) -> DataPointType:
    """Return the last point of the selected metric, checking its concrete type.

    Attributes select a metric containing a matching point; they do not reorder
    or filter that metric's data points.
    """
    metric = get_metric(metrics_data, metric_name, attributes, scope)
    assert metric is not None
    assert metric.data.data_points
    point = metric.data.data_points[-1]
    assert isinstance(point, data_point_type)
    return point


class _LogRecordLike(Protocol):
    @property
    def attributes(self) -> Mapping[str, Any] | None: ...

    @property
    def body(self) -> Any: ...


class _LogDataLike(Protocol):
    @property
    def instrumentation_scope(self) -> InstrumentationScope | None: ...

    @property
    def resource(self) -> Resource: ...

    @property
    def log_record(self) -> _LogRecordLike: ...

    def to_json(self) -> str: ...


def _matches_attributes(
    actual: Mapping[str, Any] | None, expected: Mapping[str, Any] | None
) -> bool:
    if expected is None:
        return True
    return actual is not None and all(actual.get(k) == v for k, v in expected.items())


def _matches_scope(actual: InstrumentationScope | None, expected: str | None) -> bool:
    return expected is None or (actual is not None and actual.name == expected)


def _one_or_none[T](items: list[T], kind: str) -> T | None:
    if len(items) > 1:
        raise ValueError(f"Found more than one matching {kind}")
    return items[0] if items else None


def _extract_trace_id(expected: trace.Span | int) -> int:
    match expected:
        case int():
            return expected
        case trace.Span():
            return expected.get_span_context().trace_id
        case _:
            assert_never(expected)
