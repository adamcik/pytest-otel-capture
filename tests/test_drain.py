from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, current_thread, main_thread

import pytest
from opentelemetry.sdk import _logs, trace

import pytest_otel_capture as capture


@pytest.mark.parametrize("signal", ["spans", "logs"])
def test_emission_during_drain_is_returned_now_or_next_time(signal: str) -> None:
    spans = capture.InMemorySpanExporter()
    logs = capture.InMemoryLogRecordExporter()
    collected = capture.OTelMocker(logs, spans, capture.InMemoryMetricReader())
    tracing = trace.TracerProvider()
    tracing.add_span_processor(collected.span_processor)
    logging = _logs.LoggerProvider()
    logging.add_log_record_processor(collected.log_processor)
    tracer = tracing.get_tracer("drain")
    logger = logging.get_logger("drain")

    def emit(value: str) -> None:
        if signal == "spans":
            with tracer.start_as_current_span(value):
                pass
        else:
            logger.emit(body=value)

    drain = (
        collected.get_finished_spans
        if signal == "spans"
        else collected.get_finished_logs
    )
    exporter = spans if signal == "spans" else logs
    snapshot_released = Event()
    emission_finished = Event()

    class InterleavingLock:
        """Instrument the SDK boundary, not the capture implementation.

        Release the first reader lock, let a producer finish, then let the
        reader continue. Separate SDK get/clear calls lose that producer's item.
        """

        def __init__(self) -> None:
            self.lock = Lock()
            self.interleaved = False

        def __enter__(self) -> None:
            self.lock.acquire()

        def __exit__(self, *args: object) -> None:
            self.lock.release()
            if current_thread() is main_thread() and not self.interleaved:
                self.interleaved = True
                snapshot_released.set()
                assert emission_finished.wait(5), "producer did not finish"

    try:
        emit("before")
        # SDK-private instrumentation is confined to this deterministic race test.
        exporter._lock = InterleavingLock()

        def produce() -> None:
            assert snapshot_released.wait(5), "drain did not release its lock"
            try:
                emit("during")
            finally:
                emission_finished.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            producer = executor.submit(produce)
            first = drain()
            producer.result(timeout=5)
        second = drain()
        values = [
            item.name if isinstance(item, capture.CollectedSpan) else item.body
            for item in [*first, *second]
        ]
        assert values == ["before", "during"]
        assert drain() == []
    finally:
        tracing.shutdown()
        logging.shutdown()
        collected.metric_reader.shutdown()
