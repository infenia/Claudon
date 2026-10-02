"""Claudon - Claude Code session analytics -> self-contained HTML dashboard.

  claudon [PATH] [-o report.html] [--pricing prices.json] [--redact] [--open] [--install-plugin]

PATH: a ~/.claude dir, its projects/ dir, one project dir, or a single .jsonl
(default $CLAUDE_CONFIG_DIR, else ~/.claude).
Stdlib only. Everything is derived from the transcripts; see the notes in the dashboard footer.
"""
import argparse, os, sys, webbrowser
from pathlib import Path

from . import __version__
from .discover import build
from .pricing import PRICE, load_pricing
from .redaction import redact
from .render import render_html


def config_dir():
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or '~/.claude').expanduser()


def install_plugin(force=False):
    cmd_dir = config_dir() / 'commands'
    cmd_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = cmd_dir / 'claudon.md'
    plugin_content = (
        "---\n"
        "description: Generate and open interactive Claudon analytics dashboard for Claude Code sessions\n"
        "---\n\n"
        "Run `claudon -o cc_report.html --open` (or `npx @infenia/claudon -o cc_report.html --open`) to analyze sessions.\n"
    )
    if plugin_file.exists():
        if plugin_file.read_text(encoding='utf-8') == plugin_content:
            print(f"Claudon slash command is already up to date at {plugin_file}")
            return
        if not force:
            sys.exit(f"{plugin_file} already exists with different content; "
                     "re-run with --install-plugin --force to overwrite it")
    plugin_file.write_text(plugin_content, encoding='utf-8')
    print(f"Successfully installed Claudon slash command to {plugin_file}")
    print("You can now type /claudon inside Claude Code to launch analytics!")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', nargs='?', default=str(config_dir()))
    ap.add_argument('--version', action='version', version=f'claudon {__version__}')
    ap.add_argument('-o', '--out', default='cc_report.html')
    ap.add_argument('--pricing', help='JSON {"model-substring": [in, out, cache_read, write_5m, write_1h]} $/MTok; longest match wins')
    ap.add_argument('--redact', action='store_true', help='strip prompts, titles, paths, commands and project names (safe to share)')
    ap.add_argument('--open', action='store_true')
    ap.add_argument('--install-plugin', action='store_true', help='install /claudon slash command into <config dir>/commands/')
    ap.add_argument('--force', action='store_true', help='with --install-plugin: overwrite a modified claudon.md')
    a = ap.parse_args()
    if a.install_plugin:
        install_plugin(a.force)
        return
    if a.pricing:
        PRICE.update(load_pricing(a.pricing))
    data = build(a.path)
    if not data['tasks']:
        sys.exit(f'no analysable sessions under {a.path}')
    if a.redact:
        redact(data)
    out = Path(a.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_html(data), encoding='utf-8')
    except OSError as e:
        sys.exit(f'cannot write {out}: {e}')
    print(f'{len(data["sessions"])} sessions, {len(data["tasks"])} tasks from {data["files"]} files -> {a.out}')
    if a.open:
        webbrowser.open(Path(a.out).resolve().as_uri())
