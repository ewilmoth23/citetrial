# Security model

## Threat model

Web URLs, redirects, DNS answers, response headers/bodies, filenames, uploaded bytes, PDF structures,
encodings, Markdown, extracted source instructions, and model output are untrusted. CiteTrail is intended
for loopback/local-network use by one trusted user. It is not safe to expose directly to the internet
because version 1 has no authentication.

The shipped frontend bundles its application assets and uses local system-font fallbacks; opening the UI
does not load fonts, analytics, or other assets from third-party origins.

## URL and SSRF defenses

- HTTPS only by default; HTTP is an explicit server configuration.
- Reject unsupported schemes, control characters, malformed ports, embedded credentials, localhost,
  loopback, private, link-local, multicast, reserved, unspecified, and known metadata destinations.
- Resolve every hostname and require every returned address to be public.
- Disable automatic redirects and validate each `Location` before the next request.
- Connect only to an address returned by that validation while preserving the original hostname for the
  HTTP `Host` header, TLS SNI, and certificate verification. Each address attempt and redirect uses a
  fresh connection so TLS state cannot cross hostname boundaries.
- Send no cookies or credentials, disable environment proxies, execute no JavaScript, submit no forms,
  follow no page links, and perform no crawling.
- Allow only HTML/XHTML/plain-text MIME types. Request identity encoding and enforce both declared and
  streamed byte limits.

IP pinning removes the separate hostname lookup between application validation and the TCP connection.
An outbound firewall that denies protected ranges remains recommended defense in depth for hostile
networks, resolver/OS defects, and future changes to the retrieval stack.

## Upload and rendering defenses

Uploads allow only `.pdf`, `.md`, `.markdown`, and `.txt`; size, extension, and PDF magic bytes are checked.
Generated UUID storage keys prevent traversal and collisions. The default data directory is outside the
source tree; operators who override it are responsible for preserving that boundary. PDF
responses are resolved under the upload directory, served same-origin with `nosniff` and `sandbox`, and
never expose an absolute path. Imported HTML is extracted server-side and never returned as HTML. Raw
Markdown HTML is not rendered.

## Prompt injection and providers

Prompts keep system policy separate and serialize the user question and untrusted evidence as JSON data,
so source text cannot close a hand-written prompt delimiter. Source instructions cannot grant tools—the
model has none. Model output must match a strict JSON schema before citation and quotation validation.
These controls reduce risk but cannot guarantee complete prompt-injection resistance. Remote providers
receive selected excerpts and the user question; local provider configuration is disclosed in Settings.
API keys never enter frontend responses or exports.

## Logging and deletion

Structured logs include request IDs, actions, durations, counts, status, IDs, and error types. They omit
full source bodies, complete prompts, questions, private notes, quotations, and credentials.

One process exclusively owns a configured data directory. Project/source deletion atomically moves
referenced uploads into protected same-filesystem staging, commits FTS/database removal, and only then
destroys staged bytes. A database rollback restores staged uploads. If the process stops between those
steps, startup reconciles staging against authoritative source records: referenced files are restored and
committed-away files are finalized.

## Backup and restore

Live backup uses a consistent SQLite snapshot and includes only referenced uploads plus local vector
files. The explicit custom intent header prevents ordinary cross-site form submissions; the response is
marked `no-store`. Backups contain private full source content and are not exports for sharing.

Offline restore treats the ZIP and manifest as hostile. It rejects absolute/traversal paths, backslashes,
duplicate names, directories, symbolic links, encrypted entries, undeclared files, excessive expansion,
size/hash mismatches, corrupt SQLite, and databases missing core CiteTrail tables. Extraction is manual
rather than `extractall`. Existing data is moved aside before the validated replacement is installed and
is retained for rollback. SHA-256 checksums detect accidental or internally inconsistent changes but do
not authenticate the archive creator; storage encryption and access control remain the operator's
responsibility.
