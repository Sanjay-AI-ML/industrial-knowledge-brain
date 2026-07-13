"""Root Cause Analysis (RCA) & Predictive Maintenance Agent.

Uses LangGraph for the workflow state machine and Google Gemini for
intelligent analysis.

Workflow Steps:
1. **extract_tag** — Extracts equipment tag from the query/description.
2. **fetch_graph_context** — Queries Neo4j for the equipment's history.
3. **fetch_vector_context** — Queries ChromaDB for OEM manual procedures and similar past logs.
4. **generate_rca** — Orchestrates the context and calls Gemini to format a structured RCA.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, TypedDict

from google import genai
from google.genai import types as genai_types
from langgraph.graph import END, StateGraph

from app.config import Settings, get_settings
from app.core.knowledge_graph import KnowledgeGraph
from app.core.vector_store import VectorStore

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# LangGraph state schema
# --------------------------------------------------------------------------- #
class RCAState(TypedDict):
    """Workflow state dictionary passed between nodes in the RCA LangGraph."""

    query: str
    equipment_tag: str
    graph_context: Dict[str, Any]
    vector_context: str
    rca_report: Dict[str, Any]
    error: str | None


# --------------------------------------------------------------------------- #
# Response schema (Gemini structured output for the RCA report itself)
# --------------------------------------------------------------------------- #
RCA_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "probable_root_causes": {
            "type": "ARRAY",
            "description": "List of potential root causes classified under fishbone categories.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "cause": {
                        "type": "STRING",
                        "description": "Description of the probable cause (5-Whys style explanation)."
                    },
                    "category": {
                        "type": "STRING",
                        "enum": ["Man", "Machine", "Method", "Material", "Environment"],
                        "description": "Fishbone diagram category."
                    },
                    "confidence": {
                        "type": "STRING",
                        "enum": ["high", "medium", "low"],
                        "description": "How certain the agent is based on evidence."
                    },
                    "supporting_evidence": {
                        "type": "STRING",
                        "description": "Factual quotes or connections from the graph/vector logs supporting this cause."
                    }
                },
                "required": ["cause", "category", "confidence", "supporting_evidence"]
            }
        },
        "recommended_actions": {
            "type": "ARRAY",
            "description": "List of concrete maintenance and safety recommendations.",
            "items": {"type": "STRING"}
        },
        "similar_past_incidents": {
            "type": "ARRAY",
            "description": "Linked past work orders, maintenance logs, or near-misses.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "incident_id": {
                        "type": "STRING",
                        "description": "Tag, document filename, or work order ID of the past incident."
                    },
                    "description": {
                        "type": "STRING",
                        "description": "Brief summary of what happened previously."
                    },
                    "similarity": {
                        "type": "STRING",
                        "description": "Why this is relevant to the current problem."
                    }
                },
                "required": ["incident_id", "description", "similarity"]
            }
        }
    },
    "required": ["probable_root_causes", "recommended_actions", "similar_past_incidents"]
}


# --------------------------------------------------------------------------- #
# LangGraph nodes
# --------------------------------------------------------------------------- #
def extract_tag_node(state: RCAState) -> Dict[str, Any]:
    """Node: Extract the equipment tag from the user query."""
    query = state["query"]
    
    # Try local regex first on the query itself
    match = re.search(r"\b([A-Z]{1,3}-?\d{2,4}[A-Z]{0,2})\b", query.upper())
    if match:
        tag = match.group(1)
        logger.info("Local regex extracted tag from query: %s", tag)
        return {"equipment_tag": tag}

    # If no tag is in the query text, query Vector Store to search for context matches
    try:
        vs = VectorStore()
        chunks = vs.query(query, k=3)
        for c in chunks:
            if "error" in c:
                continue
            # Search the retrieved text for equipment tags
            chunk_match = re.search(r"\b([A-Z]{1,3}-?\d{2,4}[A-Z]{0,2})\b", c["text"].upper())
            if chunk_match:
                tag = chunk_match.group(1)
                # Filter out standard codes / noise words
                if tag not in ("API", "ISO", "SS", "NDE", "DE", "WAV", "MP3", "HSE", "BPCL", "BHEL", "MSDS"):
                    logger.info("Local regex extracted tag from vector context: %s", tag)
                    return {"equipment_tag": tag}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Vector store lookup for tag extraction failed: %s", exc)

    # Call Gemini to extract the tag if not matching regex directly
    try:
        settings = get_settings()
        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            "Identify if there is any equipment tag (like P-101A, V-203, E-305) "
            "mentioned in the following query. Return ONLY the tag name, or "
            "the word 'None' if no tag is found.\n\n"
            f"Query: {query}"
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt
        )
        tag_text = getattr(response, "text", "None").strip()
        if tag_text.lower() == "none" or len(tag_text) > 12:
            tag_text = ""
        logger.info("Gemini extracted tag: %s", tag_text)
        return {"equipment_tag": tag_text}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tag extraction via Gemini failed: %s", exc)
        return {"equipment_tag": ""}


def fetch_graph_context_node(state: RCAState) -> Dict[str, Any]:
    """Node: Query Neo4j for the equipment's history and neighborhood."""
    tag = state["equipment_tag"]
    if not tag:
        return {"graph_context": {}}

    kg = KnowledgeGraph()
    if not kg.verify_connectivity():
        logger.warning("Neo4j unreachable during RCA; skipping graph context.")
        return {"graph_context": {}}

    try:
        with kg.driver.session() as session:
            # Query parameters and document linkages
            records = session.run(
                """
                MATCH (e:Equipment {tag: $tag})
                OPTIONAL MATCH (p:Parameter)-[:MEASURED_FOR]->(e)
                OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
                OPTIONAL MATCH (other)-[:MENTIONED_IN]->(d)
                WHERE other <> e AND NOT other:Document
                RETURN DISTINCT 
                    labels(other)[0] AS other_label,
                    coalesce(other.tag, other.name, other.reference, other.ref, other.value) AS other_value,
                    labels(p)[0] AS param_label,
                    p.name AS param_name,
                    p.value AS param_val,
                    d.filename AS doc_filename,
                    d.id AS doc_id
                """,
                tag=tag
            )
            
            # Format graph records
            parameters = []
            linked_docs = set()
            linked_entities = []
            
            for r in records:
                if r["param_name"]:
                    parameters.append(f"{r['param_name']}: {r['param_val']}")
                if r["doc_filename"]:
                    linked_docs.add(r["doc_filename"])
                if r["other_label"] and r["other_value"]:
                    linked_entities.append(f"{r['other_label']} ({r['other_value']}) via doc '{r['doc_filename']}'")

            return {
                "graph_context": {
                    "parameters": list(set(parameters)),
                    "documents": list(linked_docs),
                    "linked_entities": list(set(linked_entities))
                }
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_graph_context failed: %s", exc)
        return {"graph_context": {}}


def fetch_vector_context_node(state: RCAState) -> Dict[str, Any]:
    """Node: Query ChromaDB for OEM manual troubleshooting guidance or past work orders."""
    tag = state["equipment_tag"]
    query = state["query"]
    vs = VectorStore()

    try:
        # Search for both tag and the specific incident description
        search_query = f"{tag} {query}".strip()
        chunks = vs.query(search_query, k=5)
        
        formatted_chunks = []
        for i, c in enumerate(chunks):
            if "error" in c:
                continue
            filename = c.get("metadata", {}).get("filename", "unknown document")
            formatted_chunks.append(
                f"[Chunk {i}] File: {filename}\nContent:\n{c['text']}"
            )
        return {"vector_context": "\n\n".join(formatted_chunks)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_vector_context failed: %s", exc)
        return {"vector_context": ""}


def generate_rca_node(state: RCAState) -> Dict[str, Any]:
    """Node: Execute final Gemini generation to construct the structured RCA report."""
    query = state["query"]
    tag = state["equipment_tag"]
    graph_ctx = state["graph_context"]
    vector_ctx = state["vector_context"]

    # Format context blocks
    graph_block = "No direct graph history found in Neo4j."
    if graph_ctx:
        graph_block = (
            f"Parameters:\n" + "\n".join(f"- {p}" for p in graph_ctx.get("parameters", [])) + "\n\n"
            f"Linked Documents:\n" + "\n".join(f"- {d}" for d in graph_ctx.get("documents", [])) + "\n\n"
            f"Linked Entities:\n" + "\n".join(f"- {e}" for e in graph_ctx.get("linked_entities", []))
        )

    prompt = (
        f"You are the Lead Reliability Engineer and RCA Agent. Analyze the following incident report "
        f"for equipment tag '{tag}' and generate a structured Root Cause Analysis (RCA) report.\n\n"
        f"Incident Query/Description:\n{query}\n\n"
        f"=== CONTEXT FROM NEO4J KNOWLEDGE GRAPH ===\n{graph_block}\n\n"
        f"=== CONTEXT FROM INGESTED OEM MANUALS / DOCS ===\n{vector_ctx}\n\n"
        f"INSTRUCTIONS:\n"
        f"1. Perform a 5-Whys style analysis for the probable root causes.\n"
        f"2. Group root causes under fishbone diagram categories (Man, Machine, Method, Material, Environment).\n"
        f"3. Cite specific supporting evidence from the provided context (e.g. document filenames, past parameters).\n"
        f"4. Propose recommended action items.\n"
        f"5. Identify similar past incidents or work orders referenced in the context.\n"
        f"6. Output ONLY a valid JSON matching the schema specified."
    )

    try:
        settings = get_settings()
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RCA_RESPONSE_SCHEMA,
                max_output_tokens=4096
            )
        )
        raw_text = getattr(response, "text", "")
        if not raw_text:
            raise RuntimeError("Gemini returned empty text for RCA.")
            
        report = json.loads(raw_text)
        return {"rca_report": report}
    except Exception as exc:  # noqa: BLE001
        logger.exception("RCA generation failed")
        # Graceful fallback report
        fallback = {
            "probable_root_causes": [
                {
                    "cause": "Mechanical failure / wear of component (inferred).",
                    "category": "Machine",
                    "confidence": "low",
                    "supporting_evidence": "Insufficient contextual evidence retrieved to run complete RCA."
                }
            ],
            "recommended_actions": [
                "Isolate equipment and perform manual check.",
                "Review OEM manual guidelines for troubleshooting."
            ],
            "similar_past_incidents": []
        }
        return {"rca_report": fallback, "error": str(exc)}


# --------------------------------------------------------------------------- #
# LangGraph Workflow Construction
# --------------------------------------------------------------------------- #
def build_rca_workflow() -> Any:
    """Build the LangGraph state machine workflow."""
    workflow = StateGraph(RCAState)
    
    # Add nodes
    workflow.add_node("extract_tag", extract_tag_node)
    workflow.add_node("fetch_graph_context", fetch_graph_context_node)
    workflow.add_node("fetch_vector_context", fetch_vector_context_node)
    workflow.add_node("generate_rca", generate_rca_node)
    
    # Set entry point
    workflow.set_entry_point("extract_tag")
    
    # Define edges
    workflow.add_edge("extract_tag", "fetch_graph_context")
    workflow.add_edge("fetch_graph_context", "fetch_vector_context")
    workflow.add_edge("fetch_vector_context", "generate_rca")
    workflow.add_edge("generate_rca", END)
    
    return workflow.compile()


# --------------------------------------------------------------------------- #
# Predictive Maintenance Risk Score (Heuristic v1)
# --------------------------------------------------------------------------- #
class MaintenancePredictor:
    """Predictive maintenance engine using Neo4j graph density heuristics."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def get_risk_score(self, tag: str) -> dict[str, Any]:
        """Compute a heuristic risk score based on history frequency in Neo4j.

        Returns:
            ``{score: int (0-100), level: str (low/medium/high), breakdown: list[str]}``
        """
        tag = tag.upper().strip()
        kg = KnowledgeGraph(self.settings)

        # Baseline defaults
        score = 10
        breakdown = ["Baseline health check."]
        
        if not kg.verify_connectivity():
            return {
                "score": score,
                "level": "low",
                "breakdown": breakdown + ["Neo4j offline; showing minimum risk default."]
            }

        try:
            with kg.driver.session() as session:
                # Count linked documents (past work orders, safety incident reports)
                doc_record = session.run(
                    """
                    MATCH (e:Equipment {tag: $tag})
                    OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
                    RETURN count(d) AS doc_count
                    """,
                    tag=tag
                )
                doc_count = doc_record.single()["doc_count"]

                # Count linked incidents
                inc_record = session.run(
                    """
                    MATCH (e:Equipment {tag: $tag})
                    OPTIONAL MATCH (e)-[:MENTIONED_IN]->(d:Document)
                    OPTIONAL MATCH (inc:Incident)-[:MENTIONED_IN]->(d)
                    RETURN count(DISTINCT inc) AS inc_count
                    """,
                    tag=tag
                )
                inc_count = inc_record.single()["inc_count"]

                # Check parameter count
                param_record = session.run(
                    """
                    MATCH (e:Equipment {tag: $tag})
                    OPTIONAL MATCH (p:Parameter)-[:MEASURED_FOR]->(e)
                    RETURN count(p) AS param_count
                    """,
                    tag=tag
                )
                param_count = param_record.single()["param_count"]

            # Heuristic calculation
            incident_weight = 25
            work_order_weight = 12
            parameter_weight = 5

            score += (inc_count * incident_weight)
            score += (max(0, doc_count - inc_count) * work_order_weight)
            score += (param_count * parameter_weight)
            
            # Clip between 0 and 100
            score = min(100, max(0, score))

            # Build breakdown
            if inc_count > 0:
                breakdown.append(f"{inc_count} past safety/equipment incident reports logged.")
            if doc_count > inc_count:
                breakdown.append(f"{doc_count - inc_count} past maintenance work orders / inspections registered.")
            if param_count > 0:
                breakdown.append(f"{param_count} active process parameters linked in graph.")
            if score > 70:
                breakdown.append("CRITICAL: Repeated failures require immediate structural alignment audit.")
            elif score > 35:
                breakdown.append("WARNING: Moderate maintenance frequency. Schedule next inspection soon.")
            else:
                breakdown.append("INFO: Equipment shows clean recent operating runs.")

        except Exception as exc:  # noqa: BLE001
            logger.warning("get_risk_score failed: %s", exc)
            breakdown.append(f"Error reading history: {exc}")

        # Resolve level
        if score > 70:
            level = "high"
        elif score > 30:
            level = "medium"
        else:
            level = "low"

        return {
            "score": score,
            "level": level,
            "breakdown": breakdown
        }


# --------------------------------------------------------------------------- #
# Module level instances
# --------------------------------------------------------------------------- #
rca_agent = build_rca_workflow()
maintenance_predictor = MaintenancePredictor()
