#!/usr/bin/env python3
"""Build script to compile claudon.py into a native standalone executable using Nuitka.

Usage:
    python scripts/build_nuitka.py [--onefile | --standalone] [--output-dir DIST_DIR] [NUITKA_OPTION ...]
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
TARGET_SCRIPT = ROOT_DIR / "claudon.py"


def check_nuitka():
    try:
        subprocess.run(
            [sys.executable, "-m", "nuitka", "--version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def build_nuitka(onefile=True, output_dir=None, extra_args=None):
    if not check_nuitka():
        print("Error: Nuitka is not installed. Install it with 'pip install nuitka'.", file=sys.stderr)
        return False

    output_dir = Path(output_dir) if output_dir else ROOT_DIR / "dist"
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--assume-yes-for-downloads",
        f"--output-dir={output_dir}",
    ]

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--standalone")

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(str(TARGET_SCRIPT))

    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        print(f"\nCompilation successful! Executable output located in {output_dir}")
        return True
    else:
        print(f"\nCompilation failed with exit code {result.returncode}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Compile claudon.py using Nuitka.",
                                     epilog="Unrecognised options are passed through to Nuitka.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--onefile", dest="onefile", action="store_true", default=True,
                      help="Create a single-file executable (the default)")
    mode.add_argument("--standalone", dest="onefile", action="store_false",
                      help="Create a standalone directory distribution instead of a single file")
    parser.add_argument("--output-dir", default=str(ROOT_DIR / "dist"), help="Output directory for compiled binary")
    args, extra_args = parser.parse_known_args()

    success = build_nuitka(onefile=args.onefile, output_dir=args.output_dir, extra_args=extra_args)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
