from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_project
from app.db.session import get_db
from app.models.entities import Claim, ClaimEvidence, ProjectActivity, Source, SourceChunk
from app.research.citations import verify_quotation
from app.schemas.research import ClaimCreate, ClaimRead, ClaimUpdate, EvidenceCreate, EvidenceRead

router = APIRouter(prefix="/projects/{project_id}/claims", tags=["claims", "evidence"])


def require_claim(db: Session, project_id: str, claim_id: str) -> Claim:
    claim = db.scalar(
        select(Claim)
        .where(Claim.id == claim_id, Claim.project_id == project_id)
        .options(selectinload(Claim.evidence).selectinload(ClaimEvidence.source))
    )
    if claim:
        return claim
    raise HTTPException(
        status_code=404, detail={"code": "claim_not_found", "message": "Claim not found"}
    )


def evidence_read(item: ClaimEvidence) -> EvidenceRead:
    return EvidenceRead.model_validate(item).model_copy(
        update={"source_title": item.source.title or item.source.original_name}
    )


def claim_read(item: Claim) -> ClaimRead:
    return ClaimRead.model_validate(item).model_copy(
        update={"evidence": [evidence_read(link) for link in item.evidence]}
    )


@router.post("", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
def create_claim(project_id: str, payload: ClaimCreate, db: Session = Depends(get_db)) -> ClaimRead:
    require_project(db, project_id)
    claim = Claim(project_id=project_id, **payload.model_dump())
    db.add(claim)
    db.flush()
    db.add(ProjectActivity(project_id=project_id, action="claim_created", detail=claim.id))
    db.commit()
    return claim_read(require_claim(db, project_id, claim.id))


@router.get("", response_model=list[ClaimRead])
def list_claims(project_id: str, db: Session = Depends(get_db)) -> list[ClaimRead]:
    require_project(db, project_id)
    claims = (
        db.scalars(
            select(Claim)
            .where(Claim.project_id == project_id)
            .options(selectinload(Claim.evidence).selectinload(ClaimEvidence.source))
            .order_by(Claim.created_at.desc())
        )
        .unique()
        .all()
    )
    return [claim_read(item) for item in claims]


@router.get("/{claim_id}", response_model=ClaimRead)
def get_claim(project_id: str, claim_id: str, db: Session = Depends(get_db)) -> ClaimRead:
    return claim_read(require_claim(db, project_id, claim_id))


@router.patch("/{claim_id}", response_model=ClaimRead)
def update_claim(
    project_id: str, claim_id: str, payload: ClaimUpdate, db: Session = Depends(get_db)
) -> ClaimRead:
    claim = require_claim(db, project_id, claim_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(claim, key, value)
    db.commit()
    return claim_read(require_claim(db, project_id, claim_id))


@router.delete("/{claim_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_claim(project_id: str, claim_id: str, db: Session = Depends(get_db)) -> Response:
    claim = require_claim(db, project_id, claim_id)
    db.delete(claim)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{claim_id}/evidence", response_model=EvidenceRead, status_code=status.HTTP_201_CREATED
)
def connect_evidence(
    project_id: str, claim_id: str, payload: EvidenceCreate, db: Session = Depends(get_db)
) -> EvidenceRead:
    claim = require_claim(db, project_id, claim_id)
    source = db.get(Source, payload.source_id)
    if not source or source.project_id != project_id or not source.document:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_source",
                "message": "Evidence source is not ready in this project",
            },
        )
    chunk = db.get(SourceChunk, payload.source_chunk_id) if payload.source_chunk_id else None
    if payload.source_chunk_id and (
        not chunk
        or not chunk.is_active
        or chunk.project_id != project_id
        or chunk.source_id != source.id
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_chunk",
                "message": "Evidence chunk does not belong to the selected source",
            },
        )
    searchable_text = (
        chunk.content
        if chunk
        else (source.document.corrected_text or source.document.normalized_text)
    )
    if not verify_quotation(payload.excerpt, searchable_text):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unmatched_evidence",
                "message": "Evidence excerpt does not exactly match stored source text",
            },
        )
    if payload.origin != "user":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "managed_origin",
                "message": "System and model-suggestion origins cannot be asserted by this user endpoint",
            },
        )
    link = ClaimEvidence(
        claim_id=claim.id,
        source_revision=source.document.correction_revision,
        **payload.model_dump(),
    )
    db.add(link)
    db.flush()
    db.add(
        ProjectActivity(
            project_id=project_id,
            action="evidence_linked",
            detail=f"{claim_id}:{payload.relationship_type}",
        )
    )
    db.commit()
    db.refresh(link)
    link.source = source
    return evidence_read(link)


@router.patch("/{claim_id}/evidence/{evidence_id}", response_model=EvidenceRead)
def update_evidence_relationship(
    project_id: str,
    claim_id: str,
    evidence_id: str,
    relationship_type: str,
    db: Session = Depends(get_db),
) -> EvidenceRead:
    if relationship_type not in {"supports", "contradicts", "contextualizes", "uncertain"}:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_relationship", "message": "Invalid evidence relationship"},
        )
    require_claim(db, project_id, claim_id)
    item = db.get(ClaimEvidence, evidence_id)
    if not item or item.claim_id != claim_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "evidence_not_found", "message": "Evidence link not found"},
        )
    item.relationship_type = relationship_type
    db.commit()
    db.refresh(item)
    return evidence_read(item)


@router.delete("/{claim_id}/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(
    project_id: str, claim_id: str, evidence_id: str, db: Session = Depends(get_db)
) -> Response:
    require_claim(db, project_id, claim_id)
    item = db.get(ClaimEvidence, evidence_id)
    if not item or item.claim_id != claim_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "evidence_not_found", "message": "Evidence link not found"},
        )
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
