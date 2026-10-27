import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.config import settings
from app.core.cache import get_redis_client
from app.core.metrics import get_metrics_response

router = APIRouter(tags=["Operational"])


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(response: Response, db: Session = Depends(get_db)):
    """Deep health check endpoint inspecting database and Redis connectivity with latency measurements."""
    components = {}
    is_healthy = True

    # 1. Database Check
    db_start = time.time()
    try:
        db.execute(text("SELECT 1"))
        db_latency = round((time.time() - db_start) * 1000, 2)
        components["database"] = {
            "status": "connected",
            "latency_ms": db_latency
        }
    except Exception as e:
        is_healthy = False
        components["database"] = {
            "status": "error",
            "error": str(e)
        }

    # 2. Redis Check
    redis_start = time.time()
    try:
        r = get_redis_client()
        if r and r.ping():
            redis_latency = round((time.time() - redis_start) * 1000, 2)
            components["redis"] = {
                "status": "connected",
                "latency_ms": redis_latency
            }
        else:
            components["redis"] = {
                "status": "degraded",
                "detail": "Redis ping returned falsy or client not configured"
            }
    except Exception as e:
        components["redis"] = {
            "status": "degraded",
            "error": str(e)
        }

    overall_status = "healthy" if is_healthy else "unhealthy"
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall_status,
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components
    }


@router.get("/metrics")
def metrics():
    """Prometheus-compatible operational metrics endpoint."""
    return get_metrics_response()
