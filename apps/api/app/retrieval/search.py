from __future__ import annotations

import re

from sqlalchemy import Select, select, text
from sqlalchemy.orm import Session

from app.models.entities import Source, SourceChunk
from app.retrieval.embeddings import cosine_similarity, deterministic_embedding
from app.schemas.source import SearchRequest, SearchResult, SourceLocation


def _fts_query(query: str, phrase: bool) -> str:
    cleaned = re.findall(r"[\w'-]+", query, flags=re.UNICODE)
    if not cleaned:
        raise ValueError("Query does not contain searchable terms")
    if phrase:
        return '"' + " ".join(cleaned).replace('"', '""') + '"'
    return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in cleaned)


def _location(chunk: SourceChunk) -> SourceLocation:
    return SourceLocation(
        page_number=chunk.page_number,
        heading_path=chunk.heading_path,
        line_start=chunk.line_start,
        line_end=chunk.line_end,
    )


def _excerpt(content: str, query: str, maximum: int = 520) -> str:
    folded = content.casefold()
    positions = [folded.find(token.casefold()) for token in re.findall(r"[\w'-]+", query)]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - maximum // 3)
    end = min(len(content), start + maximum)
    prefix = "…" if start else ""
    suffix = "…" if end < len(content) else ""
    return f"{prefix}{content[start:end].strip()}{suffix}"


def _base_chunk_query(
    project_id: str, request: SearchRequest
) -> Select[tuple[SourceChunk, Source]]:
    statement = (
        select(SourceChunk, Source)
        .join(Source)
        .where(SourceChunk.project_id == project_id, SourceChunk.is_active.is_(True))
    )
    if request.source_ids:
        statement = statement.where(SourceChunk.source_id.in_(request.source_ids))
    if request.source_types:
        statement = statement.where(Source.source_type.in_(request.source_types))
    if request.date_from:
        statement = statement.where(Source.publication_date >= request.date_from)
    if request.date_to:
        statement = statement.where(Source.publication_date <= request.date_to)
    return statement


def lexical_search(
    db: Session, project_id: str, request: SearchRequest, candidate_limit: int = 50
) -> list[SearchResult]:
    fts = _fts_query(request.query, request.phrase)
    source_filters = ""
    params: dict[str, object] = {"project_id": project_id, "query": fts, "limit": candidate_limit}
    if request.source_ids:
        placeholders = []
        for index, source_id in enumerate(request.source_ids):
            key = f"source_{index}"
            placeholders.append(f":{key}")
            params[key] = source_id
        source_filters = f" AND f.source_id IN ({','.join(placeholders)})"
    rows = db.execute(
        text(  # noqa: S608 - placeholders are generated; every value remains a bound parameter.
            "SELECT f.chunk_id, bm25(source_chunks_fts) AS rank "
            "FROM source_chunks_fts f WHERE f.project_id = :project_id "
            f"AND source_chunks_fts MATCH :query{source_filters} ORDER BY rank LIMIT :limit"  # noqa: S608
        ),
        params,
    ).all()
    if not rows:
        return []
    ranks = {row.chunk_id: float(row.rank) for row in rows}
    statement = (
        select(SourceChunk, Source)
        .join(Source)
        .where(SourceChunk.id.in_(ranks), SourceChunk.is_active.is_(True))
    )
    if request.source_types:
        statement = statement.where(Source.source_type.in_(request.source_types))
    if request.date_from:
        statement = statement.where(Source.publication_date >= request.date_from)
    if request.date_to:
        statement = statement.where(Source.publication_date <= request.date_to)
    results: list[SearchResult] = []
    for chunk, source in db.execute(statement):
        rank = ranks[chunk.id]
        score = 1.0 / (1.0 + max(0.0, -rank))
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                source_id=source.id,
                source_title=source.title or source.original_name,
                source_type=source.source_type,
                location=_location(chunk),
                excerpt=_excerpt(chunk.content, request.query),
                score=score,
                method="lexical",
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)


def semantic_search(db: Session, project_id: str, request: SearchRequest) -> list[SearchResult]:
    query_embedding = deterministic_embedding(request.query)
    candidates = db.execute(_base_chunk_query(project_id, request)).all()
    results: list[SearchResult] = []
    for chunk, source in candidates:
        if not chunk.embedding:
            continue
        score = max(0.0, cosine_similarity(query_embedding, chunk.embedding))
        if score <= 0:
            continue
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                source_id=source.id,
                source_title=source.title or source.original_name,
                source_type=source.source_type,
                location=_location(chunk),
                excerpt=_excerpt(chunk.content, request.query),
                score=score,
                method="semantic",
            )
        )
    return sorted(results, key=lambda item: item.score, reverse=True)


def hybrid_search(db: Session, project_id: str, request: SearchRequest) -> list[SearchResult]:
    # An explicit phrase is a hard evidence boundary, not a ranking hint.
    # Mixing semantic neighbors back into these results would present chunks
    # that do not contain the phrase the researcher asked to verify.
    if request.phrase:
        return lexical_search(db, project_id, request)[: request.limit]
    if request.mode == "lexical":
        return lexical_search(db, project_id, request)[: request.limit]
    if request.mode == "semantic":
        return semantic_search(db, project_id, request)[: request.limit]
    lexical = lexical_search(db, project_id, request)
    semantic = semantic_search(db, project_id, request)
    combined: dict[str, SearchResult] = {}
    scores: dict[str, float] = {}
    for rank, item in enumerate(lexical):
        combined[item.chunk_id] = item
        scores[item.chunk_id] = scores.get(item.chunk_id, 0) + 1 / (60 + rank)
    for rank, item in enumerate(semantic):
        combined.setdefault(item.chunk_id, item)
        scores[item.chunk_id] = scores.get(item.chunk_id, 0) + 1 / (60 + rank)
    ordered = sorted(combined.values(), key=lambda item: scores[item.chunk_id], reverse=True)
    seen_fingerprints: set[str] = set()
    diverse: list[SearchResult] = []
    for item in ordered:
        fingerprint = " ".join(item.excerpt.casefold().split())[:180]
        if fingerprint in seen_fingerprints:
            continue
        item.score = round(scores[item.chunk_id], 6)
        item.method = "hybrid"
        diverse.append(item)
        seen_fingerprints.add(fingerprint)
        if len(diverse) >= request.limit:
            break
    return diverse
