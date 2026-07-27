# Troubleshooting

## Webpage retrieval

- **Blocked URL:** only HTTPS and public destinations are permitted. Local mock servers require test-only
  transports; do not enable HTTP/private imports in production.
- **Retrieval/timeout:** verify the page is publicly reachable without cookies, login, JavaScript, or a
  paywall. Increase limits cautiously.
- **Extraction problem:** inspect warnings and raw/normalized text on Source Detail. Save a correction with
  a note; the original is preserved.

## PDFs and text

- **Corrupt/encrypted PDF:** export an unencrypted valid PDF. Image-only pages are reported and need manual
  notes; OCR is not included.
- **Encoding warning:** compare extracted text with the original and use correction if necessary.
- **Unmapped corrected PDF:** the edit differed too much from the preceding revision for reliable page
  alignment. The corrected text remains searchable, but its chunks intentionally have no page number.
  Split the review into smaller corrections or cite the original PDF manually after visual verification.
- **Missing stored file:** restore the data volume or delete/reimport the failed source.

## Search and models

- **No search results:** wait for ready status, broaden terms, clear source selection, or switch mode.
- **Embedding downloads:** the default baseline downloads nothing. Install `.[semantic]` only when working
  on the future learned-embedding adapter.
- **Ollama:** run `ollama serve`, verify the model name, then `make provider-health`.
- **Malformed model output/citation warning:** CiteTrail rejects unsupported markers and shows a warning.
  Open cited excerpts and rerun only after checking provider behavior.

## Ingestion queue

- **Queued after restart:** this is expected while the embedded worker reclaims durable work. Source Detail
  shows the recovery count and current stage.
- **Failed attempt:** open the Source Detail processing trail for the stored error, then use Retry. Retrying
  creates a new attempt and preserves the failed one for audit.
- **Queue does not advance:** check `/api/v1/health`; `checks.ingestion_worker.status` must be `healthy`.
  Run exactly one API worker process. If storage was moved or deleted, restore it before retrying file jobs.

## Docker, ports, and storage

- The API uses 8000, Vite uses 5173, and Compose UI uses 8080. Change bound host ports if occupied.
- On Linux, retain the `host-gateway` mapping for host Ollama.
- Ensure the named volume or configured data directory is writable by the container user.
- Run `docker compose config` to validate interpolation and `docker compose logs api` for migration errors.
- **Data directory already in use:** another CiteTrail API or an offline backup/restore process owns the
  workspace. Stop it; never delete `.citetrail.lock` to force concurrent SQLite access.

## Backup and restore

- **Backup reports a missing upload:** the database references a file that is absent. Restore the data
  volume or delete/reimport that source; CiteTrail refuses to label an incomplete archive as a backup.
- **Backup intent required:** use the Settings button or send the documented `X-CiteTrail-Intent: backup`
  header. This prevents a normal cross-site form submission from triggering a full backup response.
- **Restore rejected:** run `python scripts/restore_backup.py ARCHIVE --inspect`. Traversal paths, links,
  encrypted or undeclared entries, checksum/size mismatches, corrupt SQLite, and unrelated databases fail
  before the current workspace changes.
- **Restore says data is in use:** stop `make api-dev` or run `docker compose down`, then retry. Restore is
  intentionally unavailable inside the running application.
- After verifying a restored workspace and running migrations, remove the reported timestamped
  pre-restore directory when you no longer need manual rollback.

## Migrations and builds

- Run `make migrate` after pulling schema changes. Create and inspect a `.ctbackup` before production
  migrations.
- For frontend type errors, run `cd apps/web && npm exec tsc -b` before `npm run build`.
- Remove `node_modules` only when its lockfile and installed tree are genuinely inconsistent, then use
  `npm install`; do not delete application data.
