# pytest-otel-capture

Capture and inspect OpenTelemetry logs, spans, and metrics in Python tests. Requires
Python 3.12 or newer.

```sh
pip install pytest-otel-capture
```

This first release is a helper library, not an auto-loaded pytest plugin. Your fixture
owns SDK providers and instrumentation; no application framework, exporter backend, or
pytest runtime dependency is required.

```python
from opentelemetry.sdk import trace
import pytest_otel_capture as capture

collected = capture.OTelMocker(
    capture.InMemoryLogRecordExporter(),
    capture.InMemorySpanExporter(),
    capture.InMemoryMetricReader(),
)
provider = trace.TracerProvider()
provider.add_span_processor(collected.span_processor)
try:
    with provider.get_tracer("example").start_as_current_span("work"):
        pass
    span = capture.get_span(collected.get_finished_spans(), "work")
    assert span is not None
    assert span.scope.name == "example"
finally:
    provider.shutdown()
```

## Capture ownership and selectors

Inject `span_processor` into a `TracerProvider`, `log_processor` into a
`LoggerProvider`, and `metric_reader` into a `MeterProvider`. Shut down each provider in
your fixture's `finally` block. Local SDK providers avoid changing the process-global
providers and keep independent tests isolated.

- `get_finished_spans()` and `get_finished_logs()` drain their exporters.
- `get_metrics_data()` collects a metric snapshot; it does not clear instruments.
- `find_spans`, `find_logs`, and `find_metrics` return all matches. Attribute matching
  is a subset match; `scope` matches the instrumentation scope name.
- `get_span`, `get_log`, and `get_metric` return `None` for no match and raise
  `ValueError` for ambiguous matches.
- `latest_metric_data` returns the selected metric's last data point and checks its
  type. Attribute filtering selects the metric, not an individual data point.
- `assert_trace_id` and `assert_trace_header` check trace identity. The header helper
  checks only the version/trace-ID prefix, not full W3C header validity.

`OTelMocker` retains a legacy context manager that resets the private global
trace/metric provider-once guards on exit. It does **not** restore or shut down
providers. The exported `reset_otel_once()` has the same limits. Prefer direct object
use with local SDK providers; global-provider replacement is unsuitable for concurrent
tests in one process.

SDK support is deliberately limited to the tested 1.43 minor series because
provider-reset and logging support depend on SDK internals. Broaden the range only after
compatibility testing. Framework-specific pytest fixtures stay in the application that
owns their settings and instrumentation.

## Development

```sh
nix develop
pytest -q
basedpyright
nix fmt
nix flake check
nix build
```

See [RELEASING.md](RELEASING.md) for repository setup and PyPI trusted publishing.

## License

Licensed under the [Apache License 2.0](LICENSE).
