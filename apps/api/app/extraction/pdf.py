from __future__ import annotations

import fitz

from app.extraction.text import normalize_text
from app.extraction.types import ExtractedDocument, ExtractedSection


def extract_pdf(
    data: bytes, *, max_pages: int = 1000, max_chars: int = 2_000_000
) -> ExtractedDocument:
    if not data.startswith(b"%PDF-"):
        raise ValueError("Uploaded file is not a PDF")
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF is corrupt or unsupported") from exc
    try:
        if document.needs_pass:
            raise ValueError("Encrypted PDFs are not supported")
        page_count = document.page_count
        if page_count > max_pages:
            raise ValueError("PDF exceeds the configured page limit")
        warnings: list[str] = []
        sections: list[ExtractedSection] = []
        pages: list[str] = []
        extracted_chars = 0
        for index, page in enumerate(document):
            page_text = normalize_text(page.get_text("text"))
            extracted_chars += len(page_text)
            if extracted_chars > max_chars:
                raise ValueError("PDF extracted text exceeds the configured size limit")
            pages.append(page_text)
            if not page_text:
                warnings.append(
                    f"Page {index + 1} appears image-only or contains no extractable text."
                )
            else:
                sections.append(ExtractedSection(page_text, page_number=index + 1))
        metadata = {key: value for key, value in document.metadata.items() if value}
    finally:
        document.close()
    title = metadata.get("title") or None
    author = metadata.get("author") or None
    raw = "\n\n".join(pages)
    return ExtractedDocument(
        raw_text=raw,
        normalized_text=raw,
        method="pymupdf/text",
        sections=sections,
        title=title,
        author=author,
        page_count=page_count,
        warnings=warnings,
        metadata=metadata,
    )
