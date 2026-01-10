#!/usr/bin/env bash
set -euo pipefail

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

# Ensure git operations use the correct GitHub SSH key in non-interactive sessions
# (Prevents CI-triggered deploys from failing with "Permission denied (publickey)")
if [[ -f "$HOME/.ssh/id_ed25519_github" ]]; then
  export GIT_SSH_COMMAND='ssh -i ~/.ssh/id_ed25519_github -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new'
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