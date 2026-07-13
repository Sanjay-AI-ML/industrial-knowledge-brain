"""Universal document parser.

Strategy
--------
1. Open the PDF with ``pdfplumber`` and extract text + tables page by page.
2. If a page yields very little text (below ``ocr_min_text_len`` chars), it is
   flagged as likely *scanned*.
3. For scanned pages, fall back to ``pdf2image`` (Poppler) + ``pytesseract``
   (Tesseract OCR) — **but only if both binaries are installed**. If they are
   missing, we degrade gracefully: mark the page as scanned, leave the text
   empty, and log a clear warning so the operator can install the binaries.

The parser returns a :class:`~app.models.schemas.ParsedDocument` which the rest
of the pipeline (entity extractor, knowledge graph, vector store) consumes.

No exceptions are raised for OCR-unavailable situations; genuine parse errors
(e.g. corrupt PDF) are raised as :class:`ValueError` for the caller to handle.
"""

from __future__ import annotations

import io
import logging
import shutil
from typing import Any

import pdfplumber

from app.config import Settings, get_settings
from app.models.schemas import ParsedDocument, ParsedPage

logger = logging.getLogger(__name__)


class DocumentParser:
    """Parse text-based and scanned PDFs into structured :class:`ParsedDocument`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ocr_checked = False
        self._ocr_available = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def parse(self, file_bytes: bytes, filename: str = "document.pdf") -> ParsedDocument:
        """Parse a PDF from raw bytes.

        Args:
            file_bytes: Raw PDF file content.
            filename: Original filename (kept for traceability in the result).

        Returns:
            A :class:`ParsedDocument` with per-page text, tables and scan flags.

        Raises:
            ValueError: If the PDF cannot be opened by pdfplumber at all.
        """
        pages: list[ParsedPage] = []
        scanned_page_nums: list[int] = []
        ocr_used = False

        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for idx, page in enumerate(pdf.pages, start=1):
                    raw_text = self._extract_text(page)
                    tables = self._extract_tables(page)

                    is_scanned = len(raw_text.strip()) < self.settings.ocr_min_text_len
                    if is_scanned:
                        scanned_page_nums.append(idx)
                        ocr_text = self._ocr_fallback(file_bytes, idx)
                        if ocr_text:
                            raw_text = ocr_text
                            ocr_used = True
                            # tables from OCR are unreliable; keep empty.

                    pages.append(
                        ParsedPage(
                            page_num=idx,
                            raw_text=raw_text,
                            tables=tables,
                            is_scanned=is_scanned,
                        )
                    )
        except Exception as exc:  # noqa: BLE001 - surface a clean error to the API
            logger.exception("pdfplumber failed to open %s", filename)
            raise ValueError(f"Could not parse PDF '{filename}': {exc}") from exc

        if scanned_page_nums and not ocr_used:
            logger.warning(
                "Pages %s in '%s' appear scanned but OCR is unavailable "
                "(install Tesseract + Poppler to enable). Text for those pages is empty.",
                scanned_page_nums,
                filename,
            )

        return ParsedDocument(
            filename=filename,
            total_pages=len(pages),
            pages=pages,
            is_scanned_any=bool(scanned_page_nums),
            ocr_used=ocr_used,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_text(page: Any) -> str:
        """Extract text from a pdfplumber page, tolerating None."""
        try:
            return page.extract_text() or ""
        except Exception:  # noqa: BLE001
            logger.debug("extract_text failed on a page", exc_info=True)
            return ""

    @staticmethod
    def _extract_tables(page: Any) -> list[list[list[Any]]]:
        """Extract tables from a pdfplumber page, tolerating None / failures."""
        try:
            tables = page.extract_tables() or []
            # tables may contain None cells; normalize to empty strings.
            cleaned: list[list[list[Any]]] = []
            for tbl in tables:
                cleaned.append([[cell if cell is not None else "" for cell in row] for row in tbl])
            return cleaned
        except Exception:  # noqa: BLE001
            logger.debug("extract_tables failed on a page", exc_info=True)
            return []

    def _ocr_fallback(self, file_bytes: bytes, page_num: int) -> str:
        """Run OCR on a single page image if the toolchain is available.

        Returns the OCR text, or an empty string if OCR is disabled or the
        required binaries are missing. Never raises.
        """
        if not self.settings.ocr_fallback_enabled:
            return ""
        if not self._check_ocr_available():
            return ""

        try:
            return self._run_tesseract(file_bytes, page_num)
        except Exception:  # noqa: BLE001
            logger.warning("OCR failed on page %s; leaving text empty.", page_num, exc_info=True)
            return ""

    def _check_ocr_available(self) -> bool:
        """One-time check that both Poppler (pdftoppm) and Tesseract exist."""
        if self._ocr_checked:
            return self._ocr_available

        has_tesseract = shutil.which("tesseract") is not None
        has_poppler = shutil.which("pdftoppm") is not None
        self._ocr_available = has_tesseract and has_poppler
        self._ocr_checked = True

        if not self._ocr_available:
            missing = []
            if not has_tesseract:
                missing.append("Tesseract (https://github.com/UB-Mannheim/tesseract/wiki)")
            if not has_poppler:
                missing.append("Poppler (pdftoppm)")
            logger.info(
                "OCR toolchain incomplete — missing %s. Scanned pages will degrade gracefully.",
                ", ".join(missing),
            )
        return self._ocr_available

    def _run_tesseract(self, file_bytes: bytes, page_num: int) -> str:
        """Convert the target page to an image and OCR it.

        Imported lazily so the app still boots when pdf2image/pytesseract are
        absent (their Python wrappers exist but the system binaries don't).
        """
        from pdf2image import convert_from_bytes
        import pytesseract

        # first_page/last_page are 1-based and inclusive.
        images = convert_from_bytes(
            file_bytes,
            dpi=300,
            first_page=page_num,
            last_page=page_num,
        )
        if not images:
            return ""
        return pytesseract.image_to_string(images[0], lang=self.settings.ocr_language)


# Module-level convenience instance (cheap; Settings are cached).
parser = DocumentParser()
