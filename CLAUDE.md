# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Claudon turns Claude Code session transcripts (`~/.claude/projects/**/*.jsonl`) into a self-contained HTML analytics dashboard. **Stdlib-only Python (3.11+) package `claudon/`** — do not add runtime dependencies.

## Commands

```bash
python3 -m claudon ~/.claude -o report.html --open   # run from source
pipx run ruff==0.16.9 check .                         # lint (CI pins this version; only F + E9 rules)
python -m unittest discover tests                     # all tests (test_ui.py skips itself without Playwright)
python -m unittest tests.test_claudon.SomeClass.test_x  # single test
python tests/test_golden.py --update                  # regenerate tests/golden.json (only for intentional output changes)
python scripts/check_version.py                       # claudon.__version__ must equal package.json version
python scripts/build_zipapp.py                        # -> dist/claudon.pyz (single runnable file)
npm test                                              # smoke-tests the Node launcher (node bin/claudon.js --help)
```

UI tests need `pip install playwright && playwright install chromium`.

## Architecture

Pipeline in `claudon/`: `transcript` (tolerant JSONL parsing, prompts, token usage) → `analyze.analyze_session` (per session: `_load_records` → `_build_calls` → `_task_starts` → `_bucket` → `_summarise_task`; splits tasks on `IDLE_SPLIT` idle gaps, attributes wall time to model/thinking/tool/agent/user-wait, prices tokens via `pricing`) → `discover.build` (walks the tree, groups main + `subagents/` files, dedupes forked history via `seen_msgs`) → optional `redaction.redact` → `render.render_html`, which injects the data JSON into `dashboard.html` (the whole dashboard UI: HTML/CSS/JS in one real file). `cli.main` wires it together. `claudon/__init__.py` re-exports `build`, `redact`, `render_html`, `main` (the WASM worker calls them).

- Task/model/tool-stat rows are positional arrays that `dashboard.html` reads by index; the layouts are the `M_*` / `T_*` constants in `analyze.py`. Change them together with the JS. `tests/golden.json` pins the output on `tests/fixtures/`.
- `dashboard.html` also holds the findings engine (`findings()`, thresholds in `RULES`) and the optional on-device AI
  (`aiDetect`/`aiSummarize`): it feature-detects the browser's `LanguageModel` / `Summarizer` globals, grounds the model
  on `facts()` built from the findings, and stays hidden when neither is available. No AI code in the Python package.
- `bin/claudon.js`: thin Node launcher; probes for Python ≥3.11 and runs `python -m claudon` with `PYTHONPATH` set to the package root (npm ships `claudon/`).
- `scripts/build_zipapp.py` builds `claudon.pyz`, the single-file artifact used by `install.sh` (SHA256-verified GitHub Release asset, attached by `nuitka-build.yml`) and by the WASM page.
- `wasm/` (`index.html` + `worker.js`): runs the package unchanged in Pyodide in a Web Worker (zipimport of `claudon.pyz`); files never leave the browser. `deploy-pages.yml` builds the pyz into `_site/app/` next to `wasm/*`, plus `site/index.html` + README at the Pages root.
- `scripts/build_nuitka.py` (via `scripts/nuitka_entry.py`, run by the manually dispatched `nuitka-build.yml`): native binaries. Not covered by PR CI.
- `--install-plugin` writes a `/claudon` slash command into the Claude config dir.

## Release & conventions

- One version, two registries: `__version__` in `claudon/__init__.py` (line tagged `# x-release-please-version`) and `package.json` (PyPI `claudon`, npm `@infenia/claudon`). **Never edit versions or `CHANGELOG.md` by hand** — release-please does it from the release PR; see `docs/RELEASING.md`.
- PRs are squash-merged and the **PR title must be a Conventional Commit** (`fix:` → patch, `feat:` → minor; `chore:/ci:/test:/refactor:` don't release). CI (`pr-title.yml`) rejects others.
- `.gitignore` ignores `*.html` (generated reports); `claudon/dashboard.html` and `wasm/index.html` are un-ignored — keep it that way for new tracked HTML.
- Workflow actions are pinned by commit SHA; npm and PyPI publish via trusted publishing (OIDC), no long-lived tokens.
- Never put real session logs in issues/tests/fixtures; use synthetic transcripts or `--redact` output.
