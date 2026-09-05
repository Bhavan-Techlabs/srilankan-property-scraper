#!/usr/bin/env bash
# Trigger the self-hosted scrape workflow. Run scripts/runner-start.sh first
# and wait for "Listening for Jobs" before running this.
set -euo pipefail

REPO="Bhavan-Techlabs/srilankan-property-scraper"
WORKFLOW="scrape-selfhosted.yml"

gh workflow run "$WORKFLOW" --repo "$REPO"
echo "Triggered. Watch it with:"
echo "  gh run watch \$(gh run list --repo $REPO --workflow=$WORKFLOW --limit 1 --json databaseId --jq '.[0].databaseId') --repo $REPO"
