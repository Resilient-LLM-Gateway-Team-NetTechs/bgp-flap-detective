"""
BGP Flap Detective Entry Point

This module serves as the main entry point for the BGP Flap Detective MCP server.
Delegates to the server.main() function which handles argument parsing and server launch.

Usage:
    python main.py                              # Start in stdio mode (local)
    python main.py --http --port 8000          # Start in HTTP mode (team access)
    BFD_MOCK_MODE=1 python main.py             # Start in mock mode (demo, no live devices)
"""

from bgp_flap_detective.server import main


if __name__ == "__main__":
    main()
