#!/usr/bin/env bash
# Bootstrap md-to-html on a new machine: clone the repo, ensure Poetry is
# installed, run `poetry install`, and put a `md-to-html` command on PATH.
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

if ! command -v poetry >/dev/null 2>&1; then
  echo "==> Poetry not found, installing (https://python-poetry.org)"
  curl -sSL https://install.python-poetry.org | python3 -
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> Installing dependencies with Poetry"
poetry -C "$INSTALL_DIR" install

mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/md-to-html" <<EOF
#!/usr/bin/env bash
exec poetry -P "$INSTALL_DIR" run md-to-html "\$@"
EOF
chmod +x "$BIN_DIR/md-to-html"
echo "==> Wrote $BIN_DIR/md-to-html (runs the project through Poetry)"

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
