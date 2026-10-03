"""Exporter ownership stays with the application or fixture that supplies them."""

from types import TracebackType
from typing import Self

from opentelemetry.sdk.metrics.export import MetricsData
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from ._compat import (
    InMemoryLogRecordExporter,
    InMemoryMetricReader,
    InMemorySpanExporter,
    SimpleLogRecordProcessor,
    reset_otel_once,
)
from ._helpers import CollectedLog, CollectedMetric, CollectedSpan


class OTelMocker:
    """Inspect telemetry collected by processors injected into SDK providers.

    Log/span reads drain the exporters; metric reads collect the reader's current
    snapshot. The context manager retains the legacy global-provider guard reset
    on exit, but does not shut down or restore providers. With local providers,
    use this object directly and let the enclosing fixture own their lifecycle.
    """

    def __init__(
        self,
        log_exporter: InMemoryLogRecordExporter,
        span_exporter: InMemorySpanExporter,
        metric_reader: InMemoryMetricReader,
    ) -> None:
        self._log_exporter = log_exporter
        self._span_exporter = span_exporter
        self.metric_reader = metric_reader
        self.span_processor = SimpleSpanProcessor(span_exporter)
        self.log_processor = SimpleLogRecordProcessor(log_exporter)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        reset_otel_once()

    def get_finished_logs(self) -> list[CollectedLog]:
        logs = [
            CollectedLog(record) for record in self._log_exporter.get_finished_logs()
        ]
        self._log_exporter.clear()
        return logs

    def get_finished_spans(self) -> list[CollectedSpan]:
        spans = [
            CollectedSpan(span) for span in self._span_exporter.get_finished_spans()
        ]
        self._span_exporter.clear()
        return spans

    def get_metrics_data(self) -> list[CollectedMetric]:
        metrics: list[CollectedMetric] = []
        data = self.metric_reader.get_metrics_data()
        if isinstance(data, MetricsData):
            for resource_metrics in data.resource_metrics:
                for scope_metrics in resource_metrics.scope_metrics:
                    metrics.extend(
                        CollectedMetric(
                            resource_metrics.resource, scope_metrics.scope, metric
                        )
                        for metric in scope_metrics.metrics
                    )
        return metrics
