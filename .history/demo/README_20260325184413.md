# Demo: BGP Flap Detective

Quick steps to run the project locally for a demo.

Prerequisites
- Python 3.10+ and the project's virtualenv at `./.venv`
- A POSIX shell (macOS / Linux)

Run tests

```bash
source ./.venv/bin/activate
./.venv/bin/python -m pytest -q
```

Start the MCP server (live demo)

```bash
source ./.venv/bin/activate
PYTHONPATH=src ./.venv/bin/python -m bgp_flap_detective.server
```

Notes
- The server runs in the foreground and logs to the terminal.
- Use Ctrl+C to stop the server.
