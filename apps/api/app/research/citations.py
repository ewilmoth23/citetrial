from __future__ import annotations

import re

from app.schemas.source import SearchResult

CITATION_PATTERN = re.compile(r"\[\s*Source\s+(\d+)(?:\s*,\s*[^\]\n]+)?\s*\]", re.IGNORECASE)
BRACKET_PATTERN = re.compile(r"\[[^\]\n]{0,160}\]")
QUOTATION_PATTERN = re.compile(r'[“"]([^”"\n]{3,500})[”"]')


def citation_marker(index: int, result: SearchResult) -> str:
    if result.location.page_number:
        return f"[Source {index}, p. {result.location.page_number}]"
    if result.location.heading_path:
        return f"[Source {index}, “{result.location.heading_path}”]"
    return f"[Source {index}]"


def validate_citation_markers(answer: str, results: list[SearchResult]) -> tuple[str, list[str]]:
    warnings: list[str] = []

    def replace(match: re.Match[str]) -> str:
        candidate = match.group(0)
        supported = CITATION_PATTERN.fullmatch(candidate)
        if not supported:
            if re.search(r"\bsource\b", candidate, re.IGNORECASE):
                warnings.append(f"Removed unsupported citation marker: {candidate[:80]}")
                return "[unsupported citation removed]"
            return candidate
        index = int(supported.group(1))
        if index < 1 or index > len(results):
            warnings.append(f"Removed unsupported citation marker for Source {index}.")
            return "[unsupported citation removed]"
        return citation_marker(index, results[index - 1])

    return BRACKET_PATTERN.sub(replace, answer), warnings


def citation_indices(answer: str) -> set[int]:
    return {int(match.group(1)) for match in CITATION_PATTERN.finditer(answer)}


def verify_quotation(quotation: str, stored_text: str) -> bool:
    normalized_quotation = " ".join(quotation.split())
    if not normalized_quotation:
        return False
    normalized_stored_text = " ".join(stored_text.split())
    return normalized_quotation in normalized_stored_text


def sanitize_quotations(answer: str, stored_excerpts: list[str]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    citation_spans = [match.span() for match in CITATION_PATTERN.finditer(answer)]

    def replace(match: re.Match[str]) -> str:
        if any(start <= match.start() and match.end() <= end for start, end in citation_spans):
            return match.group(0)
        quotation = match.group(1)
        if not any(verify_quotation(quotation, excerpt) for excerpt in stored_excerpts):
            warnings.append(f"Removed quotation marks from unmatched model text: {quotation[:80]}")
            return quotation
        return match.group(0)

    return QUOTATION_PATTERN.sub(replace, answer), warnings


def validate_quotations(answer: str, stored_excerpts: list[str]) -> list[str]:
    return sanitize_quotations(answer, stored_excerpts)[1]
