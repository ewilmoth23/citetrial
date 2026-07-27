from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    BriefSection,
    Claim,
    ResearchBrief,
    ResearchProject,
    Source,
    TimelineEvent,
)

DEFAULT_SECTIONS = [
    ("research_question", "Research question"),
    ("executive_summary", "Executive summary"),
    ("key_findings", "Key findings"),
    ("background", "Background"),
    ("evidence_by_claim", "Evidence by claim"),
    ("contradictions", "Contradictions and uncertainties"),
    ("timeline", "Timeline"),
    ("open_questions", "Open questions"),
    ("source_list", "Source list"),
    ("limitations", "Limitations"),
]


def create_brief(db: Session, project: ResearchProject, title: str) -> ResearchBrief:
    brief = ResearchBrief(project_id=project.id, title=title)
    db.add(brief)
    db.flush()
    for ordinal, (section_type, section_title) in enumerate(DEFAULT_SECTIONS):
        content = project.primary_question if section_type == "research_question" else ""
        db.add(
            BriefSection(
                brief_id=brief.id,
                section_type=section_type,
                title=section_title,
                content=content,
                ordinal=ordinal,
                origin="user" if content else "generated",
            )
        )
    db.flush()
    return brief


def deterministic_section(
    db: Session, brief: ResearchBrief, section: BriefSection
) -> tuple[str, str | None]:
    project = brief.project
    claims = db.scalars(select(Claim).where(Claim.project_id == project.id)).all()
    sources = db.scalars(select(Source).where(Source.project_id == project.id)).all()
    events = db.scalars(
        select(TimelineEvent).where(
            TimelineEvent.project_id == project.id,
            TimelineEvent.review_status == "accepted",
            TimelineEvent.evidence.any(),
        )
    ).all()
    if section.section_type == "research_question":
        return project.primary_question, None
    if section.section_type == "source_list":
        if not sources:
            return "No sources have been added.", "This section has no sources to cite."
        return "\n".join(
            f"- {source.title or source.original_name} ({source.source_type.value})"
            + (f" — {source.author}" if source.author else "")
            for source in sources
        ), None
    if section.section_type == "evidence_by_claim" or section.section_type == "key_findings":
        if not claims:
            return (
                "No reviewed claims are available.",
                "Create and review claims before generating this section.",
            )
        lines = []
        for claim in claims:
            lines.append(f"### {claim.text}\nStatus: {claim.status}.")
            for evidence in claim.evidence:
                lines.append(
                    f"- {evidence.relationship_type}: {evidence.excerpt} [source: {evidence.source_id}]"
                )
        return "\n\n".join(lines), None
    if section.section_type == "contradictions":
        contradictions = [
            evidence
            for claim in claims
            for evidence in claim.evidence
            if evidence.relationship_type == "contradicts"
        ]
        if not contradictions:
            return (
                "No contradicting evidence has been linked.",
                "Absence of linked contradictions is not proof of agreement.",
            )
        return "\n".join(
            f"- {item.excerpt} [source: {item.source_id}]" for item in contradictions
        ), None
    if section.section_type == "timeline":
        if not events:
            return (
                "No evidence-backed timeline events are available.",
                "This section needs reviewed timeline events.",
            )
        return "\n".join(
            f"- {event.date_label or event.date_start or 'Date unknown'} ({event.date_precision}): {event.title} — {event.description}"
            for event in sorted(
                events, key=lambda item: (item.date_start is None, item.date_start, item.sort_order)
            )
        ), None
    if section.section_type == "open_questions":
        unresolved = [
            claim
            for claim in claims
            if claim.claim_type == "unresolved_question" or claim.status == "insufficient_evidence"
        ]
        return (
            "\n".join(f"- {claim.text}" for claim in unresolved)
            or "No open questions have been recorded."
        ), None
    if section.section_type == "limitations":
        return (
            "This brief is limited to sources stored in CiteTrail. Citations locate source evidence; "
            "they do not establish that a claim is true. Generated synthesis and date interpretation require review."
        ), None
    if section.section_type == "background":
        return project.description or "No project background has been recorded.", None
    return (
        "A model-generated synthesis was not requested. Review the evidence-backed sections and add user-authored text here.",
        "Deterministic mode does not synthesize an executive narrative.",
    )
