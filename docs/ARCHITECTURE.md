# Architecture Outline

## Goal

Provide an MCP tool server that can diagnose likely BGP flap root causes by collecting evidence from network devices over SSH.

## Design Philosophy

- **Read-only by default**: All evidence collection is non-destructive. Recommendations are text-only; no network changes are auto-executed.
- **Vendor-agnostic output**: Parse common CLI syntax (Cisco NX-OS, Arista EOS, etc.) with vendor-specific command variants.
- **LLM-friendly**: Output is structured JSON with natural language summaries for attachment to LLM conversations.
- **Demo-first**: Mock mode allows team discussions without live lab access.
- **Safety first**: Recommendations include operational disclaimers and rollback guidance.

## Current Components

- **MCP layer** (FastMCP): Tool registration, transport handling (stdio/HTTP)
- **Access layer** (Netmiko): SSH command execution with connection pooling and timeout handling
- **Inventory layer**: Default hardcoded devices + JSON file override support
- **Analysis layer**: Heuristic-based parsers for BGP, interface, MTU, and log analysis
- **Recommendation layer**: Root-cause-to-commands mapping with safety guardrails

## Tool Flow

Recommended sequence for engineers using the server:

1. **list_devices** — Confirm target device is in inventory and reachable
2. **check_bgp_neighbors** — Identify problem peers (non-established state)
3. **get_interface_errors** — Check physical layer health on the flapping interface
4. **check_mtu_path** — Test path MTU (common cause in overlay networks)
5. **get_syslog_events** — Correlate timing of BGP notifications with observed flaps
6. **recommend_fix** — Generate validated remediation commands based on root cause

## Safety Model

- Default behavior is read-only diagnostics with zero config drift
- All commands returned are commented with operational disclaimers
- Engineers must validate and manually execute recommendations
- Sensitive credentials can be externalized through environment variables (not hardcoded in git)

## Near-Term Technical Enhancements

- Structured parser support for NX-OS, EOS, IOS, JunOS variants
- Per-vendor command templates and transport adaptation
- Confidence scoring for diagnosis synthesis
- Better error taxonomy and retries for transient SSH failures
- Optional persistence layer for snapshots and trend analysis
