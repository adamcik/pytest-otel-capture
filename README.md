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

- `get_finished_spans()` and `get_finished_logs()` drain their exporters. Each drain
  atomically removes its returned batch. Concurrent emissions fall in that batch or
  remain for a later drain; a drain does not wait for active spans, batch processors,
  threads, or async tasks. Do not independently clear or shut down the exporters while
  capturing. Atomic drains use SDK-private storage and locks, covered by the
  supported-version tests; custom exporter storage is unsupported.
- `get_metrics_data()` collects a metric snapshot; it does not clear instruments.
- `find_spans`, `find_logs`, and `find_metrics` return all matches. Attribute matching
  is a subset match; `scope` matches the instrumentation scope name.
- `get_span`, `get_log`, and `get_metric` return `None` for no match and raise
  `ValueError` for ambiguous matches.
- `latest_metric_data` returns the selected metric's last data point and checks its
  type. Attribute filtering selects the metric, not an individual data point. It is
  deprecated, with its behavior preserved until a future breaking release. Use
  `get_metric_point` to select the actual point by attributes (`None` for no match,
  `ValueError` for ambiguity), or `find_metric_points` for all matching points across
  metrics. Point sequence order does not imply chronological order.
- `assert_trace_id` and `assert_trace_header` check trace identity. The header helper
  checks only the version/trace-ID prefix, not full W3C header validity. Neither helper
  proves propagation or parentage. For relationships, inspect `parent_span_id`, `links`,
  and log `trace_id`/`span_id`. Events include SDK exception attributes.
  `readable_span`, `log_data`, and metric `metric` retain access to underlying SDK data;
  `log_data` is untyped to also accept structural records. SDK log IDs are zero when
  uncorrelated; structural records without correlation fields return `None`.

## Global state and lifecycle

Prefer designing your tests so OpenTelemetry's global state is not a problem, for
example by injecting local providers. That is not always practical. For those cases,
`reset_otel_once()` remains a private, test-only escape hatch that **may** enable
sequential tests to replace global trace/metric providers. `OTelMocker`'s legacy context
manager calls it on exit; direct object use does not change globals.

This helper only re-arms trace/metric setters. Existing providers remain installed until
replaced; logging's separate guard is not reset. It does not restore providers, rebind
cached tracers/meters/loggers, remove handlers or instrumentors, or finish work. It
deliberately does less than [upstream's internal test resets][upstream-resets], which
also clear provider references and replace proxies. Neither is a supported runtime reset
API, and upstream discourages using its test utilities externally.

Your fixture must finish and join telemetry-producing tasks/threads, force-flush any
application-owned batch processors before final assertions, remove its logging handlers,
uninstrument its instrumentors, and shut down the providers it owns. Do not shut down
providers owned by another fixture or the application. Drain before shutdown when
asserting captured records. Metrics have their own collection timing, below.

An active span can end after a drain and appear in a later drain. A tracer still bound
to an old local provider sends to that provider, not the next test's capture; shutting
down that provider early may lose the late emission. Local providers isolate capture
destinations, not unfinished work or ambient current-span context. Finish work and exit
span contexts before teardown. Global overrides require sequential tests with no
surviving producers; xdist separates workers, not tests within a worker. Use fresh
processes when stronger global-state isolation is required.

[upstream-resets]: https://github.com/open-telemetry/opentelemetry-python/blob/v1.45.1/tests/opentelemetry-test-utils/src/opentelemetry/test/globals_test.py

## Compatibility

CI tests installed wheels on Python 3.12, 3.13, and 3.14 with these exact pairs:

| OTel API/SDK | Logging instrumentation |
| ------------ | ----------------------- |
| 1.43.0       | 0.64b0                  |
| 1.44.0       | 0.65b0                  |

Runtime dependencies allow the 1.43 and 1.44 minor series. The logging instrumentation
package is used only in tests; the locked development environment uses the first pair.
Each matrix job explicitly installs and verifies its SDK versions rather than allowing
the resolver to substitute another SDK. Other SDK minors, instrumentation combinations,
free-threaded Python builds, and platforms other than Linux are not covered by this
matrix. Private exporter storage and reset internals require compatibility testing
before broadening support. Framework-specific fixtures stay in the application.

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
