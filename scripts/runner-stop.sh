#!/usr/bin/env bash
# Stop the local self-hosted runner listener process (if running).
# This does NOT unregister the runner from GitHub — use runner-remove.sh for that.
set -euo pipefail

if pkill -f "actions-runner/bin/Runner.Listener" 2>/dev/null; then
  echo "Runner listener stopped."
else
  echo "No running runner listener found."
fi
