from __future__ import annotations

import contextlib
import re
from datetime import date

import dateparser
import trafilatura
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes

from app.extraction.text import normalize_text
from app.extraction.types import ExtractedDocument, ExtractedSection


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        content = tag.get("content") if tag else None
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def _explicit_date(value: str | None) -> date | None:
    if not value:
        return None
    parsed = dateparser.parse(
        value, settings={"STRICT_PARSING": True, "RETURN_AS_TIMEZONE_AWARE": True}
    )
    return parsed.date() if parsed else None


def extract_webpage(
    data: bytes, *, encoding: str | None = None, max_chars: int = 2_000_000
) -> ExtractedDocument:
    decoded = None
    if encoding:
        with contextlib.suppress(LookupError, UnicodeDecodeError):
            decoded = data.decode(encoding, errors="strict")
    if decoded is None:
        best = from_bytes(data).best()
        if best is None:
            raise ValueError("Webpage encoding could not be detected")
        decoded = str(best)
    soup = BeautifulSoup(decoded, "html.parser")
    for node in soup(
        ["script", "style", "noscript", "template", "iframe", "object", "embed", "form"]
    ):
        node.decompose()
    title = _meta(soup, "og:title", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True) or None
    author = _meta(soup, "author", "article:author")
    publisher = _meta(soup, "og:site_name", "application-name")
    date_text = _meta(soup, "article:published_time", "datePublished", "date", "pubdate")
    publication_date = _explicit_date(date_text)
    warnings: list[str] = []

    extracted = trafilatura.extract(
        decoded,
        include_comments=False,
        include_tables=True,
        include_links=True,
        include_formatting=True,
        favor_precision=True,
        output_format="markdown",
    )
    method = "trafilatura/markdown"
    if not extracted:
        main = soup.find("main") or soup.find("article") or soup.body
        extracted = main.get_text("\n", strip=True) if main else ""
        method = "beautifulsoup/fallback"
        warnings.append("Primary-content extraction fell back to a broad text selection.")
    normalized = normalize_text(extracted)[:max_chars]
    if len(extracted) > max_chars:
        warnings.append("Extracted text was truncated at the configured maximum size.")
    if not normalized:
        warnings.append("No primary text content was extracted.")
    sections: list[ExtractedSection] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        content = "\n".join(buffer).strip()
        if content:
            sections.append(ExtractedSection(content=content, heading_path=heading))
        buffer = []

    for line in normalized.splitlines():
        match = re.match(r"^#{1,6}\s+(.+)$", line)
        if match:
            flush()
            heading = match.group(1).strip()
        else:
            buffer.append(line)
    flush()
    if not sections and normalized:
        sections.append(ExtractedSection(normalized))
    return ExtractedDocument(
        raw_text=decoded[:max_chars],
        normalized_text=normalized,
        method=method,
        sections=sections,
        title=title,
        author=author,
        publisher=publisher,
        publication_date=publication_date,
        publication_date_is_explicit=publication_date is not None,
        warnings=warnings,
    )
