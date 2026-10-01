#!/bin/sh
# Claudon Standalone Installer
#   curl -fsSL https://raw.githubusercontent.com/infenia/Claudon/main/install.sh | sh
# Pin a release with CLAUDON_VERSION=vX.Y.Z (default: main).
set -e

INSTALL_DIR="${HOME}/.local/bin"
VERSION="${CLAUDON_VERSION:-main}"
mkdir -p "${INSTALL_DIR}"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Warning: python3 not found on PATH; Claudon needs Python 3.10+ to run."
fi

TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT

# Only use a local copy when this script was run from a checkout (`sh install.sh`), never under `curl | sh`,
# where $0 is the shell and dirname "$0" would be whatever directory the user happens to be in.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$0" ] && [ "$(basename "$0")" = "install.sh" ] && [ -f "${SCRIPT_DIR}/claudon.py" ]; then
    echo "Installing Claudon from local source..."
    cp "${SCRIPT_DIR}/claudon.py" "${TMP}"
else
    DOWNLOAD_URL="https://raw.githubusercontent.com/infenia/Claudon/${VERSION}/claudon.py"
    echo "Downloading Claudon (${VERSION})..."
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "${DOWNLOAD_URL}" -o "${TMP}"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "${TMP}" "${DOWNLOAD_URL}"
    else
        echo "Error: curl or wget is required to install Claudon."
        exit 1
    fi
fi

chmod 755 "${TMP}"
mv "${TMP}" "${INSTALL_DIR}/claudon"
trap - EXIT

echo "Successfully installed Claudon to ${INSTALL_DIR}/claudon"
case ":${PATH}:" in
    *":${INSTALL_DIR}:"*) ;;
    *) echo "Notice: Please add ${INSTALL_DIR} to your PATH to run 'claudon' from anywhere." ;;
esac
echo "Run 'claudon --help' to get started!"
