#!/usr/bin/env python3
"""Check that claudon.__version__, package.json and (optionally) a release tag agree.

    python scripts/check_version.py [vX.Y.Z]

One version string serves PyPI and npm, so it must be valid for both: X.Y.Z or X.Y.Z-(alpha|beta|rc).N
(PEP 440 normalises 0.2.0-beta.1 to 0.2.0b1; npm/semver uses it as-is).
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r'\d+\.\d+\.\d+(-(alpha|beta|rc)\.\d+)?')


def module_version():
    for node in ast.parse((ROOT / 'claudon.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == '__version__' for t in node.targets):
            return node.value.value
    raise SystemExit('claudon.py: __version__ not found')


def check(tag=None):
    """Return a list of problems (empty when everything agrees)."""
    py = module_version()
    npm = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
    problems = []
    if not VERSION_RE.fullmatch(py):
        problems.append(f'claudon.__version__ {py!r} is not X.Y.Z or X.Y.Z-(alpha|beta|rc).N')
    if npm != py:
        problems.append(f'package.json version {npm!r} != claudon.__version__ {py!r}')
    if tag is not None and tag != f'v{py}':
        problems.append(f'tag {tag!r} != v{py}')
    return problems


if __name__ == '__main__':
    problems = check(sys.argv[1] if len(sys.argv) > 1 else None)
    for p in problems:
        print(f'error: {p}', file=sys.stderr)
    if problems:
        sys.exit(1)
    print(f'version {module_version()} consistent')
