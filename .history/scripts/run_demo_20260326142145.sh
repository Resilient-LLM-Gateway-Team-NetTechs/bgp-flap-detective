#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 {test|server}" >&2
  exit 2
fi

cmd="$1"

case "$cmd" in
  test)
    ./.venv/bin/python -m pytest -q
    ;;
  server)
    PYTHONPATH=src ./.venv/bin/python -m bgp_flap_detective.server
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    echo "Usage: $0 {test|server}" >&2
    exit 2
    ;;
esac
