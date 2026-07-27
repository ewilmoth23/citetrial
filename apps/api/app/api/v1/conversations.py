from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_project
from app.core.config import Settings, get_settings
from app.core.runtime_settings import effective_settings
from app.db.session import get_db
from app.models.entities import (
    Citation,
    Message,
    ProjectActivity,
    ResearchConversation,
    Source,
    SourceDocument,
)
from app.providers.factory import create_provider
from app.research.citations import citation_indices, citation_marker
from app.research.qa import answer_question
from app.retrieval.search import hybrid_search
from app.schemas.research import (
    AnswerResponse,
    CitationRead,
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
    QuestionRequest,
)
from app.schemas.source import SearchRequest

router = APIRouter(
    prefix="/projects/{project_id}/conversations", tags=["conversations", "messages"]
)


def _validate_source_selection(db: Session, project_id: str, source_ids: list[str]) -> None:
    if not source_ids:
        return
    valid = set(
        db.scalars(
            select(Source.id).where(Source.project_id == project_id, Source.id.in_(source_ids))
        ).all()
    )
    if valid != set(source_ids):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_source_selection",
                "message": "One or more selected sources are outside this project",
            },
        )


def require_conversation(
    db: Session, project_id: str, conversation_id: str
) -> ResearchConversation:
    conversation = db.scalar(
        select(ResearchConversation)
        .where(
            ResearchConversation.id == conversation_id,
            ResearchConversation.project_id == project_id,
        )
        .options(
            selectinload(ResearchConversation.messages)
            .selectinload(Message.citations)
            .selectinload(Citation.source)
        )
    )
    if conversation:
        return conversation
    raise HTTPException(
        status_code=404,
        detail={"code": "conversation_not_found", "message": "Conversation not found"},
    )


def message_read(message: Message) -> MessageRead:
    citations = [
        CitationRead.model_validate(item).model_copy(
            update={"source_title": item.source.title or item.source.original_name}
        )
        for item in message.citations
    ]
    return MessageRead.model_validate(message).model_copy(update={"citations": citations})


def conversation_read(conversation: ResearchConversation) -> ConversationRead:
    return ConversationRead.model_validate(conversation).model_copy(
        update={"messages": [message_read(message) for message in conversation.messages]}
    )


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    project_id: str, payload: ConversationCreate, db: Session = Depends(get_db)
) -> ConversationRead:
    require_project(db, project_id)
    _validate_source_selection(db, project_id, payload.selected_source_ids)
    conversation = ResearchConversation(project_id=project_id, **payload.model_dump())
    db.add(conversation)
    db.commit()
    return conversation_read(require_conversation(db, project_id, conversation.id))


@router.get("", response_model=list[ConversationRead])
def list_conversations(project_id: str, db: Session = Depends(get_db)) -> list[ConversationRead]:
    require_project(db, project_id)
    ids = db.scalars(
        select(ResearchConversation.id)
        .where(ResearchConversation.project_id == project_id)
        .order_by(ResearchConversation.updated_at.desc())
    ).all()
    return [conversation_read(require_conversation(db, project_id, item)) for item in ids]


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    project_id: str, conversation_id: str, db: Session = Depends(get_db)
) -> ConversationRead:
    return conversation_read(require_conversation(db, project_id, conversation_id))


@router.patch("/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    project_id: str,
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
) -> ConversationRead:
    conversation = require_conversation(db, project_id, conversation_id)
    if payload.selected_source_ids is not None:
        _validate_source_selection(db, project_id, payload.selected_source_ids)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(conversation, key, value)
    db.commit()
    return conversation_read(require_conversation(db, project_id, conversation_id))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    project_id: str, conversation_id: str, db: Session = Depends(get_db)
) -> Response:
    db.delete(require_conversation(db, project_id, conversation_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{conversation_id}/messages", response_model=AnswerResponse)
async def submit_question(
    project_id: str,
    conversation_id: str,
    payload: QuestionRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnswerResponse:
    conversation = require_conversation(db, project_id, conversation_id)
    selection = payload.selected_source_ids or conversation.selected_source_ids
    _validate_source_selection(db, project_id, selection)
    user_message = Message(
        conversation_id=conversation.id, role="user", content=payload.question, generated=False
    )
    db.add(user_message)
    db.flush()
    effective = effective_settings(settings, db)
    retrieval_mode = payload.retrieval_mode
    if not effective.semantic_search_enabled and retrieval_mode != "lexical":
        retrieval_mode = "lexical"
    results = hybrid_search(
        db,
        project_id,
        SearchRequest(query=payload.question, mode=retrieval_mode, source_ids=selection, limit=8),
    )
    grounded = await answer_question(create_provider(effective), payload.question, results)
    answer_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=grounded.content,
        generated=True,
        warning=" ".join(grounded.warnings) or None,
    )
    db.add(answer_message)
    db.flush()
    used_indices = citation_indices(grounded.content)
    for index in sorted(used_indices):
        if not 1 <= index <= len(results):
            continue
        result = results[index - 1]
        location = (
            f"page {result.location.page_number}"
            if result.location.page_number
            else result.location.heading_path
            or (
                f"lines {result.location.line_start}-{result.location.line_end}"
                if result.location.line_start
                else None
            )
        )
        db.add(
            Citation(
                message_id=answer_message.id,
                source_id=result.source_id,
                source_chunk_id=result.chunk_id,
                marker=citation_marker(index, result),
                excerpt=result.excerpt,
                location=location,
                source_revision=db.scalar(
                    select(SourceDocument.correction_revision).where(
                        SourceDocument.source_id == result.source_id
                    )
                )
                or 0,
            )
        )
    db.add(
        ProjectActivity(
            project_id=project_id,
            action="question_answered",
            detail=f"citations:{len(used_indices)}",
        )
    )
    db.commit()
    stored_user = db.get(Message, user_message.id)
    stored_answer = db.scalar(
        select(Message)
        .where(Message.id == answer_message.id)
        .options(selectinload(Message.citations).selectinload(Citation.source))
    )
    if stored_user is None or stored_answer is None:
        raise RuntimeError("Conversation messages were not persisted")
    return AnswerResponse(
        user_message=message_read(stored_user),
        answer_message=message_read(stored_answer),
        retrieved=results,
        provider_available=grounded.provider_available,
    )
