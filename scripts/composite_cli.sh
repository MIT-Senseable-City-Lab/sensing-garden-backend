#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYTHONPATH="$REPO_ROOT/trigger/src" poetry run python -m composite_cli "$@"
