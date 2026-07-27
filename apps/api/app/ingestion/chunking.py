from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.extraction.types import ExtractedSection


@dataclass(frozen=True)
class ChunkData:
    content: str
    content_hash: str
    char_start: int | None
    char_end: int | None
    page_number: int | None
    heading_path: str | None
    line_start: int | None
    line_end: int | None


def chunk_sections(sections: list[ExtractedSection], size: int, overlap: int) -> list[ChunkData]:
    if size < 100 or overlap < 0 or overlap >= size:
        raise ValueError("Invalid chunk size or overlap")
    chunks: list[ChunkData] = []
    occurrences: dict[str, int] = {}
    for section in sections:
        content = section.content.strip()
        start = 0
        while start < len(content):
            tentative_end = min(start + size, len(content))
            end = tentative_end
            if tentative_end < len(content):
                boundary = max(
                    content.rfind("\n\n", start, tentative_end),
                    content.rfind(". ", start, tentative_end),
                )
                if boundary > start + size // 2:
                    end = boundary + (0 if content[boundary : boundary + 2] == "\n\n" else 1)
            text = content[start:end].strip()
            base_digest = hashlib.sha256(text.encode()).hexdigest()
            occurrence = occurrences.get(base_digest, 0)
            digest = (
                base_digest
                if occurrence == 0
                else hashlib.sha256(f"{base_digest}:{occurrence}".encode()).hexdigest()
            )
            if text:
                chunks.append(
                    ChunkData(
                        text,
                        digest,
                        start,
                        end,
                        section.page_number,
                        section.heading_path,
                        section.line_start,
                        section.line_end,
                    )
                )
                occurrences[base_digest] = occurrence + 1
            if end >= len(content):
                break
            start = max(start + 1, end - overlap)
    return chunks
