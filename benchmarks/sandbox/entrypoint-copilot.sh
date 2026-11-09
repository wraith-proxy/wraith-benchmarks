#!/usr/bin/env bash
# Refuse to run with an API key, point Copilot at a tmpfs config dir, run.
set -euo pipefail
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "entrypoint: ANTHROPIC_API_KEY is set; refusing to bill the API" >&2
  exit 64
fi
export COPILOT_HOME="${COPILOT_HOME:-$HOME/.copilot}"
exec "$@"
