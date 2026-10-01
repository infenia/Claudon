#!/bin/sh
# Claudon Standalone Installer
set -e

INSTALL_DIR="${HOME}/.local/bin"
mkdir -p "${INSTALL_DIR}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${SCRIPT_DIR}/claudon.py" ]; then
    echo "Installing Claudon from local source..."
    cp "${SCRIPT_DIR}/claudon.py" "${INSTALL_DIR}/claudon"
else
    DOWNLOAD_URL="https://raw.githubusercontent.com/claudon/claudon/main/claudon.py"
    echo "Downloading Claudon..."
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "${DOWNLOAD_URL}" -o "${INSTALL_DIR}/claudon"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "${INSTALL_DIR}/claudon" "${DOWNLOAD_URL}"
    else
        echo "Error: curl or wget is required to install Claudon."
        exit 1
    fi
fi

chmod +x "${INSTALL_DIR}/claudon"

echo "Successfully installed Claudon to ${INSTALL_DIR}/claudon"
if ! echo "$PATH" | grep -q "${HOME}/.local/bin"; then
    echo "Notice: Please add ${HOME}/.local/bin to your PATH to run 'claudon' from anywhere."
fi
echo "Run 'claudon --help' to get started!"
