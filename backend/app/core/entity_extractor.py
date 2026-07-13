"""Gemini-powered industrial entity extractor.

This module sends parsed document text to the Google Gemini API and forces a
**strictly structured JSON** response via Gemini's native structured-output
mechanism:

* We define ``ENTITY_RESPONSE_SCHEMA``, a JSON-Schema object describing
  exactly the entity shape we want (equipment, parameters, persons, dates,
  regulatory references, document type, …).
* We pass ``response_mime_type="application/json"`` and
  ``response_schema=ENTITY_RESPONSE_SCHEMA`` so Gemini is *required* to return
  JSON matching that shape — it cannot emit free-form prose.
* We then ``json.loads`` the response text and validate it into the
  :class:`~app.models.schemas.ExtractedEntities` Pydantic model.

This is more robust than prompt-level "return JSON only" instructions because
the schema is enforced by the API itself.

Indian industrial context is baked into the system prompt (equipment tag
conventions like ``P-101A``/``V-203``, regulators like OISD / PESO / Factory
Act, document types common in refineries and process plants).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.config import Settings, get_settings
from app.models.schemas import DocumentType, ExtractedEntities

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Response schema (what Gemini is forced to emit)
# --------------------------------------------------------------------------- #
# Build a JSON-Schema object that mirrors ExtractedEntities. We hand-write it
# (rather than generating from the Pydantic model) so the descriptions given to
# Gemini are tuned for Indian industrial documents.
ENTITY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
            "document_type": {
                "type": "string",
                "enum": [t.value for t in DocumentType],
                "description": (
                    "Best single classification of the document. "
                    "P&ID = piping & instrumentation diagram; "
                    "work_order = maintenance work order / job card; "
                    "procedure = SOP / operating or safety procedure; "
                    "inspection_report = inspection or NDT report; "
                    "compliance_filing = regulatory submission; "
                    "maintenance_log = equipment history / logbook; "
                    "msds = material safety data sheet; "
                    "datasheet = equipment datasheet; other = fallback."
                ),
            },
            "document_title": {
                "type": "string",
                "description": "Concise title of the document, or null if none.",
            },
            "summary": {
                "type": "string",
                "description": "One or two sentence summary of what the document is about.",
            },
            "equipment": {
                "type": "array",
                "description": (
                    "Equipment items identified by tag. Indian process-plant tag "
                    "convention: letter prefix + number + optional letter suffix, "
                    "e.g. P-101A (pump), V-203 (vessel), E-305 (exchanger), "
                    "C-401 (compressor), T-110 (tower), F-502 (filter), V-101 (valve)."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "tag": {"type": "string"},
                        "equipment_type": {
                            "type": "string",
                            "description": "pump | vessel | exchanger | compressor | tower | valve | filter | other",
                        },
                        "description": {"type": "string"},
                    },
                    "required": ["tag"],
                },
            },
            "parameters": {
                "type": "array",
                "description": "Process parameters / operating values mentioned.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                        "unit": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "persons": {
                "type": "array",
                "description": "People mentioned (engineers, operators, inspectors, supervisors).",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "dates": {
                "type": "array",
                "description": "Dates found (ISO preferred, free text acceptable).",
                "items": {"type": "string"},
            },
            "regulatory_references": {
                "type": "array",
                "description": (
                    "Indian / international standards cited, e.g. OISD-117, "
                    "OISD-118, OISD-154, PESO, Factories Act 1948, "
                    "Petroleum Rules 2002, TAC, NFPA, API."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "reference": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["reference"],
                },
            },
            "procedures": {
                "type": "array",
                "description": "Names of SOPs / procedures referenced.",
                "items": {"type": "string"},
            },
            "incidents": {
                "type": "array",
                "description": "Incident IDs or descriptions referenced.",
                "items": {"type": "string"},
            },
        },
        "required": [
            "document_type",
            "document_title",
            "summary",
            "equipment",
            "parameters",
            "persons",
            "dates",
            "regulatory_references",
            "procedures",
            "incidents",
        ],
}

SYSTEM_PROMPT = """You are an expert industrial-knowledge extraction engine for Indian \
asset-intensive industries (oil & gas refineries, petrochemical plants, \
manufacturing units).

Given the text of a single document, extract structured entities with high \
precision. Context you should rely on:

- Equipment tags follow the pattern <LETTER>-<NUMBER>[<LETTER>], e.g. P-101A \
  (pump A in unit 101), V-203 (vessel), E-305 (shell-and-tube exchanger), \
  C-401 (centrifugal compressor), T-110 (distillation tower), V-101 (valve).
- Regulatory / standard bodies common in India: OISD (Oil Industry Safety \
  Directorate, e.g. OISD-117 fire protection, OISD-118 safety in petroleum \
  refineries, OISD-154 rotodynamic equipment), PESO (Petroleum & Explosives \
  Safety Organisation), the Factories Act 1948, Petroleum Rules 2002, TAC \
  (Tariff Advisory Committee), and international codes API / ASME / NFPA.
- Typical document types include P&IDs, maintenance work orders / job cards, \
  safety and operating procedures (SOPs), inspection / NDT reports, \
  compliance filings, maintenance logs, MSDS, and equipment datasheets.

Rules:
- Only extract entities explicitly present in the text; never invent.
- Normalise equipment tags to UPPERCASE with the dash (e.g. "pump p101a" -> "P-101A").
- If you are unsure about a field, prefer an empty array / null over guessing.
- Respond with JSON matching the required schema exactly. Populate every field;
  use empty arrays/strings when a category has no matches."""


class EntityExtractor:
    """Extract structured industrial entities from text using Gemini structured output."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        """Lazily build the Gemini client (deferred so import is cheap)."""
        if self._client is None:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def extract(self, text: str, filename: str = "") -> ExtractedEntities:
        """Extract entities from ``text``.

        Args:
            text: The document text (typically the concatenation of all pages).
            filename: Optional filename for prompt context only.

        Returns:
            A validated :class:`ExtractedEntities`.

        Raises:
            RuntimeError: If the API call fails or Gemini returns no usable JSON.
        """
        if not text or not text.strip():
            logger.info("Entity extraction skipped: empty text for '%s'.", filename)
            return ExtractedEntities()

        truncated = self._truncate(text)
        user_message = self._build_user_message(truncated, filename)

        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=user_message,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ENTITY_RESPONSE_SCHEMA,
                    max_output_tokens=self.settings.gemini_max_tokens,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gemini API call failed for '%s'", filename)
            raise RuntimeError(f"Entity extraction API call failed: {exc}") from exc

        parsed = self._extract_json(response, filename)
        return self._validate(parsed, filename)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _truncate(text: str, max_chars: int = 50_000) -> str:
        """Cap input length to stay well within Gemini's context window cheaply."""
        if len(text) <= max_chars:
            return text
        logger.warning("Document text truncated to %d chars for extraction.", max_chars)
        return text[:max_chars]

    @staticmethod
    def _build_user_message(text: str, filename: str) -> str:
        header = f"Filename: {filename}\n\n" if filename else ""
        return (
            f"{header}Extract all industrial entities from the following document text, "
            "and return them as JSON matching the required schema.\n\n"
            f"--- DOCUMENT START ---\n{text}\n--- DOCUMENT END ---"
        )

    @staticmethod
    def _extract_json(response: Any, filename: str) -> dict[str, Any]:
        """Parse Gemini's JSON text response into a dict.

        ``response_schema`` forces Gemini to return schema-conforming JSON in
        ``response.text``, but we still guard against empty/malformed output
        (e.g. the prompt was blocked by a safety filter).
        """
        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise RuntimeError(
                f"Gemini returned no text for '{filename}' "
                f"(possible safety block or empty response)."
            )
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Gemini response was not valid JSON for '{filename}': {exc}"
            ) from exc

    def _validate(self, tool_input: dict[str, Any], filename: str) -> ExtractedEntities:
        """Validate the raw tool dict into :class:`ExtractedEntities`.

        Tolerates minor type drift (e.g. a None where a list is expected) by
        coercing; logs and falls back to defaults if validation fully fails.
        """
        try:
            return ExtractedEntities.model_validate(tool_input)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Entity validation failed for '%s' (%s). Returning partial/empty.",
                filename,
                exc,
            )
            # Last-resort: coerce document_type if that's the only offender.
            safe = dict(tool_input)
            safe.setdefault("document_type", DocumentType.OTHER.value)
            safe["document_type"] = DocumentType.OTHER.value
            safe.setdefault("summary", "")
            safe.setdefault("equipment", [])
            safe.setdefault("parameters", [])
            safe.setdefault("persons", [])
            safe.setdefault("dates", [])
            safe.setdefault("regulatory_references", [])
            safe.setdefault("procedures", [])
            safe.setdefault("incidents", [])
            return ExtractedEntities.model_validate(safe)


# Module-level convenience instance.
extractor = EntityExtractor()
