"""OpenTelemetry tracing (opt-in with OTEL_ENABLED=true). Exports OTLP to the configured collector."""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

log = get_logger("tracing")


def setup_tracing(app: Any, settings: Any, engine: Any | None = None) -> None:
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.warning("otel_packages_missing")
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "nextbot-backend"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    log.info("otel_enabled")
