"""
ChromaDB wrapper.

Uses a single persistent collection for all documents.
Per-document filtering is done via the `document_id` metadata field.

ChromaDB's client is synchronous — callers in async contexts must wrap
calls in asyncio.to_thread().
"""
from __future__ import annotations

import logging

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.schemas import ChunkData

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=settings.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB collection '%s' ready (%d chunks stored)",
            settings.CHROMA_COLLECTION_NAME,
            self._collection.count(),
        )

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_chunks(self, chunks: list[ChunkData], embeddings: list[list[float]]) -> None:
        """Store chunks and their embeddings. Skips if list is empty."""
        if not chunks:
            return

        self._collection.add(
            ids=[f"{c.document_id}_{c.chunk_index}" for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "document_id": c.document_id,
                    "document_name": c.metadata.get("document_name", ""),
                    "page_number": c.page_number,
                    "chunk_index": c.chunk_index,
                }
                for c in chunks
            ],
        )

    def delete_document(self, document_id: str) -> None:
        """Remove all chunks belonging to a document."""
        self._collection.delete(where={"document_id": document_id})

    # ── Read ──────────────────────────────────────────────────────────────────

    def query(
        self,
        embedding: list[float],
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[dict]:
        """Return the top-k most similar chunks.

        Args:
            embedding: Query vector.
            top_k: Number of results to return.
            document_ids: If provided, restrict search to these documents.

        Returns:
            List of dicts with keys: text, document_id, document_name,
            page_number, distance.
        """
        total = self._collection.count()
        if total == 0:
            return []

        n_results = min(top_k, total)

        where: dict | None = None
        if document_ids:
            if len(document_ids) == 1:
                where = {"document_id": document_ids[0]}
            else:
                where = {"document_id": {"$in": document_ids}}

        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = results["ids"][0]
        if not ids:
            return []

        return [
            {
                "text": results["documents"][0][i],
                "document_id": results["metadatas"][0][i]["document_id"],
                "document_name": results["metadatas"][0][i]["document_name"],
                "page_number": results["metadatas"][0][i]["page_number"],
                "distance": results["distances"][0][i],
            }
            for i in range(len(ids))
        ]

    def count_chunks(self, document_id: str) -> int:
        result = self._collection.get(where={"document_id": document_id}, include=[])
        return len(result["ids"])


# Module-level singleton.
vector_store = VectorStore()
