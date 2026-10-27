from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.projects import router as projects_router
from app.api.v1.tasks import router as tasks_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(tasks_router)
api_v1_router.include_router(notifications_router)
