"""Hybrid graph + vector RAG engine — the Expert Knowledge Copilot.

Flow
----
1. Embed the question and retrieve top-k chunks from ChromaDB (VectorStore).
2. Pull graph entities connected to those chunks' source documents from Neo4j
   (KnowledgeGraph.get_related_entities) to enrich context beyond raw text.
3. Build a role-aware prompt that forces Gemini to answer ONLY from the
   retrieved context, cite the source document for every claim, and self-report
   a confidence level.
4. Compute a *retrieval-based* confidence score independently (not just trusting
   the LLM's self-report) from the vector distances, and use the lower/more
   conservative of the two so the UI doesn't over-trust a shaky answer.

This intentionally does NOT use LlamaIndex's own vector-store wrapper — the
ChromaDB collection is already owned and populated by VectorStore (Phase 1),
so re-wrapping it would add an abstraction layer with no retrieval benefit for
a single-collection hackathon scope. LlamaIndex remains a dependency for
future phases where its graph/workflow primitives pay for themselves.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.config import Settings, get_settings
from app.core.knowledge_graph import KnowledgeGraph
from app.core.vector_store import VectorStore
from app.models.schemas import (
    ConfidenceLevel,
    QueryResponse,
    RelatedEntity,
    SourceCitation,
    UserRole,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# In-memory conversation memory (hackathon scope — swap for Redis/DB later)
# --------------------------------------------------------------------------- #
# {session_id: [{"role": "user"|"assistant", "content": str}, ...]}
_CONVERSATION_STORE: dict[str, list[dict[str, str]]] = {}
_MAX_HISTORY_TURNS = 6  # keep the last N (user, assistant) pairs per session


# --------------------------------------------------------------------------- #
# Response schema (Gemini structured output for the answer itself)
# --------------------------------------------------------------------------- #
ANSWER_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "The answer, written for the requester's role, using ONLY the provided context.",
        },
        "self_reported_confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": (
                "'high' if the context directly and completely answers the question; "
                "'medium' if the context partially answers it or requires minor inference; "
                "'low' if the context barely relates or the answer is mostly absent."
            ),
        },
        "citations_used": {
            "type": "array",
            "description": "Which chunk indices (0-based, from the provided context) were actually used to support the answer.",
            "items": {"type": "integer"},
        },
        "insufficient_context": {
            "type": "boolean",
            "description": "True if the retrieved context does not contain enough information to answer the question at all.",
        },
    },
    "required": ["answer", "self_reported_confidence", "citations_used", "insufficient_context"],
}


ROLE_STYLE_GUIDANCE: dict[UserRole, str] = {
    UserRole.TECHNICIAN: (
        "Write for a field technician on the plant floor, possibly on a phone. "
        "Use short sentences, plain language, and concrete steps. Avoid jargon "
        "unless it's a term technicians use daily (equipment tags, common units). "
        "Lead with the direct answer/action first."
    ),
    UserRole.ENGINEER: (
        "Write for a plant engineer. Include relevant technical detail — exact "
        "parameter values, tolerances, standards referenced — and explain the "
        "reasoning, not just the conclusion."
    ),
    UserRole.AUDITOR: (
        "Write for a compliance/safety auditor. Emphasize traceability: which "
        "document and regulation each fact comes from, and note explicitly if "
        "something required for a full audit trail is missing from the context."
    ),
}


SYSTEM_PROMPT_TEMPLATE = """You are the Expert Knowledge Copilot for an Indian industrial \
plant's unified knowledge base (maintenance records, safety procedures, \
inspection reports, P&IDs, compliance filings).

STRICT RULES:
- Answer ONLY using the CONTEXT provided below. Never use outside/general knowledge \
  about industrial equipment, even if you know it — if it's not in the context, it's \
  not available to you.
- Every factual claim must be traceable to a specific context chunk. Track which \
  chunk indices you actually relied on in `citations_used`.
- If the context does not contain enough information to answer, set \
  `insufficient_context: true` and say so plainly in `answer` rather than guessing \
  or filling gaps with plausible-sounding industrial knowledge.
- Never invent equipment tags, values, names, or regulatory references that are not \
  literally present in the context.

STYLE FOR THIS REQUESTER: {role_style}

CONTEXT (numbered chunks, each from a specific source document):
{context_block}

{graph_context_block}"""


class RAGEngine:
    """Hybrid vector + graph retrieval-augmented generation engine."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: genai.Client | None = None
        self._vector_store = VectorStore(self.settings)
        self._graph = KnowledgeGraph(self.settings)

    @property
    def client(self) -> genai.Client:
        """Lazily build the Gemini client."""
        if self._client is None:
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def query(
        self,
        question: str,
        role: UserRole = UserRole.ENGINEER,
        session_id: str | None = None,
        top_k: int = 5,
    ) -> QueryResponse:
        """Answer ``question`` using hybrid vector + graph retrieval.

        Args:
            question: The user's natural-language question.
            role: Shapes response style only — retrieval is identical for all roles.
            session_id: Conversation thread id. A new one is generated if omitted.
            top_k: Number of chunks to retrieve from ChromaDB.

        Returns:
            A fully populated :class:`QueryResponse`. Never raises — LLM/graph
            failures degrade to a safe fallback answer with ``error`` set.
        """
        session_id = session_id or str(uuid.uuid4())
        history = _CONVERSATION_STORE.get(session_id, [])

        # --- 1. Vector retrieval ------------------------------------------
        retrieved = self._vector_store.query(question, k=top_k)
        retrieved = [r for r in retrieved if "error" not in r]

        if not retrieved:
            return self._no_context_response(session_id, question)

        # --- 2. Graph enrichment -------------------------------------------
        doc_ids = list({r["document_id"] for r in retrieved if r.get("document_id")})
        related = self._graph.get_related_entities(doc_ids)

        # --- 3. Build prompt + call Gemini ----------------------------------
        try:
            llm_result = self._generate_answer(question, role, retrieved, related, history)
        except Exception as exc:  # noqa: BLE001
            logger.exception("RAG generation failed for session '%s'", session_id)
            return QueryResponse(
                session_id=session_id,
                answer=(
                    "I couldn't generate an answer right now due to a system error. "
                    "Please try again in a moment."
                ),
                sources=[],
                confidence=ConfidenceLevel.LOW,
                related_entities=[],
                error=str(exc),
            )

        # --- 4. Assemble structured response --------------------------------
        sources = self._build_citations(retrieved, llm_result.get("citations_used", []))
        confidence = self._resolve_confidence(retrieved, llm_result)
        related_entities = [
            RelatedEntity(label=r["label"], value=r["value"], relationship=r["relationship"])
            for r in related
        ]

        answer_text = llm_result["answer"]
        if llm_result.get("insufficient_context"):
            # Confidence should never read "high" if the model itself flagged a gap.
            confidence = ConfidenceLevel.LOW

        # --- 5. Update conversation memory -----------------------------------
        self._update_history(session_id, question, answer_text)

        return QueryResponse(
            session_id=session_id,
            answer=answer_text,
            sources=sources,
            confidence=confidence,
            related_entities=related_entities,
            error=None,
        )

    # ------------------------------------------------------------------ #
    # Internals — generation
    # ------------------------------------------------------------------ #
    def _generate_answer(
        self,
        question: str,
        role: UserRole,
        retrieved: list[dict[str, Any]],
        related: list[dict[str, str | None]],
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Call Gemini with the constructed context and return parsed JSON."""
        import json

        context_block = self._format_context(retrieved)
        graph_context_block = self._format_graph_context(related)
        role_style = ROLE_STYLE_GUIDANCE[role]

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            role_style=role_style,
            context_block=context_block,
            graph_context_block=graph_context_block,
        )

        contents = self._build_contents(history, question)

        response = self.client.models.generate_content(
            model=self.settings.gemini_model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=ANSWER_RESPONSE_SCHEMA,
                max_output_tokens=self.settings.gemini_max_tokens,
            ),
        )

        raw_text = getattr(response, "text", None)
        if not raw_text:
            raise RuntimeError("Gemini returned no text (possible safety block).")
        return json.loads(raw_text)

    @staticmethod
    def _build_contents(history: list[dict[str, str]], question: str) -> list[dict[str, Any]]:
        """Build the multi-turn ``contents`` list for Gemini from stored history."""
        contents: list[dict[str, Any]] = []
        for turn in history[-(_MAX_HISTORY_TURNS * 2):]:
            gemini_role = "model" if turn["role"] == "assistant" else "user"
            contents.append({"role": gemini_role, "parts": [{"text": turn["content"]}]})
        contents.append({"role": "user", "parts": [{"text": question}]})
        return contents

    @staticmethod
    def _format_context(retrieved: list[dict[str, Any]]) -> str:
        """Render retrieved chunks as a numbered, source-labeled block."""
        lines = []
        for i, r in enumerate(retrieved):
            filename = r.get("metadata", {}).get("filename", "unknown document")
            lines.append(f"[{i}] Source: {filename}\n{r['text']}")
        return "\n\n".join(lines)

    @staticmethod
    def _format_graph_context(related: list[dict[str, str | None]]) -> str:
        """Render graph-derived facts as a supplementary block, or empty note."""
        if not related:
            return "GRAPH CONTEXT: (none available)"
        lines = [f"- {r['label']}: {r['value']} ({r['relationship']})" for r in related]
        return "GRAPH CONTEXT (structured facts related to the retrieved documents):\n" + "\n".join(
            lines
        )

    # ------------------------------------------------------------------ #
    # Internals — response assembly
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_citations(
        retrieved: list[dict[str, Any]], citation_indices: list[int]
    ) -> list[SourceCitation]:
        """Build SourceCitation objects, preferring chunks the LLM says it used.

        Falls back to all retrieved chunks if the model didn't return usable
        indices (defensive — keeps sources non-empty for a successful answer).
        """
        indices = [i for i in citation_indices if isinstance(i, int) and 0 <= i < len(retrieved)]
        chosen = [retrieved[i] for i in indices] if indices else retrieved

        citations: list[SourceCitation] = []
        for r in chosen:
            meta = r.get("metadata", {}) or {}
            distance = r.get("distance")
            relevance = max(0.0, 1.0 - distance) if isinstance(distance, (int, float)) else 0.0
            citations.append(
                SourceCitation(
                    doc_name=meta.get("filename", "unknown document"),
                    document_id=r.get("document_id") or "",
                    page=None,  # chunk-level; page granularity not tracked post-chunking
                    snippet=(r["text"][:400] + "…") if len(r["text"]) > 400 else r["text"],
                    relevance_score=round(relevance, 3),
                )
            )
        return citations

    @staticmethod
    def _resolve_confidence(
        retrieved: list[dict[str, Any]], llm_result: dict[str, Any]
    ) -> ConfidenceLevel:
        """Combine retrieval-distance confidence with the LLM's self-report.

        We take the MORE CONSERVATIVE of the two signals, but the retrieval
        thresholds below are calibrated against this project's actual embedding
        model rather than a generic guess. Cosine *distance* in the 0.4-0.6
        range is a normal, healthy match for this embedding model on a small
        multi-topic corpus — it does NOT mean "unrelated", so treating
        everything above 0.55 as LOW was overly harsh and dragged every answer
        (including clean, well-grounded ones) down to LOW regardless of
        quality. Thresholds were recalibrated from real observed distances
        (~0.44-0.62 on genuinely correct retrievals) rather than a generic
        assumption.
        """
        distances = [r["distance"] for r in retrieved if isinstance(r.get("distance"), (int, float))]
        if distances:
            best_distance = min(distances)  # the closest single match matters most
            if best_distance < 0.45:
                retrieval_confidence = ConfidenceLevel.HIGH
            elif best_distance < 0.70:
                retrieval_confidence = ConfidenceLevel.MEDIUM
            else:
                retrieval_confidence = ConfidenceLevel.LOW
        else:
            retrieval_confidence = ConfidenceLevel.LOW

        self_reported = llm_result.get("self_reported_confidence", "low")
        try:
            llm_confidence = ConfidenceLevel(self_reported)
        except ValueError:
            llm_confidence = ConfidenceLevel.LOW

        order = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.HIGH: 2}
        return min(retrieval_confidence, llm_confidence, key=lambda c: order[c])

    @staticmethod
    def _no_context_response(session_id: str, question: str) -> QueryResponse:
        """Response when vector retrieval returns nothing (empty/broken corpus)."""
        answer = (
            "I don't have any relevant documents to answer this question yet. "
            "Try ingesting relevant documents first, or rephrase the question."
        )
        RAGEngine._update_history(session_id, question, answer)
        return QueryResponse(
            session_id=session_id,
            answer=answer,
            sources=[],
            confidence=ConfidenceLevel.LOW,
            related_entities=[],
            error=None,
        )

    @staticmethod
    def _update_history(session_id: str, question: str, answer: str) -> None:
        """Append this turn to in-memory conversation history, capped in length."""
        history = _CONVERSATION_STORE.setdefault(session_id, [])
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        max_len = _MAX_HISTORY_TURNS * 2
        if len(history) > max_len:
            del history[: len(history) - max_len]


# Module-level convenience instance.
rag_engine = RAGEngine()
