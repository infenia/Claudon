# 🚀 Release Process, Manual Triggers & Beta Testing Guide

This document describes the release procedures, manual workflow dispatch triggers, semantic versioning standards, and beta testing best practices for **Claudon**.

---

## 📌 Release Strategy & Semantic Versioning

Claudon follows [Semantic Versioning (SemVer 2.0.0)](https://semver.org/):

- **Stable Releases**: `vMAJOR.MINOR.PATCH` (e.g. `v0.1.0`, `v1.0.0`)
- **Beta / Pre-releases**: `vMAJOR.MINOR.PATCH-beta.1` or `vMAJOR.MINOR.PATCHb1` (e.g. `v0.2.0b1` or `v1.0.0-rc1`)

---

## 🔒 Strictly Manual Release Workflows

To prevent accidental deployments, **all release workflows are strictly manually triggered (`workflow_dispatch`)**. No packages or binaries are ever published automatically on git push or tag creation.

Releases can be triggered manually in two ways:
1. **GitHub Actions Web UI**: Navigate to the **Actions** tab on GitHub, select the workflow, and click **Run workflow**.
2. **GitHub CLI (`gh`)**:
   ```bash
   gh workflow run "Manual Publish Release (PyPI & npm)" -f npm_tag=latest
   gh workflow run "Manual Nuitka Build & Release Standalone Binaries" -f tag_name=v0.1.0
   ```

---

## 🧪 Best Practices for Beta Testing & Pre-releases

When releasing beta features or testing release candidates across package managers:

### 1. PyPI (`uvx` / `pipx` / `pip`)
- **Version Convention**: Use PEP 440 pre-release notation in `pyproject.toml` (e.g., `version = "0.2.0b1"`).
- **Behavior**: Standard users running `uvx claudon` or `pip install claudon` will automatically receive the **latest stable release**.
- **Beta Testers**: Testers opt-in to beta releases using:
  ```bash
  # Test beta via uvx
  uvx claudon --pre

  # Test beta via pipx
  pipx run --spec claudon==0.2.0b1 claudon

  # Test beta via pip
  pip install --pre claudon
  ```

### 2. npm (`npx` / `bunx`)
- **Dist-Tag Convention**: Set `"version": "0.2.0-beta.1"` in `package.json`. When triggering the release workflow, set `npm_tag` to `beta`.
- **Behavior**: Standard users running `npx claudon` or `bunx claudon` receive the `@latest` release.
- **Beta Testers**: Testers opt-in to beta releases using:
  ```bash
  # Test beta via npx
  npx claudon@beta

  # Test beta via bunx
  bunx claudon@beta
  ```

### 3. Nuitka Native Binaries (GitHub Releases)
- **Workflow Inputs**: Set `tag_name` to the release tag (e.g., `v0.2.0b1`) and check `is_prerelease` to `true`.
- **Behavior**: GitHub creates a **Prerelease** entry with pre-compiled native binaries attached for Linux, macOS, and Windows.

---

## 🛠️ Step-by-Step Release Checklist

### 1. Bump Version in Files
Update version strings in both configuration files:
- `pyproject.toml` (`version = "X.Y.Z"`)
- `package.json` (`"version": "X.Y.Z"`)

### 2. Commit & Tag
```bash
git add pyproject.toml package.json
git commit -m "chore: bump version to vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
```

### 3. Trigger Manual Workflow
1. Go to **Actions** -> **Manual Publish Release (PyPI & npm)** -> **Run workflow**. Select `npm_tag` (`latest` for stable, `beta` for beta testing).
2. Go to **Actions** -> **Manual Nuitka Build & Release Standalone Binaries** -> **Run workflow**. Enter tag name and toggle `is_prerelease` if applicable.
