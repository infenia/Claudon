# 🚀 Releasing Claudon

Releases are driven by [Conventional Commits](https://www.conventionalcommits.org/) and
[release-please](https://github.com/googleapis/release-please). Nobody edits version numbers by hand: merged PRs decide
the next version, a bot proposes the release, a maintainer merges it, and the publish workflows run on the new tag with
a human approval gate in front of PyPI.

```
 PR "feat: ..." ──squash──▶ main ──▶ release-please keeps ONE open PR
                                      "chore(main): release 0.2.0"
                                      (bumps claudon/__init__.py + package.json, writes CHANGELOG.md)
                                                │ maintainer reviews + merges
                                                ▼
                       tag v0.2.0 + GitHub Release (notes from the changelog)
                                                │ same workflow dispatches, on the tag:
                     ┌──────────────────────────┴───────────────────────────┐
                     ▼                                                      ▼
   release.yml: preflight → full CI → build                  nuitka-build.yml: binaries, claudon.pyz, SHA256SUMS,
     ├─ PyPI (trusted publishing, `pypi` env approval)         attestations → attached to the Release
     └─ npm (provenance)
```

---

## 📌 Versioning

[SemVer 2.0.0](https://semver.org/), **one version string for every channel**:

- **Stable**: `X.Y.Z` (e.g. `0.2.0`)
- **Prerelease**: `X.Y.Z-alpha.N`, `-beta.N` or `-rc.N` (e.g. `0.2.0-beta.1`)

Valid for npm as-is; PyPI normalises it per PEP 440 (`0.2.0-beta.1` → `0.2.0b1`). Git tags are `v` + version.

The version lives in `claudon/__init__.py` (`__version__`, marked `# x-release-please-version`; `pyproject.toml` reads it
dynamically) and `package.json`. release-please updates both; `scripts/check_version.py` (CI + every publish) fails if
they disagree or the tag doesn't match.

### What a merged PR does

PRs are squash-merged and the **PR title** is the commit (CI enforces the format, see [CONTRIBUTING.md](../CONTRIBUTING.md)).

| Title | Bump (stable) | Bump while `0.x` | In changelog |
|---|---|---|---|
| `fix:` | patch | patch | Bug Fixes |
| `feat:` | minor | minor | Features |
| `feat!:` / `BREAKING CHANGE:` footer | major | minor | Features (flagged) |
| `perf:` / `deps:` / `docs:` | patch | patch | own sections |
| `chore:` `ci:` `test:` `refactor:` `build:` `style:` | none | none | hidden |

Only releasable commits open or update the release PR. To force a specific version, add a `Release-As: 1.0.0` footer to
a commit body that lands on `main`.

---

## 🛠️ Cutting a release

1. **Merge normal PRs.** release-please opens/updates the PR titled `chore(main): release X.Y.Z`.
2. **Review it**: version, `CHANGELOG.md`, and that CI is green (see the token note under setup).
3. **Merge it** (squash). The `Release Please` workflow tags `vX.Y.Z`, creates the GitHub Release, and dispatches
   `release.yml` (`npm_tag=latest`, or `beta` for a tag containing `-`) and `nuitka-build.yml` on the tag.
4. **Approve the PyPI publish** when the `pypi` environment asks for it (*Actions → the run → Review deployments*).
5. **Verify**: `uvx claudon@X.Y.Z --version`, `npx @infenia/claudon@X.Y.Z --version`, and the Release has the 4 binaries, `claudon.pyz` and `SHA256SUMS` (the workflow fails if one is missing), then `curl -fsSL .../install.sh | CLAUDON_VERSION=vX.Y.Z sh && claudon --version`.
   Until `nuitka-build.yml` finishes the new Release has no assets, so `install.sh` fails for that version; re-dispatch it if it failed.

Both publish workflows still require a tag ref, re-check the tag against the package versions, and run the full CI
suite first. Nothing publishes from a branch.

### Beta / release candidates

Set the prerelease strategy in `release-please-config.json` through a normal PR, then merge the release PR it produces:

```json
"prerelease": true, "prerelease-type": "beta", "versioning": "prerelease"
```

The next release is `X.Y.Z-beta.1`, published to npm under `beta` (never `latest`) and marked a GitHub prerelease.
Remove those keys (via another PR) to graduate to a stable release. Testers opt in explicitly:

```bash
uvx --prerelease allow claudon      # or: uvx claudon@0.2.0b1, pip install --pre claudon
npx @infenia/claudon@beta                    # or: bunx @infenia/claudon@beta
```

### Hotfix

Merge a `fix:` PR to `main` and release normally. For a fix to an older line, branch from its tag, cherry-pick, and use
the manual path below with a version that doesn't collide.

---

## 🧰 Manual fallback and re-runs

The publish workflows are plain `workflow_dispatch`, so any step can be repeated on an existing tag:

```bash
gh workflow run release.yml      --ref vX.Y.Z -f npm_tag=latest   # add -f publish_pypi=false or -f publish_npm=false
gh workflow run nuitka-build.yml --ref vX.Y.Z
```

`npm_tag` must be `latest` for a stable tag and something else (`beta`, `next`) for a prerelease; the workflow enforces
this. Use `publish_pypi=false` / `publish_npm=false` to re-run only the registry that failed: **a published version
can never be re-uploaded**, so never re-run a registry that already succeeded.

If release-please itself is unavailable, bump `claudon/__init__.py` and `package.json` in a PR, run `python scripts/check_version.py`,
merge, `git tag vX.Y.Z && git push origin vX.Y.Z`, then dispatch as above.

---

## ⏪ Rollback

Versions are immutable, so roll forward:

- Ship a `fix:` release. Never reuse or retag a version.
- npm: `npm deprecate @infenia/claudon@X.Y.Z "reason, use X.Y.Z+1"`; PyPI: *Manage → Yank release*.
- Edit the GitHub Release to mark it as broken, or delete the binary assets if they are unsafe.

---

## ⚙️ One-Time Repository Setup

- **Repo settings → General**: allow squash merging only, with *Default to pull request title*; enable *Allow GitHub
  Actions to create and approve pull requests* (needed by release-please).
- **`RELEASE_PLEASE_TOKEN` secret (recommended)**: a fine-grained PAT (or GitHub App token) with *Contents* and *Pull
  requests* write. PRs opened with the default `GITHUB_TOKEN` don't trigger CI, so without it the release PR has no
  checks; close and reopen it to run them, or use this token.
- **PyPI trusted publisher**: on PyPI add a (pending) trusted publisher for project `claudon` with owner `infenia`,
  repository `claudon`, workflow `release.yml`, environment `pypi`. No PyPI API token is needed.
- **GitHub environment** `pypi`: create it under *Settings → Environments* and add required reviewers; this is the
  manual approval gate for every PyPI publish.
- **npm**: publish `@infenia/claudon` once by hand (`npm publish --access public`), then add a Trusted Publisher in the package settings (owner `infenia`, repo `claudon`, workflow `release.yml`, no environment). No token or secret is used.
- **macOS signing (optional)**: without these secrets the macOS binaries are built unsigned. With an Apple Developer
  account add `MACOS_CERT_P12` (base64 of the *Developer ID Application* `.p12`), `MACOS_CERT_PASSWORD`,
  `MACOS_SIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID` and `APPLE_APP_PASSWORD`; the workflow then signs and notarizes.
- **Branch protection** on `main`: require pull requests, the CI and `PR title` status checks, and *Require branches to
  be up to date before merging*.

---

## 🩺 Troubleshooting

| Symptom | Fix |
|---|---|
| No release PR appears | No releasable commit since the last tag (`chore:`/`ci:` don't count), or the Actions PR setting above is off. |
| Release PR has no CI checks | It was opened by `GITHUB_TOKEN`; set `RELEASE_PLEASE_TOKEN` or close/reopen the PR. |
| Merged release PR but nothing published | Check the `Release Please` run's dispatch step; re-run the manual commands above on the tag. |
| `release.yml` fails at preflight | Tag doesn't match `claudon/__init__.py`/`package.json`, or wrong `npm_tag` for the tag type. |
| PyPI step waits forever | It is waiting for the `pypi` environment approval. |
