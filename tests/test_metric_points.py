import pytest
from conftest import Telemetry
from opentelemetry import metrics as api_metrics
from opentelemetry.sdk import metrics as sdk_metrics
from opentelemetry.sdk.metrics import export as metrics

import pytest_otel_capture as capture


def test_point_selector_filters_counter_attribute_sets(telemetry: Telemetry) -> None:
    counter = telemetry.metrics.get_meter("example").create_counter("requests")
    counter.add(2, {"route": "/first"})
    counter.add(7, {"route": "/second"})
    data = telemetry.capture.get_metrics_data()
    point = capture.get_metric_point(
        data, "requests", attributes={"route": "/first"}, scope="example"
    )
    assert isinstance(point, metrics.NumberDataPoint)
    assert point.value == 2
    assert point.attributes == {"route": "/first"}
    assert len(capture.find_metric_points(data, "requests")) == 2
    assert capture.get_metric_point(data, "missing") is None
    assert capture.get_metric_point(data, "requests", scope="other") is None
    assert (
        capture.get_metric_point(data, "requests", attributes={"route": "/absent"})
        is None
    )
    with pytest.raises(ValueError, match="more than one matching metric point"):
        capture.get_metric_point(data, "requests")


def test_point_selectors_cover_histograms_and_observable_collection(
    telemetry: Telemetry,
) -> None:
    meter = telemetry.metrics.get_meter("example")
    histogram = meter.create_histogram("duration")
    histogram.record(3, {"route": "/first"})
    histogram.record(5, {"route": "/second"})
    observations = []

    def observe(options: api_metrics.CallbackOptions) -> list[api_metrics.Observation]:
        observations.append(options)
        return [api_metrics.Observation(11, {"queue": "work"})]

    meter.create_observable_gauge("depth", callbacks=[observe])
    assert observations == []
    data = telemetry.capture.get_metrics_data()
    assert len(observations) == 1
    point = capture.get_metric_point(data, "duration", {"route": "/first"})
    assert isinstance(point, metrics.HistogramDataPoint)
    assert (point.count, point.sum) == (1, 3)
    assert len(capture.find_metric_points(data, "duration")) == 2
    depth = capture.get_metric_point(data, "depth", {"queue": "work"})
    assert isinstance(depth, metrics.NumberDataPoint)
    assert depth.value == 11
    telemetry.capture.get_metrics_data()
    assert len(observations) == 2


def test_point_ambiguity_across_scopes(telemetry: Telemetry) -> None:
    for scope in ("first", "second"):
        telemetry.metrics.get_meter(scope).create_counter("requests").add(1)
    data = telemetry.capture.get_metrics_data()
    with pytest.raises(ValueError, match="more than one"):
        capture.get_metric_point(data, "requests")
    assert capture.get_metric_point(data, "requests", scope="first") is not None


def test_legacy_last_point_is_deprecated_but_keeps_its_contract(
    telemetry: Telemetry,
) -> None:
    counter = telemetry.metrics.get_meter("example").create_counter("requests")
    counter.add(2, {"route": "/first"})
    counter.add(7, {"route": "/second"})
    with pytest.warns(DeprecationWarning, match="get_metric_point"):
        point = capture.latest_metric_data(
            telemetry.capture.get_metrics_data(),
            "requests",
            metrics.NumberDataPoint,
            attributes={"route": "/first"},
        )
    assert point.value == 7
    assert point.attributes == {"route": "/second"}


@pytest.mark.parametrize(
    ("temporality", "second_value"),
    [
        (metrics.AggregationTemporality.CUMULATIVE, 5),
        (metrics.AggregationTemporality.DELTA, 3),
    ],
)
def test_metric_reads_follow_reader_temporality(
    temporality: metrics.AggregationTemporality, second_value: int
) -> None:
    reader = capture.InMemoryMetricReader(
        preferred_temporality={sdk_metrics.Counter: temporality}
    )
    collected = capture.OTelMocker(
        capture.InMemoryLogRecordExporter(), capture.InMemorySpanExporter(), reader
    )
    provider = sdk_metrics.MeterProvider(metric_readers=[reader])
    try:
        counter = provider.get_meter("example").create_counter("requests")
        counter.add(2)
        first = capture.get_metric_point(collected.get_metrics_data(), "requests")
        assert isinstance(first, metrics.NumberDataPoint)
        assert first.value == 2
        counter.add(3)
        second = capture.get_metric_point(collected.get_metrics_data(), "requests")
        assert isinstance(second, metrics.NumberDataPoint)
        assert second.value == second_value
        assert first.value == 2
    finally:
        provider.shutdown()
        collected.span_processor.shutdown()
        collected.log_processor.shutdown()
