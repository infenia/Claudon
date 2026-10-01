#!/bin/sh
# Claudon Standalone Installer
#   curl -fsSL https://raw.githubusercontent.com/infenia/Claudon/main/install.sh | sh
# Pin a release (recommended) with CLAUDON_VERSION=vX.Y.Z: claudon.py then comes from that GitHub Release
# and is checked against the release's SHA256SUMS. Without a pin, the current main branch is installed.
set -e

INSTALL_DIR="${HOME}/.local/bin"
VERSION="${CLAUDON_VERSION:-main}"
REPO="https://github.com/infenia/Claudon"
mkdir -p "${INSTALL_DIR}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Warning: python3 not found on PATH; Claudon needs Python 3.11+ to run."
fi

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
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$0" ] && [ "$(basename "$0")" = "install.sh" ] && [ -f "${SCRIPT_DIR}/claudon.py" ]; then
    echo "Installing Claudon from local source..."
    if [ -n "${CLAUDON_VERSION}" ]; then echo "Note: CLAUDON_VERSION is ignored when installing from a checkout."; fi
    cp "${SCRIPT_DIR}/claudon.py" "${TMP}"
elif [ "${VERSION}" = "main" ]; then
    echo "Downloading Claudon (main branch, unverified; set CLAUDON_VERSION=vX.Y.Z for a checksum-verified release)..."
    fetch "https://raw.githubusercontent.com/infenia/Claudon/main/claudon.py" "${TMP}"
else
    echo "Downloading Claudon ${VERSION}..."
    fetch "${REPO}/releases/download/${VERSION}/claudon.py" "${TMP}"
    fetch "${REPO}/releases/download/${VERSION}/SHA256SUMS" "${SUMS}"
    expected="$(grep '[ *]claudon\.py$' "${SUMS}" | cut -d' ' -f1)"
    if [ -z "${expected}" ] || [ "${expected}" != "$(sha256 "${TMP}")" ]; then
        echo "Error: checksum verification failed for claudon.py ${VERSION}; nothing was installed."
        exit 1
    fi
    echo "Checksum verified."
fi

chmod 755 "${TMP}"
mv "${TMP}" "${INSTALL_DIR}/claudon"

echo "Successfully installed Claudon to ${INSTALL_DIR}/claudon"
case ":${PATH}:" in
    *":${INSTALL_DIR}:"*) ;;
    *) echo "Notice: Please add ${INSTALL_DIR} to your PATH to run 'claudon' from anywhere." ;;
esac
echo "Run 'claudon --help' to get started!"
