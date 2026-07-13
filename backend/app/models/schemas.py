"""Shared Pydantic schemas used across the ingestion pipeline.

These dataclasses flow between the document parser, entity extractor,
knowledge-graph linker, vector store, and the API response layer. Keeping
them in one place avoids circular imports between core modules.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Document parsing
# --------------------------------------------------------------------------- #
class ParsedPage(BaseModel):
    """A single page extracted from an uploaded document."""

    page_num: int = Field(..., description="1-based page number")
    raw_text: str = Field("", description="Extracted text for the page")
    tables: list[list[list[Any]]] = Field(
        default_factory=list,
        description="Tables on the page as list-of-rows (each row is a list of cells)",
    )
    is_scanned: bool = Field(
        False, description="True if the page was (likely) a scanned image / OCR path was used"
    )


class ParsedDocument(BaseModel):
    """Full parsed output of a single uploaded file."""

    filename: str
    total_pages: int
    pages: list[ParsedPage]
    is_scanned_any: bool = Field(False, description="True if any page needed OCR")
    ocr_used: bool = Field(False, description="True if the OCR engine actually ran")

    def full_text(self) -> str:
        """Concatenate all page text, page-delimited."""
        return "\n\n".join(
            f"--- Page {p.page_num} ---\n{p.raw_text}" for p in self.pages
        )


# --------------------------------------------------------------------------- #
# Entity extraction
# --------------------------------------------------------------------------- #
class DocumentType(str, Enum):
    """Coarse document taxonomy used across the platform."""

    PID = "P&ID"
    WORK_ORDER = "work_order"
    PROCEDURE = "procedure"
    INSPECTION_REPORT = "inspection_report"
    COMPLIANCE_FILING = "compliance_filing"
    MAINTENANCE_LOG = "maintenance_log"
    MSDS = "msds"
    DATASHEET = "datasheet"
    OTHER = "other"


class Equipment(BaseModel):
    """A piece of equipment identified by tag (e.g. P-101A)."""

    tag: str = Field(..., description="Equipment tag, e.g. 'P-101A', 'V-203', 'E-305'")
    equipment_type: str | None = Field(
        None, description="Inferred type: pump, vessel, exchanger, compressor, valve, etc."
    )
    description: str | None = None


class ProcessParameter(BaseModel):
    """An operating parameter mentioned in the document."""

    name: str = Field(..., description="e.g. 'suction pressure', 'outlet temperature'")
    value: str | None = Field(None, description="e.g. '4.5 kg/cm2', '120 degC'")
    unit: str | None = None


class Person(BaseModel):
    """A person mentioned in the document."""

    name: str
    role: str | None = Field(None, description="e.g. 'maintenance engineer', 'inspector'")


class RegulatoryReference(BaseModel):
    """A reference to an Indian / international standard or regulation."""

    reference: str = Field(..., description="e.g. 'OISD-117', 'OISD-118', 'PESO', 'Factory Act 1948'")
    description: str | None = None


class ExtractedEntities(BaseModel):
    """Structured entity payload returned by the Claude entity extractor."""

    document_type: DocumentType = DocumentType.OTHER
    document_title: str | None = None
    summary: str = Field("", description="One or two sentence summary of the document")
    equipment: list[Equipment] = Field(default_factory=list)
    parameters: list[ProcessParameter] = Field(default_factory=list)
    persons: list[Person] = Field(default_factory=list)
    dates: list[str] = Field(
        default_factory=list, description="ISO or free-text dates found in the document"
    )
    regulatory_references: list[RegulatoryReference] = Field(default_factory=list)
    procedures: list[str] = Field(
        default_factory=list, description="Procedure / SOP names referenced"
    )
    incidents: list[str] = Field(
        default_factory=list, description="Incident IDs or descriptions referenced"
    )


# --------------------------------------------------------------------------- #
# Pipeline result summaries
# --------------------------------------------------------------------------- #
class GraphLinkResult(BaseModel):
    """Outcome of writing entities to the Neo4j knowledge graph."""

    linked: bool
    nodes_created: int = 0
    relationships_created: int = 0
    error: str | None = None


class VectorStoreResult(BaseModel):
    """Outcome of chunking + embedding a document into ChromaDB."""

    stored: bool
    chunks_embedded: int = 0
    error: str | None = None


class IngestionResponse(BaseModel):
    """Top-level structured JSON returned by POST /api/ingest.

    ``status`` is one of:
      - ``"ok"``       — every stage succeeded
      - ``"partial"``  — parsed + stored, but extraction and/or graph failed
      - ``"error"``    — fatal parse/upload error (raised as HTTPException instead)
    """

    status: str
    filename: str
    document_id: str
    pages_parsed: int
    is_scanned: bool
    ocr_used: bool
    extracted: ExtractedEntities
    graph: GraphLinkResult
    vector: VectorStoreResult
    extraction_error: str | None = Field(
        None,
        description="If entity extraction failed, the human-readable error "
        "(e.g. Claude API billing/auth error). Null when extraction succeeded.",
    )


# --------------------------------------------------------------------------- #
# RAG / Expert Knowledge Copilot (Phase 2)
# --------------------------------------------------------------------------- #
class UserRole(str, Enum):
    """Who is asking — shapes response style, not retrieval."""

    TECHNICIAN = "technician"
    ENGINEER = "engineer"
    AUDITOR = "auditor"


class ConfidenceLevel(str, Enum):
    """Coarse confidence bucket derived from retrieval relevance scores."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class QueryRequest(BaseModel):
    """POST /api/query request body."""

    question: str = Field(..., min_length=1, description="The user's natural-language question")
    role: UserRole = Field(
        UserRole.ENGINEER, description="Influences response style, not what is retrieved"
    )
    session_id: str | None = Field(
        None,
        description="Stable id for a conversation thread. Omit to start a new session "
        "(the server generates and returns one).",
    )


class SourceCitation(BaseModel):
    """One retrieved chunk cited in the answer."""

    doc_name: str = Field(..., description="Original filename the chunk came from")
    document_id: str
    page: int | None = Field(None, description="Page number if determinable, else null")
    snippet: str = Field(..., description="The retrieved chunk text (may be truncated)")
    relevance_score: float = Field(
        ..., description="1 - cosine distance; higher is more relevant (0..1 approx)"
    )


class RelatedEntity(BaseModel):
    """An entity pulled from the Neo4j graph that's related to the query context."""

    label: str = Field(..., description="Node label, e.g. 'Equipment', 'Person', 'Regulation'")
    value: str = Field(..., description="Primary identifying value, e.g. equipment tag or name")
    relationship: str | None = Field(
        None, description="How it connects to the retrieved documents, e.g. 'MENTIONED_IN'"
    )


class QueryResponse(BaseModel):
    """POST /api/query structured response."""

    session_id: str
    answer: str
    sources: list[SourceCitation] = Field(default_factory=list)
    confidence: ConfidenceLevel
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    error: str | None = Field(
        None, description="Set if the LLM call failed; ``answer`` will contain a safe fallback."
    )


# --------------------------------------------------------------------------- #
# P&ID vision (Phase 3)
# --------------------------------------------------------------------------- #
class PIDSymbolType(str, Enum):
    """The 5 template-matched P&ID symbol classes (v1, non-ML)."""

    VALVE = "valve"
    PUMP = "pump"
    TANK = "tank"
    INSTRUMENT = "instrument_bubble"
    FLOW_ARROW = "flow_arrow"
    UNKNOWN = "unknown_shape"


class PIDBoundingBox(BaseModel):
    """Pixel-space bounding box in the original uploaded image."""

    x: int
    y: int
    width: int
    height: int


class PIDSymbol(BaseModel):
    """One detected P&ID symbol."""

    symbol_type: PIDSymbolType
    confidence: float = Field(..., ge=0.0, le=1.0, description="Shape-match confidence, 0..1")
    bounding_box: PIDBoundingBox
    nearby_tag_text: str | None = Field(
        None, description="Equipment tag OCR'd near the symbol, e.g. 'P-101A'"
    )
    position_x: float = Field(..., description="Symbol center x, pixel coordinates")
    position_y: float = Field(..., description="Symbol center y, pixel coordinates")


class PIDAnalysisResponse(BaseModel):
    """POST /api/pid/analyze structured response."""

    filename: str
    image_width: int
    image_height: int
    symbols: list[PIDSymbol] = Field(default_factory=list)
    symbol_counts: dict[str, int] = Field(default_factory=dict)
    annotated_image_base64: str = Field(
        ..., description="PNG bytes of the annotated image, base64-encoded (data-URI ready)"
    )
    graph: GraphLinkResult | None = Field(
        None, description="Set when link_to_graph=true; null if linking was skipped"
    )
