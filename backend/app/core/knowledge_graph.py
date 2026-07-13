"""Neo4j knowledge-graph operations.

Node labels
-----------
- ``Equipment``     keyed by tag (P-101A, V-203, …)
- ``Document``      keyed by document_id (filename-derived)
- ``Person``        keyed by name
- ``Procedure``     keyed by name (SOP / standard)
- ``Incident``      keyed by reference/id
- ``Parameter``     keyed by name+value (process parameters)
- ``Regulation``    keyed by reference (OISD-117, PESO, …)

Relationships
-------------
- ``(Equipment|Person|Procedure|Incident)-[:MENTIONED_IN]->(Document)``
- ``(Equipment)-[:MAINTAINED_BY]->(Person)``
- ``(Document)-[:REFERENCES]->(Regulation|Procedure)``
- ``(Parameter)-[:MEASURED_FOR]->(Equipment)``  (when both present)

All writes use ``MERGE`` (not ``CREATE``) so re-ingesting the same document is
**idempotent** — no duplicate nodes or edges.

The class is connection-safe: if Neo4j is unreachable or credentials are bad,
every method logs and returns a failure result instead of raising, so document
ingestion (vector store, etc.) still completes.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import Driver, GraphDatabase

from app.config import Settings, get_settings
from app.models.schemas import (
    Equipment,
    ExtractedEntities,
    GraphLinkResult,
    PIDSymbol,
    Person,
    ProcessParameter,
    RegulatoryReference,
)

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Thin, idempotent wrapper around the Neo4j driver for entity linking."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._driver: Driver | None = None

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    @property
    def driver(self) -> Driver:
        """Lazily create the Neo4j driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_username, self.settings.neo4j_password),
            )
        return self._driver

    def verify_connectivity(self) -> bool:
        """Return True if Neo4j is reachable, False otherwise (no raise)."""
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:  # noqa: BLE001
            logger.warning("Neo4j connectivity check failed.", exc_info=True)
            return False

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:  # noqa: BLE001
                logger.debug("Error closing Neo4j driver.", exc_info=True)
            finally:
                self._driver = None

    # ------------------------------------------------------------------ #
    # Public API — orchestrated entity linking
    # ------------------------------------------------------------------ #
    def link_entities(
        self,
        document_id: str,
        filename: str,
        entities: ExtractedEntities,
    ) -> GraphLinkResult:
        """Create/merge all nodes + relationships for one document.

        Args:
            document_id: Stable id (e.g. slug of filename + hash).
            filename: Display title for the Document node.
            entities: Output of :class:`EntityExtractor.extract`.

        Returns:
            :class:`GraphLinkResult` — ``linked=False`` if Neo4j was unreachable.
        """
        if not self.verify_connectivity():
            return GraphLinkResult(linked=False, error="Neo4j unreachable or credentials invalid")

        doc_type = entities.document_type.value if entities.document_type else "other"
        doc_title = entities.document_title or filename

        try:
            summary_counts = self._run_link_tx(
                document_id=document_id,
                doc_title=doc_title,
                doc_type=doc_type,
                entities=entities,
            )
            logger.info(
                "Graph link OK for '%s': %d nodes, %d relationships.",
                filename,
                summary_counts["nodes"],
                summary_counts["relationships"],
            )
            return GraphLinkResult(
                linked=True,
                nodes_created=summary_counts["nodes"],
                relationships_created=summary_counts["relationships"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to link entities for '%s'.", filename)
            return GraphLinkResult(linked=False, error=str(exc))

    # ------------------------------------------------------------------ #
    # Transaction
    # ------------------------------------------------------------------ #
    def _run_link_tx(
        self,
        document_id: str,
        doc_title: str,
        doc_type: str,
        entities: ExtractedEntities,
    ) -> dict[str, int]:
        """Run all merges in a single transaction; return counters.

        Returns ``{"nodes": n, "relationships": r}`` approximating work done
        (MERGE reports nodesCreated/relationshipsCreated via result.consume()
        summary counters, which we use here).
        """
        with self.driver.session() as session:
            result = session.execute_write(
                self._link_tx_body,
                document_id,
                doc_title,
                doc_type,
                entities,
            )
            return result

    @staticmethod
    def _link_tx_body(
        tx: Any,
        document_id: str,
        doc_title: str,
        doc_type: str,
        entities: ExtractedEntities,
    ) -> dict[str, int]:
        """The actual Cypher, executed inside a managed transaction.

        Uses ``UNWIND`` to batch-merge each entity list and create relationships
        back to the Document node. ``MERGE`` everywhere keeps it idempotent.
        """

        # 1. Document node -------------------------------------------------
        tx.run(
            """
            MERGE (d:Document {id: $document_id})
            SET d.title  = $doc_title,
                d.type   = $doc_type,
                d.summary = $summary,
                d.ingested_at = timestamp()
            """,
            document_id=document_id,
            doc_title=doc_title,
            doc_type=doc_type,
            summary=entities.summary,
        )

        # 2. Equipment -----------------------------------------------------
        tx.run(
            """
            UNWIND $rows AS row
            MERGE (e:Equipment {tag: row.tag})
              SET e.type = coalesce(row.equipment_type, e.type),
                  e.description = coalesce(row.description, e.description)
            MERGE (e)-[:MENTIONED_IN]->(d:Document {id: $document_id})
            """,
            rows=[
                {
                    "tag": eq.tag,
                    "equipment_type": eq.equipment_type,
                    "description": eq.description,
                }
                for eq in entities.equipment
            ],
            document_id=document_id,
        )

        # 3. Persons -------------------------------------------------------
        tx.run(
            """
            UNWIND $rows AS row
            MERGE (p:Person {name: row.name})
              SET p.role = coalesce(row.role, p.role)
            MERGE (p)-[:MENTIONED_IN]->(d:Document {id: $document_id})
            """,
            rows=[{"name": p.name, "role": p.role} for p in entities.persons],
            document_id=document_id,
        )

        # 4. Procedures ----------------------------------------------------
        tx.run(
            """
            UNWIND $names AS name
            MERGE (pr:Procedure {name: name})
            MERGE (d:Document {id: $document_id})-[:REFERENCES]->(pr)
            """,
            names=list(entities.procedures),
            document_id=document_id,
        )

        # 5. Incidents -----------------------------------------------------
        tx.run(
            """
            UNWIND $refs AS ref
            MERGE (inc:Incident {ref: ref})
            MERGE (inc)-[:MENTIONED_IN]->(d:Document {id: $document_id})
            """,
            refs=list(entities.incidents),
            document_id=document_id,
        )

        # 6. Regulatory references ----------------------------------------
        tx.run(
            """
            UNWIND $rows AS row
            MERGE (rg:Regulation {reference: row.reference})
              SET rg.description = coalesce(row.description, rg.description)
            MERGE (d:Document {id: $document_id})-[:REFERENCES]->(rg)
            """,
            rows=[
                {"reference": r.reference, "description": r.description}
                for r in entities.regulatory_references
            ],
            document_id=document_id,
        )

        # 7. Process parameters -------------------------------------------
        tx.run(
            """
            UNWIND $rows AS row
            MERGE (pa:Parameter {name: row.name, value: row.value})
              SET pa.unit = coalesce(row.unit, pa.unit)
            MERGE (pa)-[:MENTIONED_IN]->(d:Document {id: $document_id})
            """,
            rows=[
                {"name": p.name, "value": p.value or "", "unit": p.unit}
                for p in entities.parameters
            ],
            document_id=document_id,
        )

        # 8. Cross-link: equipment <-> maintainer when names co-occur -----
        # We can't infer pairing reliably from free text, so we link every
        # person whose role mentions 'maint'/'engineer'/'technician' to every
        # equipment only when a single equipment exists (safe, meaningful).
        if len(entities.equipment) == 1 and entities.persons:
            tx.run(
                """
                MATCH (e:Equipment {tag: $tag}), (p:Person)
                WHERE p.name IN $names
                  AND (toLower(p.role) CONTAINS 'maint'
                       OR toLower(p.role) CONTAINS 'engineer'
                       OR toLower(p.role) CONTAINS 'technician')
                MERGE (e)-[:MAINTAINED_BY]->(p)
                """,
                tag=entities.equipment[0].tag,
                names=[p.name for p in entities.persons],
            )

        # 9. Cross-link: parameters to the single equipment ---------------
        if len(entities.equipment) == 1 and entities.parameters:
            tx.run(
                """
                MATCH (e:Equipment {tag: $tag}), (pa:Parameter)
                WHERE pa.name IN $names
                MERGE (pa)-[:MEASURED_FOR]->(e)
                """,
                tag=entities.equipment[0].tag,
                names=[p.name for p in entities.parameters],
            )

        # Read back counts so the caller can report something meaningful.
        counter = tx.run(
            """
            MATCH (d:Document {id: $document_id})-[r]-(n)
            RETURN count(DISTINCT n) AS nodes, count(r) AS rels
            """,
            document_id=document_id,
        ).single()
        if counter:
            return {"nodes": counter["nodes"], "relationships": counter["rels"]}
        return {"nodes": 0, "relationships": 0}

    # ------------------------------------------------------------------ #
    # P&ID vision (Phase 3) — link detected symbols/tags into the graph
    # ------------------------------------------------------------------ #
    def link_pid_symbols(
        self,
        document_id: str,
        filename: str,
        symbols: list[PIDSymbol],
    ) -> GraphLinkResult:
        """Create/merge a P&ID ``Document`` node plus ``Equipment`` nodes for
        every symbol that has an OCR'd tag, linked ``APPEARS_ON`` the diagram.

        Symbols without a readable tag (OCR failed or no tag nearby) are
        counted but not written as graph nodes — a tagless shape carries no
        stable identity to merge on. This keeps the graph free of throwaway
        "unknown" equipment nodes while still reporting drawing-level symbol
        counts back to the caller via ``entities_detected``.

        Uses ``MERGE`` throughout, so re-analyzing the same P&ID is
        idempotent — no duplicate Equipment or Document nodes.
        """
        if not self.verify_connectivity():
            return GraphLinkResult(linked=False, error="Neo4j unreachable or credentials invalid")

        tagged = [s for s in symbols if s.nearby_tag_text]

        try:
            with self.driver.session() as session:
                counts = session.execute_write(
                    self._link_pid_tx, document_id, filename, tagged
                )
            logger.info(
                "P&ID graph link OK for '%s': %d equipment tags linked.",
                filename,
                counts["equipment"],
            )
            return GraphLinkResult(
                linked=True,
                nodes_created=counts["equipment"] + 1,  # +1 for the Document node
                relationships_created=counts["equipment"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to link P&ID symbols for '%s'.", filename)
            return GraphLinkResult(linked=False, error=str(exc))

    @staticmethod
    def _link_pid_tx(tx: Any, document_id: str, filename: str, tagged: list[PIDSymbol]) -> dict[str, int]:
        tx.run(
            """
            MERGE (d:Document {id: $document_id})
            SET d.title = $filename,
                d.type  = 'P&ID',
                d.ingested_at = timestamp()
            """,
            document_id=document_id,
            filename=filename,
        )

        tx.run(
            """
            UNWIND $rows AS row
            MERGE (e:Equipment {tag: row.tag})
              SET e.type = coalesce(e.type, row.symbol_type)
            MERGE (e)-[r:APPEARS_ON]->(d:Document {id: $document_id})
              SET r.confidence = row.confidence,
                  r.symbol_type = row.symbol_type
            """,
            rows=[
                {
                    "tag": s.nearby_tag_text,
                    "symbol_type": s.symbol_type.value,
                    "confidence": s.confidence,
                }
                for s in tagged
            ],
            document_id=document_id,
        )

        return {"equipment": len({s.nearby_tag_text for s in tagged})}

    # ------------------------------------------------------------------ #
    # Diagnostic query (handy for manual testing)
    # ------------------------------------------------------------------ #
    def count_nodes(self) -> dict[str, int]:
        """Return ``{label: count}`` for every node label in the graph."""
        if not self.verify_connectivity():
            return {}
        try:
            with self.driver.session() as session:
                records = session.run(
                    "MATCH (n) UNWIND labels(n) AS lbl "
                    "RETURN lbl, count(*) AS c ORDER BY lbl"
                )
                return {r["lbl"]: r["c"] for r in records}
        except Exception:  # noqa: BLE001
            logger.warning("count_nodes failed.", exc_info=True)
            return {}

    # ------------------------------------------------------------------ #
    # RAG support (Phase 2) — entities related to a set of retrieved documents
    # ------------------------------------------------------------------ #
    def get_related_entities(
        self, document_ids: list[str], limit: int = 15
    ) -> list[dict[str, str | None]]:
        """Find graph entities connected to the given document ids.

        Used by the RAG engine to enrich vector-retrieved context with
        structured facts (equipment, people, regulations, procedures) that
        the chunk text alone might not surface clearly.

        Args:
            document_ids: ``document_id`` values from the vector store's top-k
                retrieval results (deduplicated by the caller is fine either way).
            limit: Max number of related entities to return.

        Returns:
            A list of ``{label, value, relationship}`` dicts. Empty list (not
            an error) if Neo4j is unreachable or nothing is connected — RAG
            should degrade gracefully to vector-only context.
        """
        if not document_ids or not self.verify_connectivity():
            return []

        try:
            with self.driver.session() as session:
                records = session.run(
                    """
                    MATCH (d:Document)
                    WHERE d.id IN $document_ids
                    MATCH (n)-[r]-(d)
                    WHERE n:Equipment OR n:Person OR n:Regulation
                       OR n:Procedure OR n:Incident OR n:Parameter
                    RETURN DISTINCT labels(n)[0] AS label,
                           coalesce(n.tag, n.name, n.reference, n.ref, n.value) AS value,
                           type(r) AS relationship
                    LIMIT $limit
                    """,
                    document_ids=document_ids,
                    limit=limit,
                )
                return [
                    {
                        "label": r["label"],
                        "value": r["value"],
                        "relationship": r["relationship"],
                    }
                    for r in records
                    if r["value"] is not None
                ]
        except Exception:  # noqa: BLE001
            logger.warning("get_related_entities failed.", exc_info=True)
            return []


# Module-level convenience instance.
graph = KnowledgeGraph()
