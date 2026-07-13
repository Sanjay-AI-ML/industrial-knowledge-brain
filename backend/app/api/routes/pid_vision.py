"""P&ID computer-vision route (Phase 3).

Accuracy note (read this before demoing)
-----------------------------------------
Symbol detection here is **contour + Hu-moment template matching**
(OpenCV/scikit-image), not a trained deep-learning detector. That's a
deliberate v1 constraint (fully offline, zero model downloads, no GPU). It
means:

* It works well on clean, vector-exported or high-contrast scanned P&IDs
  with symbols close to standard ISA shapes.
* It will struggle with: rotated/mirrored symbols, hand-drawn or heavily
  stylized company-specific symbol sets, overlapping/touching symbols, and
  low-contrast or skewed scans.
* Confidence scores reflect shape-matching distance only — they are not a
  calibrated probability the way a trained classifier's would be.
* Pump vs. instrument-bubble and valve-subtype (gate/globe/check/control)
  disambiguation is approximate; real symbol libraries vary by company/
  standard (ISA-5.1 vs. in-house conventions).

Positioned honestly, this is a legitimate v1: it proves the ingestion ->
detection -> knowledge-graph pipeline end-to-end without an ML dependency,
and every detection is human-auditable via the annotated image. The upgrade
path (fine-tuned YOLO/Detectron2 on a labeled company P&ID symbol set) is a
drop-in replacement behind the same ``PIDDetector.analyze()`` interface.
"""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.core.knowledge_graph import KnowledgeGraph
from app.core.pid_detector import PIDDetector, encode_png
from app.core.vector_store import generate_document_id
from app.models.schemas import PIDAnalysisResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["pid_vision"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@router.get("/pid/health")
async def pid_health() -> dict[str, str]:
    """Liveness probe for the P&ID vision subsystem."""
    return {"status": "ok", "phase": "3 — P&ID symbol detection (OpenCV, offline)"}


@router.post(
    "/pid/analyze",
    response_model=PIDAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect P&ID symbols (valve/pump/tank/instrument/flow-arrow) via OpenCV template matching",
)
async def analyze_pid(
    file: UploadFile = File(...),
    link_to_graph: bool = Query(
        True, description="If true, merge detected equipment tags into the Neo4j knowledge graph"
    ),
) -> PIDAnalysisResponse:
    """Analyze an uploaded P&ID image and return detected symbols + an annotated image.

    Note: PDF P&IDs must be converted to an image first (e.g. via ``pdf2image``,
    already a project dependency) before uploading here — this endpoint takes
    raster images (PNG/JPG) directly so the CV pipeline can run on pixels.
    """
    filename = file.filename or "pid.png"

    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_EXTENSIONS)}. "
            "Convert PDF pages to PNG/JPG first (e.g. with pdf2image).",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    try:
        symbols, annotated = PIDDetector().analyze(image_bytes, filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    annotated_png = encode_png(annotated)
    annotated_b64 = base64.b64encode(annotated_png).decode("ascii")

    symbol_counts: dict[str, int] = {}
    for s in symbols:
        symbol_counts[s.symbol_type.value] = symbol_counts.get(s.symbol_type.value, 0) + 1

    graph_result = None
    if link_to_graph:
        document_id = generate_document_id(filename)
        graph_result = KnowledgeGraph().link_pid_symbols(document_id, filename, symbols)

    return PIDAnalysisResponse(
        filename=filename,
        image_height=annotated.shape[0],
        image_width=annotated.shape[1],
        symbols=symbols,
        symbol_counts=symbol_counts,
        annotated_image_base64=annotated_b64,
        graph=graph_result,
    )
