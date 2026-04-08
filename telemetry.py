from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from contextlib import contextmanager
import time


def init_telemetry():
    if not os.getenv("OTEL_ENABLED"):
        return
    exporter = ConsoleSpanExporter()
    processor = BatchSpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


@contextmanager
def agent_span(agent_name: str, pr_number: int):
    tracer = get_tracer(agent_name)
    with tracer.start_as_current_span(f"{agent_name}.review") as span:
        span.set_attribute("agent.name", agent_name)
        span.set_attribute("pr.number", pr_number)
        t0 = time.perf_counter()
        try:
            yield span
        finally:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            span.set_attribute("latency_ms", elapsed_ms)
