"""
Text chunking with sliding window and sentence-boundary preference.

Chunks each document segment independently so page attribution is always accurate.
"""
from __future__ import annotations

from app.schemas import ChunkData


def chunk_segments(
    segments: list[dict],
    document_id: str,
    document_name: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[ChunkData]:
    """Split parsed document segments into overlapping chunks.

    Args:
        segments: Output of document_parser.parse_document() —
                  list of {text: str, page_number: int}.
        document_id: UUID of the parent Document row.
        document_name: Original filename — stored in chunk metadata for citations.
        chunk_size: Maximum characters per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        Ordered list of ChunkData objects ready for embedding.
    """
    chunks: list[ChunkData] = []
    chunk_idx = 0

    for segment in segments:
        text = segment["text"].strip()
        page_num = segment["page_number"]

        if not text:
            continue

        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))

            # Prefer to break at a sentence or word boundary
            if end < len(text):
                for sep in (". ", ".\n", "\n\n", "\n", " "):
                    break_at = text.rfind(sep, start + chunk_size // 2, end)
                    if break_at > start:
                        end = break_at + len(sep)
                        break

            chunk_text = text[start:end].strip()

            # Skip very short trailing fragments
            if len(chunk_text) > 20:
                chunks.append(
                    ChunkData(
                        document_id=document_id,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                        page_number=page_num,
                        metadata={"document_name": document_name},
                    )
                )
                chunk_idx += 1

            next_start = end - overlap
            # Guard against infinite loop on very short segments
            if next_start <= start:
                start = end
            else:
                start = next_start

    return chunks
