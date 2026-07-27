from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.extraction.types import ExtractedSection

Opcode = tuple[str, int, int, int, int]


@dataclass(frozen=True)
class CorrectionAlignment:
    sections: list[ExtractedSection]
    method: str
    confidence: float
    location_status: str
    warnings: list[str]


def _section_spans(text: str, sections: list[ExtractedSection]) -> list[tuple[int, int]] | None:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for section in sections:
        start = text.find(section.content, cursor)
        if start < 0:
            return None
        end = start + len(section.content)
        spans.append((start, end))
        cursor = end
    return spans


def _map_from_opcodes(
    position: int,
    old_length: int,
    new_length: int,
    opcodes: list[Opcode],
) -> int:
    if position <= 0:
        return 0
    if position >= old_length:
        return new_length
    for tag, old_start, old_end, new_start, new_end in opcodes:
        if tag == "insert" and old_start == position:
            return new_end
        if old_start <= position <= old_end and old_end > old_start:
            if tag == "equal":
                return new_start + min(position - old_start, new_end - new_start)
            fraction = (position - old_start) / (old_end - old_start)
            return round(new_start + fraction * (new_end - new_start))
    return round(position / old_length * new_length)


def _alignment_opcodes(previous_text: str, corrected_text: str) -> tuple[list[Opcode], float, str]:
    if max(len(previous_text), len(corrected_text)) <= 20_000:
        matcher = SequenceMatcher(None, previous_text, corrected_text, autojunk=False)
        opcodes: list[Opcode] = [
            (str(tag), old_start, old_end, new_start, new_end)
            for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes()
        ]
        return opcodes, matcher.ratio(), "character-sequence-v1"

    previous_lines = previous_text.splitlines(keepends=True) or [previous_text]
    corrected_lines = corrected_text.splitlines(keepends=True) or [corrected_text]
    matcher = SequenceMatcher(None, previous_lines, corrected_lines, autojunk=True)
    previous_offsets = [0]
    corrected_offsets = [0]
    for line in previous_lines:
        previous_offsets.append(previous_offsets[-1] + len(line))
    for line in corrected_lines:
        corrected_offsets.append(corrected_offsets[-1] + len(line))

    char_opcodes: list[Opcode] = []
    matched_equivalent = 0.0
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        old_char_start = previous_offsets[old_start]
        old_char_end = previous_offsets[old_end]
        new_char_start = corrected_offsets[new_start]
        new_char_end = corrected_offsets[new_end]
        old_block = previous_text[old_char_start:old_char_end]
        new_block = corrected_text[new_char_start:new_char_end]
        if tag == "equal":
            matched_equivalent += len(old_block)
            char_opcodes.append((tag, old_char_start, old_char_end, new_char_start, new_char_end))
            continue
        if tag == "replace" and max(len(old_block), len(new_block)) <= 20_000:
            local = SequenceMatcher(None, old_block, new_block, autojunk=False)
            matched_equivalent += local.ratio() * max(len(old_block), len(new_block))
            char_opcodes.extend(
                (
                    local_tag,
                    old_char_start + local_old_start,
                    old_char_start + local_old_end,
                    new_char_start + local_new_start,
                    new_char_start + local_new_end,
                )
                for local_tag, local_old_start, local_old_end, local_new_start, local_new_end in local.get_opcodes()
            )
            continue
        char_opcodes.append((tag, old_char_start, old_char_end, new_char_start, new_char_end))

    denominator = max(len(previous_text), len(corrected_text), 1)
    confidence = min(1.0, matched_equivalent / denominator)
    return char_opcodes, confidence, "line-and-character-sequence-v1"


def _corrected_line_range(text: str, start: int, content: str) -> tuple[int, int]:
    line_start = text[:start].count("\n") + 1
    return line_start, line_start + content.count("\n")


def align_pdf_correction(
    previous_text: str,
    corrected_text: str,
    previous_sections: list[ExtractedSection],
) -> CorrectionAlignment:
    spans = _section_spans(previous_text, previous_sections)
    if not spans:
        return CorrectionAlignment(
            sections=[ExtractedSection(corrected_text)],
            method="unmapped-v1",
            confidence=0.0,
            location_status="unmapped",
            warnings=[
                "Original PDF section boundaries could not be recovered; corrected chunks have no page location."
            ],
        )

    opcodes, confidence, method = _alignment_opcodes(previous_text, corrected_text)
    if confidence < 0.75:
        return CorrectionAlignment(
            sections=[ExtractedSection(corrected_text)],
            method=method,
            confidence=round(confidence, 4),
            location_status="unmapped",
            warnings=[
                "The correction changed too much text to map reliably to the original PDF pages; corrected chunks have no page location."
            ],
        )

    old_boundaries = [0]
    for left, right in zip(spans, spans[1:], strict=False):
        old_boundaries.append(left[1] + (right[0] - left[1]) // 2)
    old_boundaries.append(len(previous_text))
    new_boundaries = [
        _map_from_opcodes(
            boundary,
            len(previous_text),
            len(corrected_text),
            opcodes,
        )
        for boundary in old_boundaries
    ]
    new_boundaries[0] = 0
    new_boundaries[-1] = len(corrected_text)
    for index in range(1, len(new_boundaries)):
        new_boundaries[index] = max(new_boundaries[index - 1], new_boundaries[index])

    corrected_sections: list[ExtractedSection] = []
    for index, previous_section in enumerate(previous_sections):
        raw_slice = corrected_text[new_boundaries[index] : new_boundaries[index + 1]]
        leading = len(raw_slice) - len(raw_slice.lstrip())
        content = raw_slice.strip()
        content_start = new_boundaries[index] + leading
        line_start, line_end = _corrected_line_range(corrected_text, content_start, content)
        corrected_sections.append(
            ExtractedSection(
                content=content,
                heading_path=previous_section.heading_path,
                page_number=previous_section.page_number,
                line_start=line_start if previous_section.line_start is not None else None,
                line_end=line_end if previous_section.line_end is not None else None,
            )
        )

    return CorrectionAlignment(
        sections=corrected_sections,
        method=method,
        confidence=round(confidence, 4),
        location_status="aligned",
        warnings=[
            f"Corrected PDF text was aligned to original page boundaries with confidence {confidence:.3f}; page assignments remain reviewable provenance, not a claim about document truth."
        ],
    )
