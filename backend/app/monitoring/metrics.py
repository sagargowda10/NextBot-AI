"""Prometheus metrics: HTTP RED metrics + agent/plugin/outbox gauges collected at scrape time."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector

REGISTRY = CollectorRegistry()
HTTP_REQUESTS = Counter("nextbot_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=REGISTRY)
HTTP_LATENCY = Histogram(
    "nextbot_http_request_duration_seconds",
    "HTTP latency",
    ["method", "route"],
    registry=REGISTRY,
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


class PlatformCollector(Collector):
    def __init__(self, state: Any) -> None:
        self.state = state

    def collect(self) -> Iterator[Any]:
        st = self.state
        status = GaugeMetricFamily("nextbot_plugin_enabled", "1 if plugin is ENABLED", labels=["plugin"])
        calls = CounterMetricFamily("nextbot_plugin_executions", "Plugin executions", labels=["plugin", "outcome"])
        latency = GaugeMetricFamily("nextbot_plugin_avg_duration_ms", "Average plugin execution time", labels=["plugin"])
        for reg in st.plugins.list():
            pid = reg.plugin.plugin_id
            status.add_metric([pid], 1.0 if reg.status.value == "ENABLED" else 0.0)
            calls.add_metric([pid, "success"], reg.stats.successes)
            calls.add_metric([pid, "failure"], reg.stats.failures)
            latency.add_metric([pid], reg.stats.avg_duration_ms)
        runs = CounterMetricFamily("nextbot_agent_executions", "Agent executions", labels=["agent", "outcome"])
        agent_ms = GaugeMetricFamily("nextbot_agent_avg_duration_ms", "Average agent duration", labels=["agent"])
        for agent in st.agents.all():
            s = st.metrics.stats(agent.name)
            runs.add_metric([agent.name, "success"], s["successes"])
            runs.add_metric([agent.name, "failure"], s["failures"])
            agent_ms.add_metric([agent.name], s["avg_duration_ms"])
        yield from (status, calls, latency, runs, agent_ms)
        bus_stats = getattr(st.bus, "stats", None)
        if bus_stats:
            ev = CounterMetricFamily("nextbot_events", "Event bus deliveries", labels=["outcome"])
            for k, v in bus_stats.items():
                ev.add_metric([k], v)
            yield ev


_collector: PlatformCollector | None = None


def install(app: Any, state: Any) -> None:
    global _collector
    from starlette.requests import Request
    from starlette.responses import Response

    if _collector is None:
        _collector = PlatformCollector(state)
        REGISTRY.register(_collector)
    else:  # app re-created (tests): point the collector at the new state
        _collector.state = state

    @app.middleware("http")
    async def _metrics_mw(request: Request, call_next: Any) -> Any:
        start = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
