import logging

import pytest
from conftest import Telemetry


def test_stdlib_logging_requires_an_explicit_bridge(telemetry: Telemetry) -> None:
    instrumentation = pytest.importorskip("opentelemetry.instrumentation.logging")
    handler_module = pytest.importorskip(
        "opentelemetry.instrumentation.logging.handler"
    )
    logger = logging.Logger("application", level=logging.INFO)
    logger.propagate = False
    null_handler = logging.NullHandler()
    logger.addHandler(null_handler)
    logger.info("not bridged")
    assert telemetry.capture.get_finished_logs() == []

    instrumentor = instrumentation.LoggingInstrumentor()
    original_factory = logging.getLogRecordFactory()
    handler = handler_module.LoggingHandler(logger_provider=telemetry.logging)
    try:
        instrumentor.instrument(
            tracer_provider=telemetry.tracing,
            inject_trace_context=True,
            enable_log_auto_instrumentation=False,
        )
        logger.addHandler(handler)
        with telemetry.tracing.get_tracer("example").start_as_current_span(
            "work"
        ) as span:
            logger.info("bridged", extra={"request": "42"})
        logs = telemetry.capture.get_finished_logs()
        assert len(logs) == 1
        assert logs[0].body == "bridged"
        assert logs[0].attributes["request"] == "42"
        assert logs[0].trace_id == span.get_span_context().trace_id
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.removeHandler(null_handler)
        instrumentor.uninstrument()
    assert logging.getLogRecordFactory() is original_factory
