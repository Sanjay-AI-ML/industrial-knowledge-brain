"""ChromaDB vector store for RAG retrieval.

Responsibilities
----------------
* Maintain a persistent ChromaDB collection (``PersistentClient``).
* Chunk document text with LangChain's ``RecursiveCharacterTextSplitter``.
* Embed + upsert chunks for a document with deterministic ids
  (``{document_id}_chunk_{i}``) so re-ingestion is idempotent.
* Expose a ``query()`` helper for later RAG phases.

Embeddings use ChromaDB's built-in ``DefaultEmbeddingFunction`` (the
``all-MiniLM-L6-v2`` ONNX model) — no external embedding API key needed. The
model (~79 MB) is downloaded on first use and cached locally.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import Settings, get_settings
from app.models.schemas import VectorStoreResult

logger = logging.getLogger(__name__)


class VectorStore:
    """Persistent ChromaDB-backed vector store."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: chromadb.api.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    @property
    def client(self) -> chromadb.api.ClientAPI:
        """Lazily create the persistent ChromaDB client."""
        if self._client is None:
            path = self.settings.chroma_path  # ensures dir exists
            logger.info("Opening ChromaDB persistent client at %s", path)
            self._client = chromadb.PersistentClient(
                path=str(path),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self) -> chromadb.Collection:
        """Get-or-create the documents collection with the default embedder."""
        if self._collection is None:
            ef = embedding_functions.DefaultEmbeddingFunction()
            self._collection = self.client.get_or_create_collection(
                name=self.settings.chroma_collection_name,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def add_document(
        self,
        document_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> VectorStoreResult:
        """Chunk ``text``, embed, and upsert into ChromaDB.

        Args:
            document_id: Stable document id; used to build chunk ids.
            text: Full document text (concatenated pages).
            metadata: Stored on every chunk (e.g. filename, doc_type, source).

        Returns:
            :class:`VectorStoreResult` with the chunk count, or
            ``stored=False`` + error on failure.
        """
        if not text or not text.strip():
            logger.info("Vector store: no text for '%s'; nothing to embed.", document_id)
            return VectorStoreResult(stored=True, chunks_embedded=0)

        chunks = self._split(text)
        if not chunks:
            return VectorStoreResult(stored=True, chunks_embedded=0)

        base_meta = self._clean_metadata(metadata or {})
        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {**base_meta, "chunk_index": i, "document_id": document_id}
            for i in range(len(chunks))
        ]

        try:
            self.collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ChromaDB upsert failed for '%s'.", document_id)
            return VectorStoreResult(stored=False, error=str(exc))

        logger.info(
            "Stored %d chunks for document '%s' in ChromaDB.", len(chunks), document_id
        )
        return VectorStoreResult(stored=True, chunks_embedded=len(chunks))

    def query(
        self,
        text: str,
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search over the collection (used by the RAG engine later).

        Args:
            text: Query text.
            k: Number of nearest neighbours to return.
            where: Optional Chroma metadata filter.

        Returns:
            A list of ``{document_id, chunk_index, text, metadata, distance}``.
        """
        try:
            res = self.collection.query(
                query_texts=[text],
                n_results=k,
                where=where,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("ChromaDB query failed.")
            return [{"error": str(exc)}]

        documents = (res.get("documents") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        out: list[dict[str, Any]] = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            out.append(
                {
                    "document_id": meta.get("document_id"),
                    "chunk_index": meta.get("chunk_index"),
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                }
            )
        return out

    def count(self) -> int:
        """Total number of chunks in the collection."""
        try:
            return self.collection.count()
        except Exception:  # noqa: BLE001
            logger.warning("ChromaDB count failed.", exc_info=True)
            return -1

    def delete_document(self, document_id: str) -> bool:
        """Delete all chunks belonging to ``document_id``."""
        try:
            self.collection.delete(where={"document_id": document_id})
            return True
        except Exception:  # noqa: BLE001
            logger.warning("delete_document failed for '%s'.", document_id, exc_info=True)
            return False

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _split(self, text: str) -> list[str]:
        """Split text into chunks, stripping empty fragments."""
        chunks = self._splitter.split_text(text)
        return [c.strip() for c in chunks if c and c.strip()]

    @staticmethod
    def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        """Ensure metadata values are ChromaDB-compatible (str/int/float/bool).

        ChromaDB rejects None and nested structures; coerce defensively.
        """
        clean: dict[str, Any] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                clean[key] = value
            else:
                clean[key] = str(value)
        return clean


def generate_document_id(filename: str) -> str:
    """Build a stable document id from filename (falls back to a uuid)."""
    import re

    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", filename).strip("_").lower()
    if not slug:
        slug = uuid4().hex
    return f"{slug}_{uuid4().hex[:8]}"


# Module-level convenience instance.
store = VectorStore()
