#!/usr/bin/env bash
# Copy the subscription login from the read-only mount to a tmpfs home so
# token refresh never writes to the host file, then run the command.
set -euo pipefail
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "entrypoint: ANTHROPIC_API_KEY is set; refusing to bill the API" >&2
  exit 64
fi
src=/run/bench/credentials.json
if [ -e "$src" ]; then
  mkdir -p "$HOME/.claude"
  install -m 0600 "$src" "$HOME/.claude/.credentials.json"
fi
exec "$@"
