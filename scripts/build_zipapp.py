#!/usr/bin/env python3
"""Bundle the claudon package into one runnable file (stdlib zipapp): dist/claudon.pyz

    python scripts/build_zipapp.py [OUT]

The .pyz is what install.sh installs and what the WASM page loads: still "one file to download", no pip needed.
"""
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build(out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(ROOT / 'claudon', Path(tmp) / 'claudon', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        zipapp.create_archive(tmp, out, main='claudon.cli:main', interpreter='/usr/bin/env python3')
    out.chmod(0o755)
    return out


if __name__ == '__main__':
    print(build(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'dist' / 'claudon.pyz'))
