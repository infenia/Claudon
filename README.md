# Claudon 📊

> Interactive session analytics and HTML dashboard for **Claude Code**.

**Claudon** turns your Claude Code session logs (`.jsonl`) into a single, self-contained interactive HTML dashboard. Gain full visibility into turn duration, wall time breakdown (model vs. tools vs. idle), tool call failures, thinking tokens & time, cost estimates, and auto-detected performance bottlenecks.

Runs 100% locally with zero dependencies (Python 3.11+ stdlib only). Your private logs and code never leave your machine.

---

## 🚀 Quick Start (Run Anywhere)

You can run **Claudon** instantly through your favorite package manager or launcher:

### Python (`uvx`, `pipx`, `pip`)
```bash
# Instant run via uv (recommended)
uvx claudon

# Instant run via pipx
pipx run claudon

# Or install via pip
pip install claudon
claudon ~/.claude -o report.html --open
```

### Node.js / JavaScript (`npx`, `bunx`)
```bash
# Instant run via npx
npx claudon

# Instant run via bunx
bunx claudon
```

### Standalone Shell Script
```bash
curl -fsSL https://raw.githubusercontent.com/infenia/Claudon/main/install.sh | sh

# recommended: pin a release (see GitHub Releases); claudon.py is checked against that release's SHA256SUMS
curl -fsSL https://raw.githubusercontent.com/infenia/Claudon/main/install.sh | CLAUDON_VERSION=vX.Y.Z sh
```
The checksum catches corrupted or mismatched downloads. To also prove a release file was built by this repo's
workflow, download it and run `gh attestation verify claudon.py -R infenia/Claudon`.

### Direct Clone
```bash
git clone https://github.com/infenia/Claudon.git
cd Claudon
python3 claudon.py ~/.claude -o report.html --open
```

### ⚡ WebAssembly (In-Browser / Zero Python)
Run Claudon entirely in your browser without local Python installed. The page loads `../claudon.py`,
so it has to be served over HTTP (opening the file directly via `file://` can't load it):
1. From the repository root run `python3 -m http.server` (or host the repo on any static server, e.g. GitHub Pages).
2. Open `http://localhost:8000/wasm/`.
3. Drop `.jsonl` transcripts, or use **Browse Folder** on `~/.claude/projects` to keep project grouping and subagents.

Transcripts are processed in the browser; only the Pyodide runtime is downloaded from jsDelivr.

### 🛠️ Native Compilation (Nuitka) & Semantic Releases
To compile Claudon into a single native binary locally:
```bash
pip install nuitka==4.2.2 zstandard
python scripts/build_nuitka.py --onefile
```
Standalone executables are output to `dist/`.

#### 📦 Release & Distribution Channels
Claudon follows **Semantic Versioning** (`vX.Y.Z`, prereleases `vX.Y.Z-beta.N`). Releases are never automatic: after pushing a tag, a maintainer dispatches the release workflows on that tag. They run the full test suite, check the tag against the package versions, and publish:
- **Nuitka Binaries**: Standalone executables for Linux x86_64, macOS (arm64 and Intel) and Windows, attached to GitHub Releases with `SHA256SUMS` and build provenance attestations (`gh attestation verify <file> -R infenia/Claudon`). macOS binaries are signed and notarized when the maintainers' Apple signing secrets are configured.
- **PyPI Package**: Published to PyPI for instant execution via `uvx claudon`, `pipx run claudon`, or `pip install claudon`.
- **npm Package**: Published to npm registry for instant execution via `npx claudon` or `bunx claudon`.

See [docs/RELEASING.md](docs/RELEASING.md) for full release process instructions.

---

## ⚡ Integration with Claude Code

Install Claudon as a native slash command inside Claude Code:

```bash
claudon --install-plugin
```

Once installed, simply type `/claudon` in any active Claude Code CLI session to instantly generate and open your analytics dashboard!

---

## ⚙️ Options & CLI Usage

```bash
claudon [PATH] [-o FILE] [--redact] [--pricing FILE] [--open] [--install-plugin [--force]] [--version]
```

`PATH` can be a `~/.claude` directory, its `projects/` subfolder, a specific project directory, or a single `.jsonl` transcript file (default: `$CLAUDE_CONFIG_DIR` if set, else `~/.claude`).

| Flag | Description |
|---|---|
| `-o FILE`, `--out FILE` | Output HTML report file path (default: `cc_report.html`) |
| `--redact` | Redact prompts, titles, project names, paths, commands, session IDs and MCP server names for safe report sharing |
| `--pricing FILE` | Custom $/MTok rates keyed by model-id substring (longest match wins): `{"claude-opus-4-1": [input, output, cache_read, write_5m, write_1h]}` |
| `--open` | Automatically open the generated HTML report in your default browser |
| `--install-plugin` | Register `/claudon` slash command in `<config dir>/commands/` |
| `--force` | With `--install-plugin`: overwrite a `claudon.md` you have edited (otherwise it is left alone) |
| `--version` | Print the version |

---

## 📊 What's in the Report?

- **Task Breakdown**: Individual human prompts to final completion.
- **Turns & Subagents**: Model API calls vs agent delegation.
- **Time Analysis**: Model latency, tool execution, user permission waits, idle silence.
- **Thinking Metrics**: Thinking time vs thinking tokens.
- **Cost Estimation**: Estimated from token usage × Anthropic list prices per model generation (override with `--pricing`).
- **Bottlenecks**: Automatic detection of tool failures, slow turns, and loops.
- **Privacy First**: Fully local parsing and HTML generation; `--redact` option for public sharing.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
