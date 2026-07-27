from __future__ import annotations

from app.extraction.types import ExtractedSection
from app.ingestion.corrections import align_pdf_correction


def test_minor_pdf_correction_retains_page_lineage() -> None:
    previous_sections = [
        ExtractedSection(
            content="Page one recorded 8,240 weekday boardings.",
            page_number=1,
        ),
        ExtractedSection(
            content="Page two recorded 410 weekend boardings.",
            page_number=2,
        ),
    ]
    previous_text = "\n\n".join(section.content for section in previous_sections)
    corrected_text = previous_text.replace("8,240", "8,241")

    alignment = align_pdf_correction(previous_text, corrected_text, previous_sections)

    assert alignment.location_status == "aligned"
    assert alignment.confidence > 0.95
    assert [section.page_number for section in alignment.sections] == [1, 2]
    assert "8,241" in alignment.sections[0].content
    assert "weekend boardings" in alignment.sections[1].content
    assert any("aligned to original page boundaries" in item for item in alignment.warnings)


def test_radical_pdf_replacement_drops_unreliable_page_assignments() -> None:
    previous_sections = [
        ExtractedSection(content="Original first-page evidence.", page_number=1),
        ExtractedSection(content="Original second-page evidence.", page_number=2),
    ]
    previous_text = "\n\n".join(section.content for section in previous_sections)
    corrected_text = "A wholly unrelated replacement with no recoverable page structure."

    alignment = align_pdf_correction(previous_text, corrected_text, previous_sections)

    assert alignment.location_status == "unmapped"
    assert alignment.confidence < 0.75
    assert len(alignment.sections) == 1
    assert alignment.sections[0].page_number is None
    assert "no page location" in alignment.warnings[0]


def test_missing_pdf_section_boundaries_fails_closed() -> None:
    alignment = align_pdf_correction(
        "Stored extraction no longer matches its sections.",
        "Corrected text.",
        [ExtractedSection(content="Missing section text", page_number=3)],
    )

    assert alignment.location_status == "unmapped"
    assert alignment.method == "unmapped-v1"
    assert alignment.confidence == 0
    assert alignment.sections == [ExtractedSection(content="Corrected text.")]
