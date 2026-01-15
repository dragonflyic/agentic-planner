"""Main API router that aggregates all route modules."""

from fastapi import APIRouter

from workbench.api.routes import attempts, clarifications, jobs, signals

api_router = APIRouter()

api_router.include_router(signals.router, prefix="/signals", tags=["signals"])
api_router.include_router(attempts.router, prefix="/attempts", tags=["attempts"])
api_router.include_router(clarifications.router, prefix="/clarifications", tags=["clarifications"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
