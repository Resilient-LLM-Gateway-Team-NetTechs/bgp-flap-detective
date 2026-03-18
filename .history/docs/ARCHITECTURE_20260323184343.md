# Architecture Outline

## Goal

Provide an MCP tool server that can diagnose likely BGP flap root causes by collecting evidence from network devices over SSH.

## Current Components

- MCP layer: FastMCP tool registration and transport handling
- Access layer: Netmiko-based SSH command execution
- Inventory layer: local defaults with optional JSON source override
- Analysis layer: parser and heuristic checks for BGP, interface, MTU, and logs
- Recommendation layer: root-cause mapped command suggestions

## Tool Flow

1. list_devices
2. check_bgp_neighbors
3. get_interface_errors
4. check_mtu_path
5. get_syslog_events
6. recommend_fix

## Safety Model

- Default behavior is read-only diagnostics
- Recommendation output is text only; no config push is executed
- Sensitive credentials can be externalized through environment variables

## Near-Term Technical Enhancements

- Structured parser support for NX-OS, EOS, IOS, JunOS variants
- Per-vendor command templates and transport adaptation
- Confidence scoring for diagnosis synthesis
- Better error taxonomy and retries for transient SSH failures
- Optional persistence layer for snapshots and trend analysis
