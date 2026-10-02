"""Claudon - Claude Code session analytics -> self-contained HTML dashboard."""

__version__ = '0.3.0'  # x-release-please-version

from .cli import main                        # after __version__: cli imports it
from .discover import build                 # public API, also called by wasm/worker.js
from .redaction import redact
from .render import render_html

__all__ = ['__version__', 'build', 'main', 'redact', 'render_html']
