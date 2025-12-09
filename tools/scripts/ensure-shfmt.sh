#!/usr/bin/env bash
set -euo pipefail

# This script ensures that the correct version of shfmt is installed in .local/bin
# It reads the version from toolchain.versions.yml

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TOOLCHAIN_FILE="$REPO_ROOT/toolchain.versions.yml"
INSTALL_DIR="$REPO_ROOT/.local/bin"
BINARY="$INSTALL_DIR/shfmt"

# Ensure python3 is available for yaml-get
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required to parse toolchain versions." >&2
  exit 1
fi

# Get version from toolchain file
VERSION="$("$REPO_ROOT/bin/yaml-get" "shfmt" "$TOOLCHAIN_FILE")"

if [[ -z "$VERSION" ]]; then
  echo "Error: Could not determine shfmt version from $TOOLCHAIN_FILE" >&2
  exit 1
fi

# Check if current installed version matches
CURRENT_VERSION=""
if [[ -x "$BINARY" ]]; then
  # shfmt --version output usually is like "v3.7.0"
  CURRENT_VERSION="$("$BINARY" --version 2>/dev/null | head -n1 | awk '{print $1}')"
fi

if [[ "$CURRENT_VERSION" == "$VERSION" ]]; then
  # Already installed
  exit 0
fi

echo "Installing shfmt $VERSION to $BINARY..."
mkdir -p "$INSTALL_DIR"

# Download logic
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

# Map architecture
case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *)
    echo "Error: Unsupported architecture $ARCH" >&2
    exit 1
    ;;
esac

URL="https://github.com/mvdan/sh/releases/download/${VERSION}/shfmt_${VERSION}_${OS}_${ARCH}"

# Use curl or wget
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$URL" -o "$BINARY"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$BINARY" "$URL"
else
  echo "Error: curl or wget required" >&2
  exit 1
fi

chmod +x "$BINARY"
echo "shfmt $VERSION installed."
