# 🚀 Release Process & Semantic Versioning

This document describes the semantic versioning convention and release procedures for **Claudon**.

---

## 📌 Semantic Versioning Overview

Claudon follows [Semantic Versioning (SemVer 2.0.0)](https://semver.org/):

`vMAJOR.MINOR.PATCH` (e.g. `v0.1.0`, `v1.0.0`)

- **MAJOR** (`X.0.0`): Incompatible API or structural changes.
- **MINOR** (`0.X.0`): New features, CLI flags, dashboard additions, or backwards-compatible enhancements.
- **PATCH** (`0.0.X`): Backwards-compatible bug fixes, performance improvements, and minor internal corrections.

---

## 🛠️ Step-by-Step Release Checklist

### 1. Update Version in Core Config Files
Before cutting a release tag, ensure the version string is bumped in both distribution metadata files:

- **Python (`pyproject.toml`)**:
  ```toml
  [project]
  version = "X.Y.Z"
  ```

- **Node.js (`package.json`)**:
  ```json
  {
    "version": "X.Y.Z"
  }
  ```

### 2. Commit Version Updates
```bash
git add pyproject.toml package.json
git commit -m "chore: bump version to vX.Y.Z"
git push origin main
```

### 3. Create and Push Semantic Release Tag
Cutting a git tag matching `v*` initiates the automated multi-ecosystem release pipeline:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

---

## ⚙️ Automated GitHub Actions CI/CD Pipeline

When a `v*` tag is pushed to GitHub, two automated GitHub Actions workflows execute in parallel:

### 1. Nuitka Native Executables (`.github/workflows/nuitka-build.yml`)
- Compiles `claudon.py` into standalone native binaries on Linux (`claudon-linux-x86_64`), macOS (`claudon-macos-x86_64`), and Windows (`claudon-windows-x86_64.exe`).
- Attaches the pre-compiled native binaries directly to the GitHub Release.

### 2. Multi-Ecosystem Packages (`.github/workflows/release.yml`)
- **PyPI Distribution**: Builds Python wheels/sdists and publishes to PyPI (enabling instant run via `uvx claudon`, `pipx run claudon`, and `pip install claudon`).
- **npm Registry**: Publishes Node launcher package to npm (enabling instant run via `npx claudon` and `bunx claudon`).
