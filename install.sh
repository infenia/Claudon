#!/bin/sh
# Claudon Standalone Installer
#   curl -fsSL https://raw.githubusercontent.com/infenia/claudon/main/install.sh | sh
# Works on Linux, macOS and Windows (Git Bash / MSYS2 / WSL); in plain PowerShell use install.ps1.
# Installs the native binary for this platform (no Python needed) from a GitHub Release, checked against that
# release's SHA256SUMS. Platforms without a binary get claudon.pyz instead, which needs Python 3.11+.
# Pin a release (recommended) with CLAUDON_VERSION=vX.Y.Z; without a pin the latest release is installed.
set -e

INSTALL_DIR="${HOME}/.local/bin"
VERSION="${CLAUDON_VERSION:-latest}"
REPO="https://github.com/infenia/claudon"
mkdir -p "${INSTALL_DIR}"

TMP="$(mktemp "${INSTALL_DIR}/.claudon.XXXXXX")"     # same filesystem as the target, so mv is atomic
SUMS="$(mktemp)"
trap 'rm -f "${TMP}" "${SUMS}"' EXIT

fetch() {  # fetch URL OUTFILE
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$1" -o "$2"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$2" "$1"
    else
        echo "Error: curl or wget is required to install Claudon."
        exit 1
    fi
}

sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# Only use a local copy when this script was run from a checkout (`sh install.sh`), never under `curl | sh`,
# where $0 is the shell and dirname "$0" would be whatever directory the user happens to be in.
# download NAME: fetch a release asset into TMP and verify it. Returns 1 if the release has no such asset;
# a checksum mismatch is fatal (never fall back past a failed verification).
download() {
    fetch "${BASE}/$1" "${TMP}" 2>/dev/null || return 1
    fetch "${BASE}/SHA256SUMS" "${SUMS}"
    expected="$(grep "[ *]$1\$" "${SUMS}" | cut -d' ' -f1)"
    if [ -z "${expected}" ] || [ "${expected}" != "$(sha256 "${TMP}")" ]; then
        echo "Error: checksum verification failed for $1 ${VERSION}; nothing was installed."
        exit 1
    fi
    echo "Checksum verified."
}

need_python() {
    command -v python3 >/dev/null 2>&1 || echo "Warning: python3 not found on PATH; this install of Claudon needs Python 3.11+ to run."
}

# Only use a local copy when this script was run from a checkout (`sh install.sh`), never under `curl | sh`,
# where $0 is the shell and dirname "$0" would be whatever directory the user happens to be in.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$0" ] && [ "$(basename "$0")" = "install.sh" ] && [ -f "${SCRIPT_DIR}/scripts/build_zipapp.py" ]; then
    echo "Installing Claudon from local source..."
    if [ -n "${CLAUDON_VERSION}" ]; then echo "Note: CLAUDON_VERSION is ignored when installing from a checkout."; fi
    need_python
    python3 "${SCRIPT_DIR}/scripts/build_zipapp.py" "${TMP}" >/dev/null
else
    if [ "${VERSION}" = "latest" ]; then BASE="${REPO}/releases/latest/download"; else BASE="${REPO}/releases/download/${VERSION}"; fi
    EXE=claudon
    case "$(uname -s)-$(uname -m)" in
        Linux-x86_64)  ASSET=claudon-linux-x86_64
                       # the Linux binary is built against glibc; musl (Alpine) gets the .pyz instead
                       if (ldd --version 2>&1 || true) | grep -qi musl; then ASSET=; fi ;;
        Darwin-arm64)  ASSET=claudon-macos-arm64 ;;
        Darwin-x86_64) ASSET=claudon-macos-x86_64 ;;
        MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64)   # Git Bash / MSYS2 / Cygwin on Windows
                       ASSET=claudon-windows-x86_64.exe; EXE=claudon.exe ;;
        *)             ASSET= ;;
    esac
    echo "Downloading Claudon ${VERSION}..."
    if [ -n "${ASSET}" ] && download "${ASSET}"; then
        echo "Installed the native binary (${ASSET}); Python is not required."
    else
        case "${EXE}" in *.exe) echo "Error: no Windows binary in release ${VERSION}."; exit 1 ;; esac    # the .pyz isn't directly runnable on Windows
        echo "No native binary for this platform/release; using claudon.pyz."
        need_python
        download claudon.pyz || { echo "Error: claudon.pyz not found in release ${VERSION}."; exit 1; }
    fi
fi

chmod 755 "${TMP}"
mv "${TMP}" "${INSTALL_DIR}/${EXE:-claudon}"

echo "Successfully installed Claudon to ${INSTALL_DIR}/${EXE:-claudon}"
case ":${PATH}:" in
    *":${INSTALL_DIR}:"*) ;;
    *) echo "Notice: Please add ${INSTALL_DIR} to your PATH to run 'claudon' from anywhere." ;;
esac
echo "Run 'claudon --help' to get started!"
