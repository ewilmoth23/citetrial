# Retrieval methodology

## Lexical retrieval

SQLite FTS5 indexes source chunks with Porter/unicode tokenization. User terms are parsed into quoted FTS
tokens, preventing raw FTS operator injection. Phrase mode constructs one quoted phrase. Project ID and
selected source IDs are mandatory SQL filters; source type and explicit publication dates may narrow them.

## Semantic retrieval

Version 1 generates deterministic 256-dimensional feature-hash vectors locally. This preserves offline
operation and deterministic CI but does not provide the language understanding of a learned embedding
model. `sentence-transformers` and ChromaDB are available as optional dependencies for a future adapter.

## Hybrid reranking

Lexical and semantic candidates are combined with reciprocal-rank fusion using an explicit constant of
60. Near-identical excerpts are deduplicated before the requested limit. Results return source/chunk IDs,
title, type, page/heading/line location, excerpt, score, and method.

## Limitations

FTS misses purely conceptual matches; feature hashing misses synonyms and cross-lingual relationships.
Ranks indicate query relevance, never source quality or truth. Evidence diversity is limited to excerpt
deduplication; researchers must inspect disagreements and source dependence.
