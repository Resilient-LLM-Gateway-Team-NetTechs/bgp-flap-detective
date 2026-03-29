#!/usr/bin/env bash
# BGP Flap Detective Demo Launcher
#
# This script provides a simple interface to run the BGP Flap Detective server
# in test or interactive mode for demonstrations and team troubleshooting sessions.
#
# Usage:
#   ./run_demo.sh test              # Run unit test suite
#   ./run_demo.sh server            # Start MCP server in stdio mode (for local IDE)
#
# Environment Variables:
#   BFD_MOCK_MODE=1                 # Enable synthetic data (demo without live devices)
#   PYTHONPATH=src                  # Required for Python to locate modules
#
# The script enforces:-u (exit on undefined variable errors)
#   -e (exit on any command error)
#   -o pipefail (exit on pipe failures)

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 {test|server}" >&2
  exit 2
fi

cmd="$1"

case "$cmd" in
  test)
    # Run the full unit test suite
    # Tests validate parsing logic and investigation workflows without live devices
    ./.venv/bin/python -m pytest -q
    ;;
  server)
    # Start the MCP server in stdio mode
    # This launches the FastMCP server for attachment to an MCP-capable IDE or client
    PYTHONPATH=src ./.venv/bin/python -m bgp_flap_detective.server
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    echo "Usage: $0 {test|server}" >&2
    exit 2
    ;;
esac
