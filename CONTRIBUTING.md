# Contributing to CiteTrail

Thank you for improving provenance-first research software.

Use a short branch name such as `feature/pdf-location`, `fix/redirect-validation`, or
`docs/provider-privacy`. Keep pull requests focused and explain the research/security behavior they
change.

Before opening a pull request:

1. Run backend and frontend tests, lint, type checks, and the production build.
2. Add tests for successful, warning, empty, failure, and boundary behavior.
3. Preserve source ID and location through any extraction, normalization, chunking, retrieval, evidence,
   timeline, citation, brief, or export change.
4. Never construct authoritative citation metadata from model text. Verify excerpts and quotations against
   stored source content.
5. Treat every URL, redirect, DNS answer, file, extracted instruction, and model response as untrusted.
   Security-sensitive changes need abuse-case tests and corresponding security documentation.
6. Update user, architecture, provenance, citation, retrieval, or troubleshooting documentation whenever
   behavior changes.
7. Do not commit secrets, `.env`, uploads, local databases, source bodies, or private research projects.

Pull requests should state motivation, implementation, risk, test evidence, migration impact, screenshots
only when real, and any remaining limitation. Maintainers may request smaller commits or a threat-model
note for network, parsing, rendering, deletion, or provider changes.
