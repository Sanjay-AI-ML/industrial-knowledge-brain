"""POST /api/maintenance/rca — Maintenance Intelligence & RCA Agent.

GET /api/maintenance/risk-score/{equipment_tag} — Predictive maintenance scoring.
"""

from __future__ import annotations

import logging
from typing import Any, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.rca_agent import rca_agent, maintenance_predictor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["maintenance"])


# --------------------------------------------------------------------------- #
# Request / Response schemas
# --------------------------------------------------------------------------- #
class RCAMatchCause(BaseModel):
    cause: str
    category: str
    confidence: str
    supporting_evidence: str


class RCAMatchIncident(BaseModel):
    incident_id: str
    description: str
    similarity: str


class RCARequest(BaseModel):
    """Input payload to trigger RCA agent analysis."""

    query: str = Field(..., description="Incident description or equipment tag to run RCA on.")


class RCAResponse(BaseModel):
    """Structured Root Cause Analysis report output."""

    equipment_tag: str = Field("", description="Extracted or resolved equipment tag.")
    probable_root_causes: List[RCAMatchCause] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    similar_past_incidents: List[RCAMatchIncident] = Field(default_factory=list)
    error: str | None = Field(None, description="System error details if generation failed.")


class RiskScoreResponse(BaseModel):
    """Predictive maintenance risk score response."""

    equipment_tag: str
    score: int = Field(..., description="Heuristic risk score from 0 to 100.")
    level: str = Field("low", description="Risk classification: low, medium, or high.")
    breakdown: List[str] = Field(default_factory=list, description="Reasoning logs behind the score.")


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.get("/maintenance/health")
async def maintenance_health() -> dict[str, object]:
    """Liveness probe for the maintenance subsystem."""
    return {"status": "ok", "agent": "LangGraph RCA v1", "predictor": "Neo4j Heuristics v1"}


@router.post(
    "/maintenance/rca",
    response_model=RCAResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Root Cause Analysis (RCA) report for an equipment issue",
)
async def get_rca_report(request: RCARequest) -> RCAResponse:
    """Trigger the LangGraph workflow to perform a 5-Whys root cause analysis.

    Queries Neo4j for full historical maintenance link records and ChromaDB
    for OEM troubleshooting guides before calling Gemini to compile the fishbone report.
    """
    try:
        # Run LangGraph state machine
        initial_state = {
            "query": request.query,
            "equipment_tag": "",
            "graph_context": {},
            "vector_context": "",
            "rca_report": {},
            "error": None
        }
        
        final_state = rca_agent.invoke(initial_state)
        report = final_state.get("rca_report", {})
        
        return RCAResponse(
            equipment_tag=final_state.get("equipment_tag", ""),
            probable_root_causes=report.get("probable_root_causes", []),
            recommended_actions=report.get("recommended_actions", []),
            similar_past_incidents=report.get("similar_past_incidents", []),
            error=final_state.get("error")
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in RCA router")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RCA generation failed: {exc}"
        )


@router.get(
    "/maintenance/risk-score/{equipment_tag}",
    response_model=RiskScoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve the predictive maintenance risk score for an asset",
)
async def get_asset_risk_score(equipment_tag: str) -> RiskScoreResponse:
    """Calculate a heuristic risk score based on the frequency of linked history in Neo4j."""
    try:
        res = maintenance_predictor.get_risk_score(equipment_tag)
        return RiskScoreResponse(
            equipment_tag=equipment_tag.upper(),
            score=res["score"],
            level=res["level"],
            breakdown=res["breakdown"]
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in risk predictor")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Predictive calculation failed: {exc}"
        )
