"""POST /api/ingest — the document ingestion pipeline.

Flow::

    UploadFile (PDF)
      -> DocumentParser.parse()           # text + tables, OCR fallback
         -> EntityExtractor.extract()     # Claude tool-use NER
            -> KnowledgeGraph.link_entities()   # Neo4j (idempotent MERGE)
            -> VectorStore.add_document()       # ChromaDB chunk + embed
      -> IngestionResponse (structured JSON)

Every failure path returns structured JSON rather than a bare 500, so the
frontend can show what succeeded (e.g. parsed OK, vector stored, but graph
unreachable) and what didn't.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.document_parser import DocumentParser
from app.core.entity_extractor import EntityExtractor
from app.core.knowledge_graph import KnowledgeGraph
from app.core.vector_store import VectorStore, generate_document_id
from app.models.schemas import ExtractedEntities, IngestionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["ingestion"])

ALLOWED_EXTENSIONS = {".pdf"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB safety cap


@router.post(
    "/ingest",
    response_model=IngestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest a PDF (parse -> extract entities -> graph -> vector store)",
)
async def ingest_document(file: UploadFile = File(...)) -> IngestionResponse:
    """Ingest one PDF through the full extraction + linking pipeline.

    Returns a structured :class:`IngestionResponse` describing what was parsed,
    which entities were extracted, and whether Neo4j / ChromaDB writes
    succeeded. Partial failures (e.g. Neo4j down) are reported in the response,
    not raised.
    """
    filename = file.filename or "upload.pdf"

    # --- Validate extension + size ---------------------------------------
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty."
        )
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    document_id = generate_document_id(filename)

    # --- 1. Parse --------------------------------------------------------
    try:
        parsed = DocumentParser().parse(file_bytes, filename)
    except ValueError as exc:
        logger.warning("Parse failed for '%s': %s", filename, exc)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    full_text = parsed.full_text()

    # --- 2. Extract entities (Claude) ------------------------------------
    # Extraction failure is non-fatal (the doc is still searchable via the
    # vector store), but we MUST surface the error to the caller instead of
    # silently returning empty entities.
    extraction_error: str | None = None
    try:
        entities = EntityExtractor().extract(full_text, filename)
    except RuntimeError as exc:
        logger.warning("Entity extraction failed for '%s': %s", filename, exc)
        extraction_error = str(exc)
        entities = ExtractedEntities()

    # --- 3. Knowledge graph (Neo4j) --------------------------------------
    graph_result = KnowledgeGraph().link_entities(document_id, filename, entities)

    # --- 4. Vector store (ChromaDB) --------------------------------------
    vector_result = VectorStore().add_document(
        document_id=document_id,
        text=full_text,
        metadata={
            "filename": filename,
            "document_type": entities.document_type.value,
            "pages": parsed.total_pages,
            "is_scanned": parsed.is_scanned_any,
            "source": "upload",
        },
    )

    # --- Response --------------------------------------------------------
    # "partial" when extraction failed (e.g. Claude billing/auth error) even
    # if parsing and vector storage succeeded.
    final_status = "ok" if extraction_error is None else "partial"

    return IngestionResponse(
        status=final_status,
        filename=filename,
        document_id=document_id,
        pages_parsed=parsed.total_pages,
        is_scanned=parsed.is_scanned_any,
        ocr_used=parsed.ocr_used,
        extracted=entities,
        graph=graph_result,
        vector=vector_result,
        extraction_error=extraction_error,
    )
