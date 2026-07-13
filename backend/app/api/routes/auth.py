"""Authentication route — STUB.

JWT-based auth (python-jose + passlib) is built in a later phase. The login,
token-issue and protected-dependency helpers will live here.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/auth/health")
async def auth_health() -> dict[str, str]:
    """Liveness probe for the auth subsystem."""
    return {"status": "stub", "todo": "later phase — JWT auth"}
