from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.data_lock import DataDirectoryInUseError, DataDirectoryLock  # noqa: E402
from app.db.init_db import init_database  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.extraction.pdf import extract_pdf  # noqa: E402
from app.extraction.text import extract_markdown, extract_plain_text  # noqa: E402
from app.extraction.webpage import extract_webpage  # noqa: E402
from app.ingestion.pipeline import index_document  # noqa: E402
from app.ingestion.storage import persist_upload  # noqa: E402
from app.models.entities import (  # noqa: E402
    Claim,
    ClaimEvidence,
    ProcessingStatus,
    ProjectActivity,
    ResearchProject,
    Source,
    SourceType,
    TimelineEvent,
    TimelineEvidence,
)
from app.research.briefs import create_brief, deterministic_section  # noqa: E402


def add_source(db, project, filename: str, source_type: SourceType):
    path = ROOT / "sample_data" / filename
    data = path.read_bytes()
    source = Source(
        project_id=project.id,
        source_type=source_type,
        original_name=filename,
        title=path.stem.replace("-", " ").title(),
        processing_status=ProcessingStatus.extracting,
    )
    db.add(source)
    db.flush()
    if source_type == SourceType.webpage:
        extracted = extract_webpage(data)
        source.normalized_url = f"https://sample.citetrail.local/{filename}"
        source.final_url = source.normalized_url
    elif source_type == SourceType.pdf:
        source.storage_key = persist_upload(filename, data, get_settings())
        extracted = extract_pdf(data)
    elif source_type == SourceType.markdown:
        extracted = extract_markdown(data)
    else:
        extracted = extract_plain_text(data)
    index_document(db, source, extracted, get_settings())
    return source


def main() -> None:
    settings = get_settings()
    try:
        with DataDirectoryLock(settings.data_dir):
            init_database()
            with SessionLocal() as db:
                load_sample(db)
    except DataDirectoryInUseError as exc:
        raise SystemExit(f"Sample load refused: {exc}") from exc


def load_sample(db) -> None:
    existing = db.scalar(
        select(ResearchProject).where(
            ResearchProject.title == "Harbor Loop transit pilot - synthetic demo"
        )
    )
    if existing:
        print(existing.id)
        return
    project = ResearchProject(
        title="Harbor Loop transit pilot - synthetic demo",
        primary_question="What effects did the fictional Harbor Loop municipal transit program have, and where does the evidence conflict?",
        description="A fully synthetic project demonstrating agreement, contradiction, approximate dates, duplicate text, missing authorship, and an unresolved causal question.",
        status="analyzing",
    )
    db.add(project)
    db.flush()
    overview = add_source(db, project, "transit-program-overview.html", SourceType.webpage)
    survey = add_source(db, project, "transit-rider-survey.html", SourceType.webpage)
    add_source(db, project, "transit-evaluation-report.pdf", SourceType.pdf)
    meeting = add_source(db, project, "transit-meeting-notes.md", SourceType.markdown)
    add_source(db, project, "transit-press-release.txt", SourceType.text)
    claim = Claim(
        project_id=project.id,
        text="Average weekday Harbor Loop boardings increased after the pilot began, but the September total is disputed.",
        claim_type="factual",
        status="disputed",
        user_notes="The sources use different transfer-validation rules.",
    )
    db.add(claim)
    db.flush()
    support_excerpt = "Validated weekday boardings on the loop averaged 8,240 in September, compared with a baseline average of 6,800 during March."
    contradiction_excerpt = (
        "The bulletin calculated September weekday boardings at 7,510, not 8,240."
    )
    db.add_all(
        [
            ClaimEvidence(
                claim_id=claim.id,
                source_id=overview.id,
                excerpt=support_excerpt,
                relationship_type="supports",
                origin="system",
            ),
            ClaimEvidence(
                claim_id=claim.id,
                source_id=survey.id,
                excerpt=contradiction_excerpt,
                relationship_type="contradicts",
                origin="system",
            ),
        ]
    )
    unresolved = Claim(
        project_id=project.id,
        text="Did construction near Central Station cause part of the recorded ridership increase?",
        claim_type="unresolved_question",
        status="insufficient_evidence",
    )
    db.add(unresolved)
    event = TimelineEvent(
        project_id=project.id,
        title="Signal-priority tuning began",
        date_label="around late spring 2032",
        date_precision="approximate",
        description="Staff recalled beginning signal-priority tuning, but did not identify an exact day.",
        origin="system",
        review_status="accepted",
    )
    db.add(event)
    db.flush()
    db.add(
        TimelineEvidence(
            timeline_event_id=event.id,
            source_id=meeting.id,
            excerpt="Staff recalled that signal-priority tuning began around late spring 2032.",
            location="Around late spring 2032",
        )
    )
    brief = create_brief(db, project, "Harbor Loop evidence brief")
    db.flush()
    for section in brief.sections:
        section.content, section.generation_warning = deterministic_section(db, brief, section)
    db.add(
        ProjectActivity(
            project_id=project.id,
            action="synthetic_sample_loaded",
            detail="Deterministic fictional project",
        )
    )
    db.commit()
    print(project.id)


if __name__ == "__main__":
    main()
