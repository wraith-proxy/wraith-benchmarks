#!/usr/bin/env bash
# up: internal network plus allowlist proxy for Bash tasks. down: remove both.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
case "${1:-}" in
  up)
    docker network inspect wraith-bench-egress >/dev/null 2>&1 \
      || docker network create --internal wraith-bench-egress >/dev/null
    docker run -d --rm --name wraith-bench-proxy --cap-drop ALL \
      --security-opt no-new-privileges --user 1000:1000 \
      -e BENCH_EGRESS_ALLOW \
      -v "$here/egress_proxy.py:/proxy.py:ro" --entrypoint python3 \
      wraith-bench:latest /proxy.py >/dev/null
    docker network connect wraith-bench-egress wraith-bench-proxy ;;
  down)
    docker rm -f wraith-bench-proxy >/dev/null 2>&1 || true
    docker network rm wraith-bench-egress >/dev/null 2>&1 || true ;;
  *) echo "usage: egress.sh up|down" >&2; exit 2 ;;
esac
