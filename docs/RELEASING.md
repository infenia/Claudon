# 🚀 Release Process, Manual Triggers & Beta Testing Guide

This document describes how **Claudon** is versioned, released and beta-tested.

---

## 📌 Versioning

Claudon follows [Semantic Versioning (SemVer 2.0.0)](https://semver.org/), with **one version string** for every channel:

- **Stable**: `X.Y.Z` (e.g. `0.1.0`, `1.0.0`)
- **Prerelease**: `X.Y.Z-alpha.N`, `X.Y.Z-beta.N` or `X.Y.Z-rc.N` (e.g. `0.2.0-beta.1`)

That string is valid for npm as-is, and PyPI normalises it per PEP 440 (`0.2.0-beta.1` → `0.2.0b1`), so no
per-registry spelling is needed. Git tags are the version prefixed with `v` (`v0.2.0-beta.1`).

The version lives in exactly two files, and `scripts/check_version.py` (run in CI and before every release) fails
if they disagree or the tag doesn't match:

- `claudon.py` → `__version__` (`pyproject.toml` reads it dynamically)
- `package.json` → `"version"`

---

## 🔒 Strictly Manual, Tag-Only Release Workflows

No package or binary is ever published automatically on push or tag creation. Both release workflows are
`workflow_dispatch` only, **must be dispatched on a release tag** (they fail on a branch), re-check the tag against
the versions above, and run the full CI suite before publishing.

| Workflow | Publishes |
|---|---|
| `release.yml` — Publish Release (PyPI & npm) | PyPI (trusted publishing) and npm (with provenance) |
| `nuitka-build.yml` — Build & Release Standalone Binaries | GitHub Release with Linux / macOS arm64 + Intel / Windows binaries, `SHA256SUMS` and build provenance attestations; tags containing `-` become prereleases |

---

## 🛠️ Step-by-Step Release Checklist

### 1. Bump the version
Set the same version in `claudon.py` (`__version__ = "X.Y.Z"`) and `package.json` (`"version": "X.Y.Z"`), then:
```bash
python scripts/check_version.py
```

### 2. Merge, then tag the merged commit
```bash
git switch -c release/vX.Y.Z
git commit -am "chore: bump version to X.Y.Z"
git push -u origin release/vX.Y.Z      # open a PR, wait for CI, merge
git switch main && git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

### 3. Dispatch the workflows on the tag
```bash
gh workflow run release.yml      --ref vX.Y.Z -f npm_tag=latest
gh workflow run nuitka-build.yml --ref vX.Y.Z
```
Or in the **Actions** tab: pick the workflow → **Run workflow** → choose the tag (not a branch) under *Use workflow from*.

---

## 🧪 Beta Testing & Pre-releases

Tag `vX.Y.Z-beta.N` and dispatch `release.yml` with `npm_tag=beta` (the workflow refuses to put a prerelease on
`latest`). `nuitka-build.yml` marks the GitHub Release as a prerelease automatically.

Regular users keep getting the latest stable release; testers opt in explicitly:

```bash
# PyPI (version as normalised by PyPI)
uvx claudon@0.2.0b1
uvx --prerelease allow claudon
pipx run --spec claudon==0.2.0b1 claudon
pip install --pre claudon

# npm
npx claudon@beta
bunx claudon@beta
```

---

## ⚙️ One-Time Repository Setup

- **PyPI trusted publisher**: on PyPI, add a (pending) trusted publisher for project `claudon` with owner `infenia`,
  repository `Claudon`, workflow `release.yml`, environment `pypi`. No PyPI API token is needed.
- **GitHub environment** `pypi`: create it under *Settings → Environments*; adding required reviewers gives every
  PyPI publish a manual approval gate.
- **npm**: add an automation token as the `NPM_TOKEN` repository secret.
- **Branch protection** on `main`: require pull requests, the CI status checks, and *Require branches to be up to
  date before merging*, so a stale branch can't silently revert merged work.
