# Contributing to Claudon

Thanks for helping out! Claudon is a single-file, stdlib-only Python tool; please keep it that way (no runtime dependencies).

## Development setup

```bash
git clone https://github.com/infenia/claudon.git && cd claudon
python3 claudon.py ~/.claude -o report.html --open     # run from source
pip install ruff playwright && playwright install chromium
pipx run ruff check .                                   # lint (same as CI)
python -m unittest discover tests                       # tests (tests/test_ui.py needs Playwright)
```

## Pull requests

1. Fork, branch from `main`, make a focused change with tests where it makes sense.
2. **Title your PR as a [Conventional Commit](https://www.conventionalcommits.org/).** PRs are squash-merged, the
   title becomes the commit message, and the release tooling reads it to bump the version and write the changelog.
   CI rejects other titles.

   | Title prefix | Meaning | Release bump |
   |---|---|---|
   | `fix:` | Bug fix | patch |
   | `feat:` | New feature | minor |
   | `feat!:` / `fix!:` or a `BREAKING CHANGE:` footer | Incompatible change | major (minor while `0.x`) |
   | `perf:`, `deps:`, `docs:` | Listed in the changelog | patch |
   | `chore:`, `ci:`, `test:`, `refactor:`, `build:`, `style:` | Internal, no release by themselves | none |

3. **Do not edit the version or `CHANGELOG.md`.** The release PR does that. See [docs/RELEASING.md](docs/RELEASING.md).
4. Keep your branch green: lint, tests on Python 3.11-3.14 and Windows/macOS, and the Node wrapper check.

## Reporting bugs and ideas

Use the [issue templates](https://github.com/infenia/claudon/issues/new/choose). For security problems follow
[SECURITY.md](SECURITY.md) instead. Never attach real session logs; use `--redact` output or a synthetic transcript.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Contributions are licensed under the [MIT License](LICENSE).
