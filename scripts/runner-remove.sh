#!/usr/bin/env bash
# Unregister the local self-hosted runner from GitHub.
# Pass --purge to also delete the local .actions-runner/ directory afterward.
set -euo pipefail

REPO="Bhavan-Techlabs/srilankan-property-scraper"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER_DIR="$REPO_ROOT/.actions-runner"

# Make sure the listener isn't running before removing.
pkill -f "actions-runner/bin/Runner.Listener" 2>/dev/null && echo "Stopped running listener." || true

if [ -x "$RUNNER_DIR/config.sh" ]; then
  TOKEN=$(gh api -X POST "repos/$REPO/actions/runners/remove-token" --jq .token)
  (cd "$RUNNER_DIR" && ./config.sh remove --token "$TOKEN")
else
  echo "No runner config found at $RUNNER_DIR — nothing to unregister."
fi

if [ "${1:-}" = "--purge" ]; then
  rm -rf "$RUNNER_DIR"
  echo "Deleted $RUNNER_DIR"
fi
