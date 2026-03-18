# Demo Test Plan

## Objective

Run a repeatable demo that proves the agent can identify likely BGP flap causes and suggest safe remediation steps.

## Pre-Demo Checklist

- Python environment is created and dependencies installed
- Inventory points to reachable lab devices
- Read-only credentials are valid
- One controlled failure scenario is prepared
- One healthy baseline scenario is prepared

## Demo Script

1. Start server in stdio mode for local MCP client.
2. Run list_devices to prove inventory visibility.
3. Run check_bgp_neighbors on a known impacted spine.
4. Run get_interface_errors on affected peering interface.
5. Run check_mtu_path to peer IP.
6. Run get_syslog_events for BGP keyword.
7. Call recommend_fix with diagnosed root cause.
8. Summarize evidence and final recommendation.

## Expected Evidence

- Non-established BGP neighbor state or abnormal reset behavior
- Interface counters indicating CRC or flap symptoms when relevant
- MTU failure breakpoint when mismatch exists
- Log entries that align with observed event timing
- Clear and safe recommendation command sequence

## Post-Demo Validation

- Confirm tool outputs are timestamped
- Confirm no command execution changes running config automatically
- Save transcript for feedback and iteration
