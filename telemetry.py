from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from contextlib import contextmanager
import time


# skipping telemetry entirely when not needed keeps local dev clean
# set OTEL_ENABLED to true in env file when you want to traces output in the console
def init_telemetry():
    if not os.getenv("OTEL_ENABLED"):
        return
    exporter = ConsoleSpanExporter()
    processor = BatchSpanProcessor(exporter)
    provider = TracerProvider()
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


# wrapper function, so that agents cannot call opentelemetry directly
def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


# wrap any agent's work in this function to get latency, token counts and finding counts recorded automatically as span attributes
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
