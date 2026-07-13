"""FastAPI application entrypoint.

Responsibilities
----------------
* Create the FastAPI app instance with metadata + version.
* Configure CORS using origins from settings (``*`` allowed in dev).
* Mount every API router (ingestion is fully implemented in Phase 1; the rest
  are stubs that will be fleshed out in later phases).
* Expose a ``GET /health`` endpoint returning a structured status payload that
  also reports which backend services (Neo4j, ChromaDB) are reachable.

Run locally::

    cd backend
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import (
    auth,
    compliance,
    ingestion,
    maintenance,
    pid_vision,
    query,
    voice,
)
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("industrial-knowledge-brain")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle hook.

    We intentionally do NOT hard-fail if external services are unreachable at
    startup — ingestion degrades gracefully per subsystem. We just log what's
    available so the operator has a clear picture.
    """
    settings = get_settings()
    logger.info("Starting %s v%s (env=%s)", settings.app_name, __version__, settings.app_env)
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Unified industrial-knowledge intelligence platform for Indian "
            "asset-intensive industries. Ingests heterogeneous documents, builds "
            "a knowledge graph, and powers RAG retrieval, P&ID vision, and "
            "maintenance/compliance agents."
        ),
        lifespan=lifespan,
    )

    # CORS — permissive in dev, restricted by settings in production.
    origins = settings.cors_origins if not settings.is_dev else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers -------------------------------------------------------------
    app.include_router(ingestion.router)
    app.include_router(query.router)
    app.include_router(pid_vision.router)
    app.include_router(voice.router)
    app.include_router(maintenance.router)
    app.include_router(compliance.router)
    app.include_router(auth.router)

    @app.get("/health", tags=["meta"], summary="Liveness + service connectivity probe")
    async def health() -> dict[str, object]:
        """Return app health plus reachable status of each backend service.

        Each service is probed non-fatally: a missing Neo4j/Postgres just
        reports ``False`` rather than raising, so ``/health`` always returns 200.
        """
        from app.core.knowledge_graph import KnowledgeGraph
        from app.core.vector_store import VectorStore

        # ChromaDB is local; count() returns -1 if it failed.
        chroma_ok = False
        chroma_count = -1
        try:
            vs = VectorStore()
            chroma_count = vs.count()
            chroma_ok = chroma_count >= 0
        except Exception:  # noqa: BLE001
            pass

        neo4j_ok = False
        try:
            neo4j_ok = KnowledgeGraph().verify_connectivity()
        except Exception:  # noqa: BLE001
            pass

        return {
            "status": "healthy",
            "version": __version__,
            "env": settings.app_env,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {
                "chromadb": {"reachable": chroma_ok, "chunks": chroma_count},
                "neo4j": {"reachable": neo4j_ok},
            },
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_dev,
    )
