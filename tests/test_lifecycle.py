from concurrent.futures import ThreadPoolExecutor
from threading import Event

from opentelemetry.sdk import trace

import pytest_otel_capture as capture


def test_late_span_stays_with_its_original_local_capture() -> None:
    first = capture.OTelMocker(
        capture.InMemoryLogRecordExporter(),
        capture.InMemorySpanExporter(),
        capture.InMemoryMetricReader(),
    )
    second = capture.OTelMocker(
        capture.InMemoryLogRecordExporter(),
        capture.InMemorySpanExporter(),
        capture.InMemoryMetricReader(),
    )
    old_provider, new_provider = trace.TracerProvider(), trace.TracerProvider()
    old_provider.add_span_processor(first.span_processor)
    new_provider.add_span_processor(second.span_processor)
    started, finish = Event(), Event()

    def old_work() -> None:
        with old_provider.get_tracer("example").start_as_current_span("late"):
            started.set()
            assert finish.wait(5), "test did not release old work"

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            task = executor.submit(old_work)
            try:
                assert started.wait(5), "old work did not start"
                assert first.get_finished_spans() == []
                with new_provider.get_tracer("example").start_as_current_span("new"):
                    pass
            finally:
                finish.set()
            task.result(timeout=5)
        assert [span.name for span in first.get_finished_spans()] == ["late"]
        assert [span.name for span in second.get_finished_spans()] == ["new"]
        assert first.get_finished_spans() == second.get_finished_spans() == []
    finally:
        old_provider.shutdown()
        new_provider.shutdown()
        for collected in (first, second):
            collected.log_processor.shutdown()
            collected.metric_reader.shutdown()
