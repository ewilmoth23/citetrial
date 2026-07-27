from __future__ import annotations

import re

from charset_normalizer import from_bytes

from app.extraction.types import ExtractedDocument, ExtractedSection


def decode_text(data: bytes) -> tuple[str, list[str]]:
    warnings: list[str] = []
    result = from_bytes(data).best()
    if result is None:
        raise ValueError("Text encoding could not be detected")
    text = str(result)
    if result.chaos > 0.2:
        warnings.append("The file encoding was ambiguous; inspect the extracted text.")
    return text, warnings


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.splitlines()]
    normalized = "\n".join(lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def extract_plain_text(data: bytes) -> ExtractedDocument:
    raw, warnings = decode_text(data)
    normalized = normalize_text(raw)
    if not normalized:
        warnings.append("No searchable text was found.")
    sections: list[ExtractedSection] = []
    search_from = 0
    for _index, paragraph in enumerate(re.split(r"\n\s*\n", normalized)):
        if not paragraph.strip():
            continue
        prefix = normalized.find(paragraph, search_from)
        if prefix < 0:
            prefix = search_from
        search_from = prefix + len(paragraph)
        line_start = normalized[:prefix].count("\n") + 1
        sections.append(
            ExtractedSection(
                content=paragraph.strip(),
                line_start=line_start,
                line_end=line_start + paragraph.count("\n"),
            )
        )
    return ExtractedDocument(
        raw, normalized, "charset-normalizer/plain-text", sections, warnings=warnings
    )


def extract_markdown(data: bytes) -> ExtractedDocument:
    raw, warnings = decode_text(data)
    normalized = normalize_text(raw)
    sections: list[ExtractedSection] = []
    heading_stack: list[str] = []
    buffer: list[str] = []
    start_line = 1

    def flush(end_line: int) -> None:
        nonlocal buffer
        content = "\n".join(buffer).strip()
        if content:
            sections.append(
                ExtractedSection(
                    content=content,
                    heading_path=" › ".join(heading_stack) or None,
                    line_start=start_line,
                    line_end=end_line,
                )
            )
        buffer = []

    for line_number, line in enumerate(normalized.splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*$", line)
        if match:
            flush(line_number - 1)
            level = len(match.group(1))
            heading_stack[level - 1 :] = [match.group(2).strip()]
            start_line = line_number + 1
        else:
            if not buffer:
                start_line = line_number
            buffer.append(line)
    flush(len(normalized.splitlines()))
    title = heading_stack[0] if heading_stack else None
    return ExtractedDocument(
        raw, normalized, "markdown/line-preserving", sections, title=title, warnings=warnings
    )
