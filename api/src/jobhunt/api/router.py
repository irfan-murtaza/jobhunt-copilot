from __future__ import annotations

from fastapi import APIRouter

from jobhunt.api.routes import auth, health, jobs, matches, profile

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(jobs.router)
api_router.include_router(matches.router)
api_router.include_router(matches.preferences_router)
