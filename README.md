# BGP Flap Detective

BGP Flap Detective is an MCP server that helps diagnose BGP session flapping in data center spine-leaf networks.

## The Problem

BGP session flaps are disruptive and costly in production data centers. A single flap can:
- Drop traffic for seconds to minutes
- Trigger cascading route reconvergence
- Impact entire availability zones if not caught quickly

Troubleshooting flaps is historically manual and slow:
- Engineers must SSH to multiple devices
- Correlate outputs from BGP, interfaces, logs, and traceroute
- Distinguish among root causes: MTU mismatch, physical layer issues, timer mismatches, policy errors, authentication problems

Root causes vary significantly, and incorrect diagnosis wastes time and risks dangerous config changes.

## The Solution

BGP Flap Detective structures this diagnosis into a repeatable workflow:
1. **check_bgp_neighbors** — Identify which sessions are non-established
2. **get_interface_errors** — Check physical layer health on the affected interface
3. **check_mtu_path** — Test path MTU with progressive ping sizes
4. **get_syslog_events** — Correlate event timing with BGP notifications and resets
5. **recommend_fix** — Map findings to safe, validated remediation commands

All evidence collection is read-only; recommendations are text-only with safety notes. No config changes are auto-executed.

## What this prototype includes

- Working MCP server with diagnostic tools
- SSH command execution via Netmiko
- Inventory-driven device access
- Root-cause based fix recommendation tool
- Unit tests for parsing and analysis logic
- VS Code task for quick local testing

## Quick start

1. Create and activate a Python environment.
2. Install dependencies:

   ./.venv/bin/python -m pip install -r requirements.txt

3. Start the MCP server in stdio mode:

   PYTHONPATH=src ./.venv/bin/python -m bgp_flap_detective.server

4. Start in HTTP mode for team testing:

   PYTHONPATH=src ./.venv/bin/python -m bgp_flap_detective.server --http --host 0.0.0.0 --port 8000

## Test without real network devices

Enable mock mode:

   BFD_MOCK_MODE=1 PYTHONPATH=src ./.venv/bin/python -m bgp_flap_detective.server

In mock mode, the server returns synthetic outputs for BGP summary, interface counters, MTU ping checks, and syslog events.

Use tool:

- run_mock_investigation(device_name="spine-1", interface="Ethernet1/1", peer_ip="192.168.1.21")

This gives you an end-to-end simulated investigation bundle for demo and QA testing.

## Configure inventory

Edit default inventory in src/bgp_flap_detective/inventory.py or point BFD_INVENTORY_FILE to a JSON inventory file.

Example JSON structure:

{
  "spine-1": {
    "host": "192.168.1.10",
    "device_type": "cisco_nxos",
    "username": "admin",
    "password": "admin",
    "port": 22
  }
}

## Run tests

./.venv/bin/python -m pytest -q

## Demo checklist

- Verify SSH reachability from your machine to all target switches
- Verify credentials for read-only user
- Run list_devices and check_bgp_neighbors first
- Trigger a known flap in lab and capture output for demo
- Keep one rollback-safe recommendation example ready

## Planning docs

- docs/ARCHITECTURE.md
- docs/DEMO_TEST_PLAN.md
- docs/ROADMAP.md
