#!/usr/bin/env bash
# Start the local self-hosted GitHub Actions runner in the foreground.
# Leave this running, then in another terminal run: scripts/runner-trigger.sh
# Stop it with Ctrl+C, or from elsewhere: scripts/runner-stop.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER_DIR="$REPO_ROOT/.actions-runner"

if [ ! -x "$RUNNER_DIR/run.sh" ]; then
  echo "Runner not found at $RUNNER_DIR — has it been registered? See CLAUDE.md." >&2
  exit 1
fi

cd "$RUNNER_DIR"
exec ./run.sh
