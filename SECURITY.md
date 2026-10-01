# Security Policy

## Supported versions

Only the latest release on PyPI / npm receives fixes.

## Reporting a vulnerability

Please **do not open a public issue**. Report privately through
[GitHub Security Advisories](https://github.com/infenia/claudon/security/advisories/new) or email
engineering@infenia.com. We aim to acknowledge reports within 3 business days and will coordinate a fix and
disclosure with you.

## Scope

Claudon runs locally and makes no network requests (the optional WebAssembly page only downloads the Pyodide runtime).
Relevant issues include crafted `.jsonl` transcripts that execute code or escape the generated HTML (XSS), `--redact`
leaking data it should hide, and weaknesses in the install script or release pipeline.

Releases are published from GitHub Actions with PyPI trusted publishing, npm provenance, `SHA256SUMS` and build
attestations (`gh attestation verify <file> -R infenia/claudon`).
