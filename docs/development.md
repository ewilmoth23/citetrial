# Development

Follow the setup and command table in the README. Backend code is grouped by API, core configuration,
database, extraction, ingestion, providers, research logic, retrieval, schemas, and services. Frontend
routes assemble feature-focused pages over one typed API client.

## Migrations

Run `make migrate`. After changing SQLAlchemy models, create a reviewed revision from `apps/api` with
`alembic revision --autogenerate -m "description"`; inspect foreign keys, cascading behavior, and indexes
before applying it to real data.

## Backups and destructive data changes

Use the Settings download for an online full-workspace backup or `make backup` when the API is stopped.
Never treat Markdown/JSON export as a restorable database backup. Restore must remain offline and must
validate the entire archive before replacing any target data; retain the pre-restore rollback directory
until the restored workspace has been opened and verified.

Code that changes the upload file set must participate in the storage-operation lock. Deletion first moves
files into protected staging, commits the database transaction, and then destroys the staged bytes.
Startup recovery restores staged files still referenced by the database and finalizes files whose records
were committed away. Add pre-commit interruption, post-commit interruption, and unsafe-path tests when
changing this lifecycle.

## Tests

Backend tests must use temporary storage, an isolated database, synthetic files, mocked HTTP responses,
and mocked providers. Network tests must never contact arbitrary public pages. Frontend tests use mocked
fetch responses. E2E tests use the deterministic mock server.

## Add an extractor

Return `ExtractedDocument` with raw/normalized text, method, sections, warnings, and only explicit
metadata. Preserve source locations. Register the type in the ingestion pipeline and add corrupt,
empty, oversize, provenance, and deletion tests.

## Change ingestion jobs

Keep job creation in the same transaction as the source record. A source may have only one active
(`queued` or `running`) job, and a retry must create a new numbered attempt rather than mutating history.
The embedded worker owns claiming and dispatch; processing functions update the claimed row in place.
Add tests for startup recovery, orphan reconstruction, same-row failure, retry history, deletion, and
event-loop-safe execution. Run only one API worker process until lease-based multi-worker execution is
implemented.

## Add a provider

Implement `ModelProvider.health`, `complete`, and `leaves_device`; normalize errors to `ProviderError`.
Never expose credentials or provider-specific payloads outside `app/providers`.

## Change retrieval or citations

Keep project and selected-source filters inside the retrieval layer. Return structured locations. Use the
single citation builder/validator in `app/research/citations.py`; do not recreate markers in routes or
trust provider metadata.
