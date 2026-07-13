"""Compliance Gap Detection Agent.

⚠️  DISCLAIMER  ⚠️
This module is a DECISION-SUPPORT TOOL only.  It is NOT a substitute for
qualified legal / regulatory advice, certified compliance audits, or
professional interpretations of statutes and standards.  All gap
identifications and coverage assessments are illustrative and non-exhaustive.
Real compliance audits must be conducted by qualified compliance officers
familiar with applicable Indian and international regulations.

Architecture
------------
1. A curated, versioned reference set of key Indian regulatory requirements
   (Factory Act 1948, OISD standards, PESO rules) stored in-process as
   structured JSON — clearly labelled as illustrative summaries for demo use.
2. Given a facility area or equipment tag, the agent:
   a) Queries ChromaDB for any matching procedures / inspection records.
   b) Queries Neo4j for documents and regulatory references linked to that area.
   c) Uses Gemini structured-output to cross-reference the corpus against each
      regulatory requirement and classify coverage as COVERED / PARTIAL / GAP.
   d) Generates plain-language gap explanations and remediation suggestions.
3. An ``audit_evidence_package`` builder that, given a regulation ID, pulls all
   linked documents/citations into a structured summary for an auditor.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.config import Settings, get_settings
from app.core.knowledge_graph import KnowledgeGraph
from app.core.vector_store import VectorStore

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Regulatory reference set
# (illustrative summaries — NOT exhaustive legal text)
# --------------------------------------------------------------------------- #
REGULATORY_REFERENCES: list[dict[str, Any]] = [
    # ------------------------------------------------------------------ #
    # Factory Act 1948
    # ------------------------------------------------------------------ #
    {
        "id": "FA-1948-S13",
        "regulation": "Factory Act 1948",
        "clause": "Section 13 — Ventilation & Temperature",
        "requirement": (
            "Every factory shall make effective and suitable provision for securing "
            "and maintaining adequate ventilation and reasonable temperature in every "
            "workroom, including control of humidity and heat in process areas."
        ),
        "keywords": ["ventilation", "temperature", "humidity", "heat", "workroom"],
        "severity": "high",
    },
    {
        "id": "FA-1948-S21",
        "regulation": "Factory Act 1948",
        "clause": "Section 21 — Fencing of Machinery",
        "requirement": (
            "Every dangerous part of any machinery shall be securely fenced by "
            "safeguards of substantial construction which shall be constantly maintained "
            "and kept in position while the parts of machinery they are fencing are in "
            "motion or in use."
        ),
        "keywords": ["machinery", "fencing", "guarding", "safeguard", "rotating parts"],
        "severity": "critical",
    },
    {
        "id": "FA-1948-S38",
        "regulation": "Factory Act 1948",
        "clause": "Section 38 — Fire Prevention & Firefighting",
        "requirement": (
            "Every factory shall be provided with adequate means of escape in case of "
            "fire, and all fire exits, fire extinguishers, hydrant systems shall be "
            "maintained in good repair and inspected periodically. Fire drills must "
            "be conducted at regular intervals."
        ),
        "keywords": ["fire", "escape", "extinguisher", "hydrant", "fire drill", "emergency"],
        "severity": "critical",
    },
    {
        "id": "FA-1948-S41B",
        "regulation": "Factory Act 1948",
        "clause": "Section 41-B — Compulsory Disclosure of Information",
        "requirement": (
            "Occupiers of hazardous process factories must disclose relevant safety "
            "information including process hazards, MSDS (Material Safety Data Sheets), "
            "and emergency response plans to workers and local authorities."
        ),
        "keywords": ["msds", "hazardous", "disclosure", "safety information", "emergency response"],
        "severity": "high",
    },
    # ------------------------------------------------------------------ #
    # OISD Standards (Oil Industry Safety Directorate)
    # ------------------------------------------------------------------ #
    {
        "id": "OISD-117",
        "regulation": "OISD STD 117",
        "clause": "Fire Protection Facilities for Petroleum Depots & Terminals",
        "requirement": (
            "Oil installations shall maintain adequate fire protection systems including "
            "fixed foam systems, deluge systems, water spray for vessels and tanks, "
            "dedicated fire water pump sets, and trained Emergency Response Teams (ERT)."
        ),
        "keywords": ["foam", "deluge", "fire water", "ert", "emergency response team", "fire pump"],
        "severity": "critical",
    },
    {
        "id": "OISD-118",
        "regulation": "OISD STD 118",
        "clause": "Layouts for Oil and Gas Installations",
        "requirement": (
            "Layout of oil and gas installations shall comply with minimum safe separation "
            "distances between process units, storage facilities, and buildings. "
            "Risk-based layout review shall be conducted for new or modified installations."
        ),
        "keywords": ["layout", "separation distance", "process unit", "storage", "risk"],
        "severity": "high",
    },
    {
        "id": "OISD-154",
        "regulation": "OISD STD 154",
        "clause": "Safety in Operation of Pumps and Compressors",
        "requirement": (
            "All centrifugal and reciprocating pumps in petroleum service shall have "
            "documented maintenance procedures, vibration monitoring programs, mechanical "
            "seal inspection schedules, alignment checks per API 686, and records of "
            "work orders and inspection outcomes in a CMMS."
        ),
        "keywords": [
            "pump", "compressor", "vibration", "mechanical seal", "alignment",
            "api 686", "cmms", "maintenance procedure", "inspection",
        ],
        "severity": "critical",
    },
    {
        "id": "OISD-GDN-192",
        "regulation": "OISD GDN 192",
        "clause": "Permit to Work (PTW) Systems",
        "requirement": (
            "All hazardous work including hot work, confined space entry, and work on "
            "energized systems shall be controlled by a formal Permit to Work system "
            "with documented signatures from issuing authority, area incharge, and "
            "safety officer. PTW records shall be maintained for 3 years."
        ),
        "keywords": [
            "permit to work", "ptw", "hot work", "confined space", "safety clearance",
            "permit", "hazardous work",
        ],
        "severity": "critical",
    },
    # ------------------------------------------------------------------ #
    # PESO (Petroleum and Explosives Safety Organisation)
    # ------------------------------------------------------------------ #
    {
        "id": "PESO-SCR",
        "regulation": "PESO — Static & Mobile Pressure Vessels Rules",
        "clause": "Statutory Inspection of Pressure Vessels",
        "requirement": (
            "All pressure vessels operating above atmospheric pressure shall be "
            "inspected by a competent person approved under PESO / CCOE regulations "
            "at prescribed intervals. Inspection certificates and test reports shall "
            "be maintained and available for audit."
        ),
        "keywords": [
            "pressure vessel", "inspection certificate", "peso", "statutory inspection",
            "competent person", "hydrotest", "thickness survey",
        ],
        "severity": "critical",
    },
    {
        "id": "PESO-GAS",
        "regulation": "PESO — Gas Cylinder Rules",
        "clause": "Handling and Storage of Compressed Gas Cylinders",
        "requirement": (
            "Compressed gas cylinders shall be stored upright in well-ventilated areas, "
            "secured against falling, segregated by gas type, and colour-coded. "
            "Periodic hydrostatic testing of cylinders shall be documented."
        ),
        "keywords": ["gas cylinder", "compressed gas", "storage", "hydrostatic", "colour-coded"],
        "severity": "medium",
    },
]

# Build quick lookup
REG_BY_ID: dict[str, dict[str, Any]] = {r["id"]: r for r in REGULATORY_REFERENCES}


# --------------------------------------------------------------------------- #
# Result dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class GapItem:
    """A single regulatory requirement with its assessed coverage status."""

    regulation_id: str
    regulation: str
    clause: str
    requirement: str
    severity: str
    status: str = "gap"          # "covered" | "partial" | "gap"
    evidence_docs: list[str] = field(default_factory=list)
    gap_explanation: str = ""
    remediation: str = ""


@dataclass
class GapReport:
    """Full gap analysis report for a facility area or equipment tag."""

    query: str
    facility_area: str
    total_requirements: int = 0
    covered: int = 0
    partial: int = 0
    gaps: int = 0
    items: list[GapItem] = field(default_factory=list)
    disclaimer: str = (
        "⚠ DISCLAIMER: This report is generated by an AI decision-support tool "
        "and is NOT a substitute for a formal compliance audit conducted by a "
        "qualified compliance officer. All gap findings are illustrative and "
        "non-exhaustive. Real audits must be conducted by certified professionals."
    )


@dataclass
class AuditEvidencePackage:
    """Structured evidence package for a single regulatory requirement."""

    regulation_id: str
    regulation: str
    clause: str
    requirement: str
    evidence_documents: list[dict[str, str]] = field(default_factory=list)
    coverage_summary: str = ""
    disclaimer: str = (
        "⚠ DISCLAIMER: This evidence package is AI-generated for decision-support "
        "purposes only. It does not constitute a legal compliance certification."
    )


# --------------------------------------------------------------------------- #
# Compliance Agent
# --------------------------------------------------------------------------- #
# Gemini structured output schema for gap analysis
_GAP_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "regulation_id": {"type": "STRING"},
            "status": {
                "type": "STRING",
                "enum": ["covered", "partial", "gap"],
                "description": (
                    "'covered' if the corpus clearly shows full compliance evidence, "
                    "'partial' if some but incomplete evidence exists, "
                    "'gap' if no matching evidence is found."
                ),
            },
            "evidence_docs": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Filenames or document IDs that provide supporting evidence.",
            },
            "gap_explanation": {
                "type": "STRING",
                "description": "Plain-language explanation of what is missing (empty string if covered).",
            },
            "remediation": {
                "type": "STRING",
                "description": "Suggested corrective action to close the gap (empty string if covered).",
            },
        },
        "required": ["regulation_id", "status", "evidence_docs", "gap_explanation", "remediation"],
    },
}


class ComplianceAgent:
    """Cross-references ingested corpus against regulatory requirements."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._vs = VectorStore(self.settings)
        self._kg = KnowledgeGraph(self.settings)
        self._client = genai.Client(api_key=self.settings.gemini_api_key)

    # ------------------------------------------------------------------ #
    # Gap Analysis
    # ------------------------------------------------------------------ #
    def run_gap_analysis(self, query: str) -> GapReport:
        """Cross-reference the corpus against all regulatory requirements."""
        report = GapReport(query=query, facility_area=query)

        # 1. Gather corpus evidence
        corpus_text, doc_filenames = self._gather_corpus(query)

        # 2. Build Gemini prompt
        reg_list_json = json.dumps(
            [
                {
                    "id": r["id"],
                    "regulation": r["regulation"],
                    "clause": r["clause"],
                    "requirement": r["requirement"],
                    "severity": r["severity"],
                }
                for r in REGULATORY_REFERENCES
            ],
            indent=2,
        )

        prompt = (
            "You are a Senior Compliance Auditor reviewing an industrial facility's "
            "document corpus against Indian regulatory requirements.\n\n"
            f"FACILITY / EQUIPMENT BEING AUDITED: {query}\n\n"
            "=== CORPUS EVIDENCE (ingested documents, procedures, inspection records) ===\n"
            f"{corpus_text}\n\n"
            "=== REGULATORY REQUIREMENTS TO ASSESS ===\n"
            f"{reg_list_json}\n\n"
            "INSTRUCTIONS:\n"
            "For EACH regulatory requirement, assess whether the corpus provides:\n"
            "- 'covered': Clear documentary evidence of compliance.\n"
            "- 'partial': Some evidence exists but is incomplete or outdated.\n"
            "- 'gap': No matching evidence found in the corpus.\n"
            "For gaps and partial items, write a plain-language explanation and "
            "suggest specific remediation steps.\n"
            "Return a JSON array with one object per regulation_id.\n"
            "⚠ This is for decision-support only, not a legal opinion."
        )

        try:
            response = self._client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_GAP_ANALYSIS_SCHEMA,
                    max_output_tokens=4096,
                ),
            )
            assessments: list[dict] = json.loads(response.text or "[]")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gemini gap analysis failed: %s", exc)
            assessments = []

        # 3. Merge assessments back to the reference set
        assessment_map = {a["regulation_id"]: a for a in assessments}
        items: list[GapItem] = []

        for ref in REGULATORY_REFERENCES:
            a = assessment_map.get(ref["id"], {})
            item = GapItem(
                regulation_id=ref["id"],
                regulation=ref["regulation"],
                clause=ref["clause"],
                requirement=ref["requirement"],
                severity=ref["severity"],
                status=a.get("status", "gap"),
                evidence_docs=a.get("evidence_docs", []),
                gap_explanation=a.get("gap_explanation", "Unable to assess — no Gemini response."),
                remediation=a.get("remediation", ""),
            )
            items.append(item)

        # 4. Summary counts
        report.items = items
        report.total_requirements = len(items)
        report.covered = sum(1 for i in items if i.status == "covered")
        report.partial = sum(1 for i in items if i.status == "partial")
        report.gaps = sum(1 for i in items if i.status == "gap")

        return report

    # ------------------------------------------------------------------ #
    # Audit Evidence Package
    # ------------------------------------------------------------------ #
    def build_evidence_package(self, regulation_id: str) -> AuditEvidencePackage:
        """Pull all corpus evidence related to a single regulation."""
        ref = REG_BY_ID.get(regulation_id.upper())
        if not ref:
            return AuditEvidencePackage(
                regulation_id=regulation_id,
                regulation="Unknown",
                clause="Unknown",
                requirement="Regulation ID not found in reference set.",
                coverage_summary="No matching regulation found.",
            )

        # Build search query from regulation keywords
        keyword_query = " ".join(ref["keywords"][:5])
        corpus_text, doc_filenames = self._gather_corpus(keyword_query)

        # Ask Gemini for a structured audit summary
        prompt = (
            f"You are preparing an audit evidence package for the following regulation:\n\n"
            f"Regulation: {ref['regulation']} — {ref['clause']}\n"
            f"Requirement: {ref['requirement']}\n\n"
            "=== AVAILABLE CORPUS DOCUMENTS ===\n"
            f"{corpus_text}\n\n"
            "Write a concise (200-300 word) audit evidence summary covering:\n"
            "1. Which documents provide coverage evidence and what they contain.\n"
            "2. Whether the coverage is complete, partial, or absent.\n"
            "3. Specific document references (filenames / IDs) an auditor should review.\n"
            "⚠ This is for decision-support only, not a legal opinion."
        )

        summary = ""
        try:
            response = self._client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(max_output_tokens=1024),
            )
            summary = getattr(response, "text", "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gemini evidence summary failed: %s", exc)
            summary = "Evidence summary could not be generated."

        evidence_docs = [
            {"filename": fn, "relevance": "Retrieved via keyword search"}
            for fn in doc_filenames
        ]

        return AuditEvidencePackage(
            regulation_id=regulation_id,
            regulation=ref["regulation"],
            clause=ref["clause"],
            requirement=ref["requirement"],
            evidence_documents=evidence_docs,
            coverage_summary=summary,
        )

    # ------------------------------------------------------------------ #
    # Corpus helpers
    # ------------------------------------------------------------------ #
    def _gather_corpus(self, query: str) -> tuple[str, list[str]]:
        """Pull relevant text from ChromaDB + Neo4j for a given query."""
        lines: list[str] = []
        doc_filenames: list[str] = []

        # Vector store retrieval
        try:
            chunks = self._vs.query(query, k=8)
            for i, c in enumerate(chunks):
                if "error" in c:
                    continue
                fn = c.get("metadata", {}).get("filename", "unknown")
                if fn not in doc_filenames:
                    doc_filenames.append(fn)
                lines.append(f"[Doc {i}: {fn}]\n{c['text']}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vector store retrieval failed: %s", exc)

        # Neo4j regulatory references
        try:
            if self._kg.verify_connectivity():
                with self._kg.driver.session() as session:
                    records = session.run(
                        """
                        MATCH (r:Regulation)
                        OPTIONAL MATCH (d:Document)-[:REFERENCES]->(r)
                        RETURN r.reference AS ref, d.filename AS doc
                        LIMIT 20
                        """
                    )
                    for rec in records:
                        ref_val = rec["ref"]
                        doc_val = rec["doc"] or "unknown"
                        lines.append(
                            f"[Graph — Regulation '{ref_val}' referenced in '{doc_val}']"
                        )
                        if doc_val not in doc_filenames:
                            doc_filenames.append(doc_val)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Neo4j regulation query failed: %s", exc)

        corpus_text = "\n\n".join(lines) if lines else "(No corpus evidence retrieved)"
        return corpus_text, doc_filenames


# Module-level instance
compliance_agent = ComplianceAgent()
