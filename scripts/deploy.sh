#!/usr/bin/env bash
set -euo pipefail
if [[ "$(whoami)" == "drew" ]]; then
  export HOME="/home/drew"
fi

# Ensure HOME is set for non-interactive sessions (e.g., CI)
export HOME="${HOME:-/home/drew}"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="origin"
BRANCH="main"

echo "==> Deploying yf-hockey-cli"
echo "    App dir : $APP_DIR"
echo "    Remote  : $REMOTE"
echo "    Branch  : $BRANCH"
echo

cd "$APP_DIR"

# Ensure git operations use the correct GitHub SSH key in non-interactive sessions.
# We use an absolute path (not ~) because non-interactive shells may not expand it.
GITHUB_KEY_PATH="$HOME/.ssh/id_ed25519_github"
if [[ -f "$GITHUB_KEY_PATH" ]]; then
  export GIT_SSH_COMMAND="ssh -i $GITHUB_KEY_PATH -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
else
  echo "WARN: GitHub SSH key not found at $GITHUB_KEY_PATH"
fi

# Lightweight diagnostics for CI runs (helps debug GitHub Actions SSH environment)
if [[ -n "${CI:-}" ]]; then
  echo "==> CI diagnostics"
  echo "    WHOAMI: $(whoami)"
  echo "    HOME  : $HOME"
  echo "    KEY   : $GITHUB_KEY_PATH (exists: $(test -f "$GITHUB_KEY_PATH" && echo yes || echo no))"
  ls -la "$HOME/.ssh" || true
  ssh -i "$GITHUB_KEY_PATH" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -T git@github.com || true
fi

# Prevent concurrent deploys
LOCKFILE="/tmp/yf-hockey-cli-deploy.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  echo "ERROR: Another deploy is running (lock: $LOCKFILE)"
  exit 1
fi

# Verify repo
git rev-parse --is-inside-work-tree >/dev/null

echo "==> Fetching latest code..."
git fetch "$REMOTE" "$BRANCH"

echo "==> Resetting to $REMOTE/$BRANCH..."
git reset --hard "$REMOTE/$BRANCH"
git clean -fd

# Ensure required runtime dirs exist (persistent host dirs)
mkdir -p "$APP_DIR/../data" "$APP_DIR/../.cache"

# If you plan to symlink these, do that later; for now, keep it simple:
# (We'll wire these into Docker/Compose in the next step.)

echo "==> Build container image..."
docker compose build --pull

echo "==> Sanity check (help output)..."
docker compose run --rm hockey --help >/dev/null

echo "==> Done."
git --no-pager log -1 --oneline