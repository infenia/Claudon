<div align="center">

# Claudon

**See where your Claude Code time and money actually go.**

One command turns your session logs into an interactive HTML dashboard.<br>
100% local · zero dependencies · nothing leaves your machine.

[![CI](https://github.com/infenia/claudon/actions/workflows/ci.yml/badge.svg)](https://github.com/infenia/claudon/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/claudon?label=PyPI)](https://pypi.org/project/claudon/)
[![npm](https://img.shields.io/npm/v/@infenia/claudon)](https://www.npmjs.com/package/@infenia/claudon)
[![Python](https://img.shields.io/pypi/pyversions/claudon?label=Python)](https://pypi.org/project/claudon/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

```bash
uvx claudon --open
```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/demo-dark.webp">
  <img loading="lazy" decoding="async" src="docs/assets/demo-light.webp" alt="Claudon dashboard tour: overview, tasks, tools, models and bottlenecks" width="860">
</picture>

<sub>Redacted sample. Your own sessions stay on your machine.</sub>

[Quick start](#quick-start) · [In the browser](#in-the-browser-no-install) · [Usage](#usage) · [On-device AI](#on-device-ai-optional) · [Privacy](#privacy) · [Contributing](#contributing)

</div>

---

## Why Claudon?

Claude Code is fast until it isn't. Which turn burned ten minutes? Was it the model, a slow tool, or you being away? Did a failing tool call loop? What did the session really cost?

The answers are already in `~/.claude`. Claudon reads them and shows you:

| | |
|---|---|
| **Where time went** | model vs. tools vs. permission waits vs. idle, per task, turn and subagent |
| **What it cost** | token usage × list prices per model generation (override with `--pricing`) |
| **What went wrong** | ranked findings with a concrete fix each: tool failures and retry loops, permission-prompt waits, expired prompt caches, repeated reads, edit churn, context bloat, trends |
| **How hard it thought** | thinking time vs. thinking tokens |
| **What to fix first** *(optional AI)* | an AI summary on the Overview and an **Ask AI** chat, run by your browser's on-device model, [only in browsers that support it](#on-device-ai-optional) |
| **Safe to share** | `--redact` strips prompts, paths, commands and project names |

It is a small Python package using only the standard library. No telemetry, no network, no account.

---

## Quick start

Run it with whichever tool you already have. Each one downloads the latest release on demand.

| Tool | Run once | Install globally |
|---|---|---|
| **uv** | `uvx claudon` | `uv tool install claudon` |
| **pipx** | `pipx run claudon` | `pipx install claudon` |
| **pip** | | `pip install claudon` |
| **npm** | `npx @infenia/claudon` | `npm install -g @infenia/claudon` |
| **pnpm** | `pnpm dlx @infenia/claudon` | `pnpm add -g @infenia/claudon` |
| **Yarn** (2+) | `yarn dlx @infenia/claudon` | |
| **Bun** | `bunx @infenia/claudon` | `bun add -g @infenia/claudon` |

After a global install:

```bash
claudon ~/.claude -o report.html --open
```

> **Requirements:** Python 3.11+ on your `PATH` (`python3`, `python` or `py`). The npm-family packages are a thin
> launcher around the same Python script. No Python? Use the [browser version](#in-the-browser-no-install) or a
> standalone binary from [GitHub Releases](https://github.com/infenia/claudon/releases).

<details>
<summary><b>Other ways to install</b> (shell script, git clone, pre-releases)</summary>

### Shell script

```bash
curl -fsSL https://raw.githubusercontent.com/infenia/claudon/main/install.sh | sh

# recommended: pin a release (see GitHub Releases); the download is checked against that release's SHA256SUMS
curl -fsSL https://raw.githubusercontent.com/infenia/claudon/main/install.sh | CLAUDON_VERSION=vX.Y.Z sh
```

The script installs the native binary for your platform (Linux x86_64, macOS arm64/Intel, Windows x86_64 via Git Bash or
MSYS2), so **Python is not needed**. Other platforms (Linux arm64, Alpine/musl) get `claudon.pyz`, which needs Python 3.11+.

On Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/infenia/claudon/main/install.ps1 | iex
# pin a release: $env:CLAUDON_VERSION = 'vX.Y.Z' first
```
 The checksum catches corrupted or mismatched downloads. To
also prove a release file was built by this repo's workflow, download it and run
`gh attestation verify <file> -R infenia/claudon`.

### Git clone

```bash
git clone https://github.com/infenia/claudon.git
cd claudon
python3 -m claudon ~/.claude -o report.html --open
```

### Pre-releases

```bash
uvx --prerelease allow claudon
npx @infenia/claudon@beta
```

</details>

---

## In the browser (no install)

Claudon also runs entirely in your browser, with no local Python.

- **Live app:** [claudon.infenia.com/app](https://claudon.infenia.com/app/)
- **Locally:** from the repository root run `python3 -m http.server`, then open `http://localhost:8000/wasm/`.

Drop `.jsonl` transcripts onto the page, or use **Open Folder** on `~/.claude/projects` to keep project grouping and subagents.
The optional [AI summary and Ask AI](#on-device-ai-optional) work here too, in browsers that support the built-in AI APIs.

---

## Use it inside Claude Code

```bash
claudon --install-plugin
```

Then type `/claudon` in any Claude Code session to generate and open your dashboard.

---

## Usage

```bash
claudon [PATH] [-o FILE] [--redact] [--pricing FILE] [--open] [--install-plugin [--force]] [--version]
```

`PATH` can be a `~/.claude` directory, its `projects/` subfolder, a specific project directory, or a single `.jsonl`
transcript. The default is `$CLAUDE_CONFIG_DIR` if set, else `~/.claude`.

| Flag | Description |
|---|---|
| `-o FILE`, `--out FILE` | Output HTML report path (default: `cc_report.html`) |
| `--redact` | Redact prompts, titles, project names, paths, commands, session IDs and MCP server names, for safe sharing |
| `--pricing FILE` | Custom $/MTok rates keyed by model-id substring (longest match wins): `{"claude-opus-4-1": [input, output, cache_read, write_5m, write_1h]}` |
| `--open` | Open the generated report in your default browser |
| `--install-plugin` | Register the `/claudon` slash command in `<config dir>/commands/` |
| `--force` | With `--install-plugin`: overwrite a `claudon.md` you have edited (otherwise it is left alone) |
| `--version` | Print the version |

**Common recipes**

```bash
claudon --open                                  # analyze everything, open the report
claudon ~/.claude/projects/my-project --open    # one project only
claudon --redact -o share-me.html               # safe to attach to an issue
```

### What's in the report

| Tab | What it shows | Works in |
|---|---|---|
| **Overview** | KPIs, where the wall-clock time goes, per-task distribution, cost per day, per project and by token type | any modern browser |
| **Tasks** | every human prompt through to completion; click one for its timeline, tools, context growth and signals | any modern browser |
| **Tools** | time, errors and rejections per tool, plus the slowest individual calls | any modern browser |
| **Models & thinking** | calls, cost, speed and thinking per model | any modern browser |
| **Bottlenecks** | findings ranked worst first, each with the time and spend at stake, why it matters and how to fix it | any modern browser |
| Overview → **AI summary** | a headline, where the time and money go, and the fixes to do first (each opens its finding in Bottlenecks) | [browsers with built-in AI only](#on-device-ai-optional) |
| **Ask AI** | chat about the sessions in view | [browsers with the Prompt API only](#on-device-ai-optional) |

The report is one self-contained `.html` file: no server, no external assets.

#### The Bottlenecks findings

Every finding is computed exactly from the transcripts (no AI involved) and comes with a **Fix** line:

- **Idle time** and **permission-prompt waits** (Read/Edit/Write calls that sat waiting for your approval)
- **Failing tools**, and tasks **stuck retrying** the same failing step
- **Repeated identical reads/searches** and **edit churn** (the same file edited 10+ times)
- **Context bloat** past 400k tokens, **expired prompt caches** after a 5+ minute pause, and a high **cache-write** share
- **Interrupts and rejected tool calls**, **heavy thinking**, and **subagent** cost share
- Tasks with **unusually many turns** for their project, **cost concentration**, and **trends** (earlier vs. later tasks)

Filters (project, search) apply to every finding. The thresholds live in one `RULES` object in
`claudon/dashboard.html`.

---

## On-device AI (optional)

> [!IMPORTANT]
> **The AI features work only if your browser supports the built-in AI APIs** (Chrome's
> [Prompt API](https://developer.chrome.com/docs/ai/prompt-api) or
> [Summarizer API](https://developer.chrome.com/docs/ai/summarizer-api)) **and your computer meets that browser's
> hardware requirements.** Otherwise the AI summary and the Ask AI tab are hidden. Everything else, including all the
> Bottlenecks findings, works in any modern browser.

When your browser can run its own built-in language model, the report adds:

- **AI summary** (Overview tab, under the KPIs): a headline, where the time and money go, and up to four priorities.
  Each priority opens the Bottlenecks finding it is based on.
- **Ask AI** (its own tab, Prompt API only): chat about the sessions in view, e.g. *"Why was yesterday slow?"*,
  *"Which tools fail most?"* or *"What did expired caches cost me?"*. Tasks the answer cites become clickable, and
  *Data the model saw* shows exactly what it was given. The chat is kept in your browser's local storage (per report)
  until you press *Clear chat*.

**Which browsers**

| Browser | AI summary | Ask AI |
|---|---|---|
| Chrome 148+ (desktop) | ✅ Prompt API | ✅ |
| Chrome 138–147 (desktop) | ✅ Summarizer API | ❌ needs the Prompt API |
| Microsoft Edge (desktop) | ✅ Summarizer API | ⚙️ enable `edge://flags` → *Prompt API for on-device language model* |
| Firefox, Safari, mobile browsers | ❌ hidden | ❌ hidden |
| Any browser that later ships the same standard `LanguageModel` / `Summarizer` APIs | ✅ automatically | ✅ automatically |

Support is detected by asking the browser itself (`LanguageModel.availability()` / `Summarizer.availability()`), never
from its name, so new browsers work as soon as they ship the APIs.

**Hardware.** Chrome runs Gemini Nano on Windows 10/11, macOS 13+, Linux or ChromeOS (Chromebook Plus). It needs about
22 GB of free disk, plus either a GPU with more than 4 GB of VRAM or 16 GB of RAM and 4 CPU cores. Edge has similar
requirements for its Phi model. If the browser reports that the device can't run the model, the AI features stay
hidden. Check the model's state at `chrome://on-device-internals` (Edge: `edge://on-device-internals`).

**First use.** The browser may need to download its model once (a few GB). Claudon never starts that download on its
own: it shows **Enable on-device AI**, and the browser downloads its model only after you click. After that the model
runs locally and keeps working offline.

**Where it works**

- A report the CLI wrote, opened from disk (`file://`)
- The [browser app](#in-the-browser-no-install), whose report frame is allowed to use the AI APIs
- A report saved from the browser app

**How it stays accurate.** The AI never computes numbers. It is given the findings and report data (already-formatted
figures), is told to use only that data, and can only point at findings that exist. Its output is shown as plain text.
For chat, the data for each question is picked by fixed rules (the tasks, projects, tools, dates and metric it
mentions), not by the model. The numbers in the findings are always exact; treat the AI's wording as a summary.

**Not seeing it?** Your browser doesn't expose the APIs, the device doesn't meet the requirements, or (Edge) the
Prompt API flag is off. The [live check](https://claudon.infenia.com/) on the project page tells you which features
your current browser supports.

---

## Privacy

Everything runs on your machine. The CLI makes no network requests, and neither does the report page. The optional
[AI summary and Ask AI chat](#on-device-ai-optional) use the browser's own on-device model, so your data never leaves
your computer for them either. If the browser still has to fetch that model, it does so itself, and only after you
click *Enable on-device AI*. Chat history stays in your browser's local storage until you clear it.

The browser version uploads nothing either: files are read and analyzed locally. Its only downloads are the Pyodide
runtime (from jsDelivr) and `claudon.pyz`, and once it shows *Ready* it keeps working offline. Chrome and Edge ask to
let the page *view* the folder you pick. Firefox and Safari show their own "upload" prompt for folder pickers, which
only grants the page read access.

---

## Releases

Claudon follows [Semantic Versioning](https://semver.org/). Conventional Commit PR titles drive an auto-generated
release PR (version bump + [CHANGELOG](CHANGELOG.md)); merging it tags the release and publishes:

- **PyPI** (trusted publishing) and **npm** (with provenance)
- **Standalone binaries** for Linux x86_64, macOS (arm64 and Intel) and Windows, on GitHub Releases with `SHA256SUMS`
  and build provenance attestations (`gh attestation verify <file> -R infenia/claudon`), plus `claudon.pyz`
  (single-file Python bundle, used by `install.sh` where no binary exists)

Full process: [docs/RELEASING.md](docs/RELEASING.md).

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) (PR titles must be
[Conventional Commits](https://www.conventionalcommits.org/)) and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Report vulnerabilities privately per [SECURITY.md](SECURITY.md).

## License

Developed by **Infenia Private Limited**. MIT License. See [LICENSE](LICENSE).
