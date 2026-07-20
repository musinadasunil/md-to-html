#!/usr/bin/env bash
# Bootstrap md-to-html on a new machine: clone the repo, ensure uv is
# installed, and put a `md-to-html` command on PATH.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/musinadasunil/md-to-html/main/install.sh | bash
#   # or copy this file over and run: bash install.sh
#
# Override defaults with env vars:
#   INSTALL_DIR=~/code/md-to-html REPO_URL=git@github.com:musinadasunil/md-to-html.git bash install.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/musinadasunil/md-to-html.git}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/Projects/md-to-html}"
BIN_DIR="$HOME/.local/bin"

echo "==> Repo:   $REPO_URL"
echo "==> Target: $INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "==> Existing checkout found, pulling latest"
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "==> Cloning"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "==> uv not found, installing (https://astral.sh/uv)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

chmod +x "$INSTALL_DIR/md_to_html.py"
mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/md_to_html.py" "$BIN_DIR/md-to-html"
echo "==> Linked $BIN_DIR/md-to-html -> $INSTALL_DIR/md_to_html.py"

case ":$PATH:" in
  *":$BIN_DIR:"*)
    ;;
  *)
    RC_FILE="$HOME/.zshrc"
    [ "${SHELL:-}" = "/bin/bash" ] && RC_FILE="$HOME/.bash_profile"
    LINE='export PATH="$HOME/.local/bin:$PATH"'
    if ! grep -Fxq "$LINE" "$RC_FILE" 2>/dev/null; then
      echo "$LINE" >> "$RC_FILE"
      echo "==> Added $BIN_DIR to PATH in $RC_FILE (open a new terminal, or run: source $RC_FILE)"
    fi
    ;;
esac

echo "==> Done. Try: md-to-html --help"
