from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ExtractedSection:
    content: str
    heading_path: str | None = None
    page_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class ExtractedDocument:
    raw_text: str
    normalized_text: str
    method: str
    sections: list[ExtractedSection]
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    publication_date: date | None = None
    publication_date_is_explicit: bool = False
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
