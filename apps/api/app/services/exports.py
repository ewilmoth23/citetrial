from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Claim,
    ResearchBrief,
    ResearchNote,
    ResearchProject,
    Source,
    TimelineEvent,
)


def project_export_data(
    db: Session, project: ResearchProject, include_full_text: bool = False
) -> dict[str, Any]:
    sources = db.scalars(
        select(Source)
        .where(Source.project_id == project.id)
        .options(
            selectinload(Source.document),
            selectinload(Source.correction_revisions),
        )
    ).all()
    claims = db.scalars(
        select(Claim).where(Claim.project_id == project.id).options(selectinload(Claim.evidence))
    ).all()
    notes = db.scalars(select(ResearchNote).where(ResearchNote.project_id == project.id)).all()
    events = db.scalars(
        select(TimelineEvent)
        .where(TimelineEvent.project_id == project.id)
        .options(selectinload(TimelineEvent.evidence))
    ).all()
    briefs = db.scalars(
        select(ResearchBrief)
        .where(ResearchBrief.project_id == project.id)
        .options(selectinload(ResearchBrief.sections))
    ).all()
    return {
        "schema_version": "1.1",
        "project": {
            "id": project.id,
            "title": project.title,
            "primary_question": project.primary_question,
            "description": project.description,
            "status": project.status.value,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
        },
        "sources": [
            {
                "id": source.id,
                "source_type": source.source_type.value,
                "original_name": source.original_name,
                "normalized_url": source.normalized_url,
                "final_url": source.final_url,
                "title": source.title,
                "author": source.author,
                "publisher": source.publisher,
                "publication_date": source.publication_date.isoformat()
                if source.publication_date
                else None,
                "content_hash": source.content_hash,
                "extraction_method": source.extraction_method,
                "processing_status": source.processing_status.value,
                "warnings": source.warnings,
                "correction_revision": (
                    source.document.correction_revision if source.document else 0
                ),
                "correction_history": [
                    {
                        "revision": item.revision,
                        "correction_note": item.correction_note,
                        "previous_text_hash": item.previous_text_hash,
                        "corrected_text_hash": item.corrected_text_hash,
                        "alignment_method": item.alignment_method,
                        "alignment_confidence": item.alignment_confidence,
                        "location_status": item.location_status,
                        "created_at": item.created_at.isoformat(),
                        **({"corrected_text": item.corrected_text} if include_full_text else {}),
                    }
                    for item in source.correction_revisions
                ],
                **(
                    {
                        "full_text": (
                            source.document.corrected_text or source.document.normalized_text
                            if source.document
                            else None
                        ),
                        "original_normalized_text": (
                            source.document.normalized_text if source.document else None
                        ),
                        "correction_note": (
                            source.document.correction_note if source.document else None
                        ),
                    }
                    if include_full_text
                    else {}
                ),
            }
            for source in sources
        ],
        "claims": [
            {
                "id": claim.id,
                "text": claim.text,
                "type": claim.claim_type,
                "status": claim.status,
                "confidence": claim.confidence,
                "user_notes": claim.user_notes,
                "evidence": [
                    {
                        "id": evidence.id,
                        "source_id": evidence.source_id,
                        "excerpt": evidence.excerpt,
                        "location": evidence.location,
                        "relationship": evidence.relationship_type,
                        "origin": evidence.origin,
                        "source_revision": evidence.source_revision,
                    }
                    for evidence in claim.evidence
                ],
            }
            for claim in claims
        ],
        "timeline": [
            {
                "id": event.id,
                "title": event.title,
                "date_start": event.date_start.isoformat() if event.date_start else None,
                "date_end": event.date_end.isoformat() if event.date_end else None,
                "date_label": event.date_label,
                "date_precision": event.date_precision,
                "description": event.description,
                "origin": event.origin,
                "review_status": event.review_status,
                "evidence": [
                    {
                        "source_id": item.source_id,
                        "excerpt": item.excerpt,
                        "location": item.location,
                        "source_revision": item.source_revision,
                    }
                    for item in event.evidence
                ],
            }
            for event in events
        ],
        "notes": [
            {
                "id": note.id,
                "title": note.title,
                "content": note.content,
                "origin": "user",
                "source_id": note.source_id,
                "claim_id": note.claim_id,
                "timeline_event_id": note.timeline_event_id,
            }
            for note in notes
        ],
        "briefs": [
            {
                "id": brief.id,
                "title": brief.title,
                "sections": [
                    {
                        "type": section.section_type,
                        "title": section.title,
                        "content": section.content,
                        "origin": section.origin,
                        "user_edited": section.user_edited,
                    }
                    for section in brief.sections
                ],
            }
            for brief in briefs
        ],
        "limitations": [
            "Citations identify stored source locations; they do not prove truth.",
            "Generated summaries and inferences require human review.",
            "The export omits provider secrets, hidden prompts, logs, and local storage paths.",
        ],
    }


def project_markdown(db: Session, project: ResearchProject, include_notes: bool = True) -> str:
    data = project_export_data(db, project)
    lines = [f"# {project.title}", "", "## Research question", "", project.primary_question, ""]
    if project.description:
        lines += ["## Background", "", project.description, ""]
    lines += ["## Claims and evidence", ""]
    if not data["claims"]:
        lines += ["No claims have been recorded.", ""]
    for claim in data["claims"]:
        lines += [f"### {claim['text']}", "", f"Status: **{claim['status']}**", ""]
        for evidence in claim["evidence"]:
            lines.append(
                f"- **{evidence['relationship']}** — {evidence['excerpt']} "
                f"[source {evidence['source_id']}, text revision "
                f"{evidence['source_revision']}"
                f"{', ' + evidence['location'] if evidence['location'] else ''}]"
            )
        lines.append("")
    lines += ["## Timeline", ""]
    for event in data["timeline"]:
        when = event["date_label"] or event["date_start"] or "Date unknown"
        lines.append(
            f"- **{when}** ({event['date_precision']}; {event['review_status']}; "
            f"origin: {event['origin']}) — {event['title']}: {event['description']}"
        )
        for evidence in event["evidence"]:
            lines.append(
                f"  - Evidence: {evidence['excerpt']} [source {evidence['source_id']}"
                f", text revision {evidence['source_revision']}"
                f"{', ' + evidence['location'] if evidence['location'] else ''}]"
            )
    lines.append("")
    if include_notes:
        lines += ["## User-authored notes", ""]
        for note in data["notes"]:
            lines += [f"### {note['title']}", "", note["content"], ""]
    lines += ["## Research brief", ""]
    for brief in data["briefs"]:
        for section in brief["sections"]:
            lines += [f"### {section['title']}", "", section["content"], ""]
    lines += ["## Sources", ""]
    for source in data["sources"]:
        attribution = ", ".join(
            item
            for item in [source["author"], source["publisher"], source["publication_date"]]
            if item
        )
        lines.append(
            f"- {source['title'] or source['original_name']} "
            f"({source['source_type']}; text revision {source['correction_revision']})"
            + (f" — {attribution}" if attribution else "")
        )
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in data["limitations"]]
    return "\n".join(lines).strip() + "\n"
