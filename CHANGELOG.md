# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and semantic
versioning.

## [Unreleased]

### Added

- Verified full-workspace `.ctbackup` archives with consistent SQLite snapshots, referenced uploads,
  vector files, exact manifests, byte counts, SHA-256 validation, and an in-product download.
- Hardened offline restore with hostile-archive validation, SQLite integrity checks, atomic replacement,
  and retained pre-restore rollback data.
- Exclusive data-directory ownership plus crash-recoverable upload-deletion staging.
- Durable SQLite-backed ingestion jobs with atomic claiming, live stage/progress, graceful shutdown,
  automatic restart recovery, orphan reconstruction, and numbered retry history.
- Processing health, recovery counts, and attempt history in the API and Source Detail interface.
- Immutable source-correction revision history with before/after hashes, review notes, mapping method,
  confidence, and an auditable Source Detail ledger.
- Revision labels on claim evidence, timeline evidence, citations, Markdown exports, and JSON schema 1.1.
- Confidence-gated PDF correction alignment that retains page lineage for small edits and fails closed to
  unmapped locations for unreliable rewrites.

### Changed

- Upload and webpage endpoints now commit queued work before returning instead of depending on
  request-scoped FastAPI background tasks. CPU-bound ingestion runs outside the API event loop.
- Exact-phrase retrieval now treats the quoted phrase as a hard boundary instead of mixing in
  semantically related results.
- Citation verification now tolerates PDF line-wrap whitespace while continuing to require exact
  punctuation and numbers.
- Provider health now distinguishes a reachable Ollama/OpenAI-compatible server from an actually
  available configured model.
- Production PDF rendering uses a version-matched PDF.js worker with the correct JavaScript MIME type
  and a user-visible load failure state.
- Preserved brief edits now require an explicit in-application confirmation before regeneration.
- Docker Compose now declares production mode, loopback-only ports, non-root users, and
  `no-new-privileges`; production web bundles no longer publish source maps.
- Production images now pin base-image digests; Python runtime packages install from a generated,
  fully hashed lockfile.
- Migration `20260723_0003` repairs stale legacy running jobs and enforces one active job per source.
- Source corrections now deactivate superseded chunks instead of deleting them, preserving historical
  citations and evidence while keeping current retrieval free of stale text.
- Migration `20260718_0002` upgrades both fresh and existing SQLite databases with correction provenance.

## [0.1.0] - 2026-07-18

### Added

- Provenance-first FastAPI/React monorepo.
- Safe webpage retrieval and PDF/Markdown/text/note ingestion.
- Location-preserving extraction, FTS5 and local semantic/hybrid retrieval.
- Grounded answers with validated structured citations and quotation warnings.
- Claims, verified evidence relationships, timeline, notes, briefs, exports, history, and deletion.
- Synthetic transit research project, tests, Docker, CI, and security/responsible-AI documentation.
