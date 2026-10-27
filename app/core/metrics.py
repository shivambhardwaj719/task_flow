import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY
)

# Prometheus Counters and Histograms
REQUEST_COUNT = Counter(
    "taskflow_http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"]
)

REQUEST_DURATION = Histogram(
    "taskflow_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

CACHE_OPERATIONS = Counter(
    "taskflow_cache_operations_total",
    "Total cache operations (hits, misses, invalidations)",
    ["operation", "result"]
)

NOTIFICATIONS_GENERATED = Counter(
    "taskflow_notifications_generated_total",
    "Total notification records generated",
    ["type"]
)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """ASGI Middleware to collect request counts and duration metrics for Prometheus."""

    async def dispatch(self, request: Request, call_next):
        # Exclude metrics and health endpoints from latency metrics to avoid skewing
        path = request.url.path
        if path in ("/metrics", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"):
            return await call_next(request)

        start_time = time.time()
        try:
            response: Response = await call_next(request)
            duration = time.time() - start_time
            status_code = str(response.status_code)

            # Normalize route path if possible
            matched_endpoint = path
            for route in request.app.routes:
                match, _ = route.matches(request.scope)
                if match.name == "FULL":
                    matched_endpoint = getattr(route, "path", path)
                    break

            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=matched_endpoint,
                status_code=status_code
            ).inc()

            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=matched_endpoint
            ).observe(duration)

            return response
        except Exception:
            duration = time.time() - start_time
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=path,
                status_code="500"
            ).inc()
            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=path
            ).observe(duration)
            raise


def get_metrics_response() -> Response:
    """Return latest Prometheus metrics text representation."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )
