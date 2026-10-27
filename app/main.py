import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_v1_router
from app.api.v1.operational import router as operational_router
from app.config import settings
from app.core.metrics import PrometheusMetricsMiddleware
from app.database import Base, engine

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("taskflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist
    if settings.ENVIRONMENT != "testing":
        try:
            logger.info("Initializing database tables...")
            Base.metadata.create_all(bind=engine)
            logger.info(
                "%s v%s started up successfully in %s mode.",
                settings.PROJECT_NAME,
                settings.VERSION,
                settings.ENVIRONMENT,
            )
        except Exception as e:
            logger.warning("Startup table initialization skipped or failed: %s", str(e))
    yield
    logger.info("Shutting down %s...", settings.PROJECT_NAME)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Task Management API with Notifications, Caching, and Background Processing",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Prometheus Metrics Middleware
app.add_middleware(PrometheusMetricsMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Operational endpoints available at top level (/health, /metrics)
app.include_router(operational_router)

# Versioned API routes (/api/v1/...)
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "version": settings.VERSION,
    }
