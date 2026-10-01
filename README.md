# Claudon 📊

> Interactive session analytics and HTML dashboard for **Claude Code**.

**Claudon** turns your Claude Code session logs (`.jsonl`) into a single, self-contained interactive HTML dashboard. Gain full visibility into turn duration, wall time breakdown (model vs. tools vs. idle), tool call failures, thinking tokens & time, cost estimates, and auto-detected performance bottlenecks.

Runs 100% locally with zero dependencies (Python stdlib only). Your private logs and code never leave your machine.

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
curl -fsSL https://raw.githubusercontent.com/claudon/claudon/main/install.sh | sh
```

### Direct Clone
```bash
git clone https://github.com/claudon/claudon.git
cd claudon
python3 claudon.py ~/.claude -o report.html --open
```

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
claudon [PATH] [-o FILE] [--redact] [--pricing FILE] [--open] [--install-plugin]
```

`PATH` can be a `~/.claude` directory, its `projects/` subfolder, a specific project directory, or a single `.jsonl` transcript file (default: `~/.claude`).

| Flag | Description |
|---|---|
| `-o FILE`, `--output FILE` | Output HTML report file path (default: `cc_report.html`) |
| `--redact` | Redact prompts, project names, paths, and commands for safe report sharing |
| `--pricing FILE` | Custom JSON pricing rates: `{"sonnet": [input, output, cache_read, write_5m, write_1h]}` |
| `--open` | Automatically open the generated HTML report in your default browser |
| `--install-plugin` | Register `/claudon` slash command in `~/.claude/commands/` |

---

## 📊 What's in the Report?

- **Task Breakdown**: Individual human prompts to final completion.
- **Turns & Subagents**: Model API calls vs agent delegation.
- **Time Analysis**: Model latency, tool execution, user permission waits, idle silence.
- **Thinking Metrics**: Thinking time vs thinking tokens.
- **Cost Estimation**: Accurate cost calculation based on Anthropic token pricing.
- **Bottlenecks**: Automatic detection of tool failures, slow turns, and loops.
- **Privacy First**: Fully local parsing and HTML generation; `--redact` option for public sharing.

---

## 📄 License

Developed by **Infenia Private Limited**. MIT License. See [LICENSE](LICENSE) for details.
