"""POST /api/query — the Expert Knowledge Copilot (hybrid RAG chatbot).

Flow::

    QueryRequest {question, role, session_id?}
      -> RAGEngine.query()
         -> VectorStore.query()            # top-k ChromaDB retrieval
         -> KnowledgeGraph.get_related_entities()   # Neo4j enrichment
         -> Gemini structured-output generation
      -> QueryResponse {answer, sources, confidence, related_entities}

The engine never raises for LLM/graph failures — it degrades to a safe
fallback answer with ``error`` set, so this route only needs to guard against
truly unexpected exceptions (defensive 500).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.core.rag_engine import rag_engine
from app.models.schemas import QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


@router.get("/query/health")
async def query_health() -> dict[str, str]:
    """Liveness probe for the query subsystem."""
    return {"status": "ok"}


@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask the Expert Knowledge Copilot a question (hybrid vector + graph RAG)",
)
async def query_copilot(request: QueryRequest) -> QueryResponse:
    """Answer a natural-language question using the ingested document corpus.

    Retrieval is identical regardless of ``role``; only the answer's writing
    style adapts (technician = short/direct, engineer = technical detail,
    auditor = traceability-focused).

    Pass the ``session_id`` returned by a previous call to continue the same
    conversation with memory of prior turns; omit it to start a new session.
    """
    try:
        return rag_engine.query(
            question=request.question,
            role=request.role,
            session_id=request.session_id,
        )
    except Exception as exc:  # noqa: BLE001
        # RAGEngine.query() is designed to never raise — this is a defensive
        # backstop for genuinely unexpected failures (e.g. bad settings).
        logger.exception("Unexpected failure in /api/query")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed unexpectedly: {exc}",
        )
