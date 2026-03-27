"""
BGP Flap Detective MCP Server Module

This module implements the core diagnostic logic for identifying BGP session flap root causes.
It provides MCP tools for SSH-based device interrogation, evidence collection, and recommendation.

Key responsibilities:
- SSH command execution and error handling via Netmiko
- BGP summary, interface, MTU, and syslog data parsing
- Root-cause analysis and safe remediation recommendations
- Mock mode support for demo and testing without live hardware
"""

import argparse
import os
import re
from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from .inventory import load_inventory

SWITCH_INVENTORY = load_inventory()
MOCK_MODE = os.getenv("BFD_MOCK_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}

# Initialize the MCP server with diagnostic session instructions for the attached LLM client
mcp = FastMCP(
    "BGP Flap Detective",
    instructions=(
        "You are a senior network engineer specializing in BGP troubleshooting. "
        "For BGP issues, call check_bgp_neighbors first, then inspect interface errors, "
        "then run MTU checks and syslog correlation before recommending a fix."
    ),
)


def now_iso() -> str:
    """Return current UTC time in ISO 8601 format for timestamp tracking."""
    return datetime.now().isoformat()


def _mock_command_output(device_name: str, command: str) -> str:
    """
    Generate synthetic CLI output for demo and testing without live devices.
    
    This function simulates realistic output from Cisco NX-OS and similar platforms
    for common diagnostic commands. Used when BFD_MOCK_MODE environment variable is set.
    
    Args:
        device_name: Logical device name from inventory (e.g., "spine-1")
        command: Full CLI command string to simulate
        
    Returns:
        Synthetic CLI output matching the command, or error message if command unknown.
    """
    cmd = command.lower().strip()

    if "show bgp ipv4 unicast summary" in cmd or "show ip bgp summary" in cmd:
        return """
Neighbor        V    AS MsgRcvd MsgSent TblVer InQ OutQ Up/Down  State/PfxRcd
192.168.1.20    4 65001   1000    1200    124   0    0 1d02h     224
192.168.1.21    4 65002    100     120    124   0    0 00:00:12  Active
""".strip()

    if cmd.startswith("show interface"):
        return """
Ethernet1/1 is up, line protocol is up
  MTU 1500 bytes
  4 input error, 132 CRC, 0 frame, 0 overrun, 0 ignored
  3 output drop
  9 carrier transition
  2 interface reset
""".strip()

    if cmd.startswith("show logging"):
        return """
2026 Mar 23 10:12:05 spine-1 %BGP-5-ADJCHANGE: neighbor 192.168.1.21 Down BGP Notification sent
2026 Mar 23 10:12:06 spine-1 %BGP-3-NOTIFICATION: sent to neighbor 192.168.1.21 hold time expired
2026 Mar 23 10:12:11 spine-1 %BGP-5-ADJCHANGE: neighbor 192.168.1.21 Up
""".strip()

    if cmd.startswith("ping"):
        if any(size in cmd for size in ["size 1450", "size 1500", "size 9000"]):
            return "Success rate is 0 percent (0/5)"
        return "Success rate is 100 percent (5/5)"

    return f"MOCK: no sample data available for command '{command}' on {device_name}"


def ssh_run(device_name: str, command: str) -> str:
    """
    Execute a CLI command on a remote device via SSH using Netmiko.
    
    This is the core mechanism for device interrogation. In production, this connects
    to real switches; in mock mode, it returns synthetic data for testing.
    
    Args:
        device_name: Inventory key (e.g., "spine-1"), must exist in SWITCH_INVENTORY
        command: Full CLI command string to send to the device
        
    Returns:
        CLI command output as string, or error message prefixed with "ERROR:" if connection fails.
        
    Raises:
        None (all exceptions are caught and returned as error strings for graceful handling)
    """
    if device_name not in SWITCH_INVENTORY:
        return (
            f"ERROR: '{device_name}' not found in inventory. "
            f"Known devices: {list(SWITCH_INVENTORY.keys())}"
        )

    if MOCK_MODE:
        return _mock_command_output(device_name, command)

    params = SWITCH_INVENTORY[device_name]
    try:
        with ConnectHandler(**params) as conn:
            return str(conn.send_command(command, read_timeout=30))
    except NetmikoAuthenticationException:
        return f"ERROR: Authentication failed for {device_name} ({params['host']})."
    except NetmikoTimeoutException:
        return f"ERROR: Connection timed out for {device_name} ({params['host']})."
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"


def parse_bgp_summary(raw: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse BGP neighbor summary output into structured neighbor records.
    
    Parses typical Cisco NX-OS "show bgp ipv4 unicast summary" output to extract
    neighbor IP, AS number, state, and flap indicators. Identifies non-established
    peers as potential problem indicators for further diagnosis.
    
    Args:
        raw: Raw CLI output from "show bgp [ipv4 unicast] summary" command
        
    Returns:
        Tuple of (all_neighbors_list, problem_peers_list) where problem_peers_list
        contains only non-established peers requiring investigation
    """
    neighbors: list[dict[str, Any]] = []
    flapping: list[dict[str, Any]] = []

    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        if not re.match(r"^\d+\.\d+\.\d+\.\d+$", parts[0]):
            continue

        peer_ip = parts[0]
        peer_as = parts[2] if len(parts) > 2 else "unknown"
        up_down = parts[-2] if len(parts) >= 2 else "unknown"
        state_pfx = parts[-1]
        # A numeric state_pfx indicates established with prefix count; otherwise it's a failure state
        is_established = state_pfx.isdigit()

        item = {
            "peer_ip": peer_ip,
            "peer_as": peer_as,
            "state_or_prefixes": state_pfx,
            "up_down": up_down,
            "is_established": is_established,
        }
        neighbors.append(item)

        if not is_established:
            flapping.append(
                {
                    "peer_ip": peer_ip,
                    "state": state_pfx,
                    "likely_flapping": True,
                }
            )

    return neighbors, flapping


def parse_interface_output(raw: str) -> dict[str, Any]:
    """
    Extract interface diagnostics from "show interface" output.
    
    Parses physical layer counters (CRC errors, carrier transitions, resets, etc.)
    and identifies conditions that could trigger BGP flaps. Returns structured
    diagnostics with a flag indicating presence of problems.
    
    Args:
        raw: Raw output from "show interface <name>" command
        
    Returns:
        Dict with parsed counters, line protocol state, MTU, and list of detected problems
    """
    def extract(pattern: str, default: str = "0") -> str:
        """Helper to regex-extract a value from CLI output with default fallback."""
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        return match.group(1) if match else default

    line_protocol = extract(r"line protocol is (\w+)", "unknown")
    crc_errors = int(extract(r"(\d+)\s+CRC"))
    input_errors = int(extract(r"(\d+)\s+input error"))
    output_drops = int(extract(r"(\d+)\s+output drop"))
    carrier_transitions = int(extract(r"(\d+)\s+carrier transition"))
    interface_resets = int(extract(r"(\d+)\s+interface reset"))
    mtu = extract(r"MTU\s+(\d+)\s+bytes", "unknown")

    # Heuristic detection: flag conditions likely to cause BGP flaps
    problems: list[str] = []
    if line_protocol.lower() != "up":
        problems.append("Line protocol is not up")
    if crc_errors > 100:
        problems.append(f"High CRC errors ({crc_errors})")
    if carrier_transitions > 5:
        problems.append(f"Frequent carrier transitions ({carrier_transitions})")
    if output_drops > 0:
        problems.append(f"Output drops observed ({output_drops})")

    return {
        "line_protocol": line_protocol,
        "mtu_bytes": mtu,
        "crc_errors": crc_errors,
        "input_errors": input_errors,
        "output_drops": output_drops,
        "carrier_transitions": carrier_transitions,
        "interface_resets": interface_resets,
        "problems_detected": problems,
        "has_problems": len(problems) > 0,
    }


def analyze_mtu_results(results: dict[int, bool]) -> dict[str, Any]:
    """
    Synthesize MTU ping results to identify path MTU constraint.
    
    Tests progressive packet sizes (typically 576, 1400, 1450, 1500, 9000) with
    DF bit set to discover the effective MTU on the path. MTU mismatch is a common
    root cause of BGP flaps, especially in overlay networks.
    
    Args:
        results: Dict mapping packet size (int) to success boolean
        
    Returns:
        Dict with effective_path_mtu, fail points, diagnosis message, and mtu_problem_detected flag
    """
    effective_mtu = 0
    failed_at: list[int] = []

    for size in sorted(results.keys()):
        if results[size]:
            effective_mtu = size
        else:
            failed_at.append(size)

    # Diagnosis: if largest passing size is less than standard 1500, we have an MTU problem
    mtu_problem = len(failed_at) > 0 and effective_mtu < 1500
    if mtu_problem:
        diagnosis = (
            f"Likely MTU mismatch: largest passing payload is {effective_mtu}, "
            f"failures start at {failed_at[0]}"
        )
    else:
        diagnosis = "No MTU mismatch detected in tested packet sizes"

    return {
        "effective_path_mtu": effective_mtu,
        "failed_at_sizes": failed_at,
        "mtu_problem_detected": mtu_problem,
        "diagnosis": diagnosis,
    }


@mcp.tool
def list_devices() -> dict[str, Any]:
    """
    MCP Tool: List all configured network devices from inventory.
    
    This is the first tool to call in a troubleshooting session to confirm
    which devices are reachable and available for diagnostic queries.
    
    Returns:
        Dict containing device count, list of device objects (name, host, type, port),
        current timestamp, and mock mode indicator
    """
    return {
        "count": len(SWITCH_INVENTORY),
        "devices": [
            {
                "name": name,
                "host": data.get("host", ""),
                "device_type": data.get("device_type", ""),
                "port": data.get("port", 22),
            }
            for name, data in SWITCH_INVENTORY.items()
        ],
        "timestamp": now_iso(),
        "mock_mode": MOCK_MODE,
    }


@mcp.tool
def check_bgp_neighbors(device_name: str) -> dict[str, Any]:
    """
    MCP Tool: Query BGP neighbor summary for established and problematic sessions.
    
    Runs vendor-specific BGP summary command and parses neighbor states, ASNs,
    and session uptime. Identifies non-established neighbors for further investigation.
    
    Args:
        device_name: Device identifier from inventory (e.g., "spine-1")
        
    Returns:
        Dict with neighbor list, problem peers, counts, raw output, and timestamp
    """
    device_type = SWITCH_INVENTORY.get(device_name, {}).get("device_type", "cisco_nxos")
    cmd = "show ip bgp summary" if "arista" in device_type else "show bgp ipv4 unicast summary"
    raw = ssh_run(device_name, cmd)

    if raw.startswith("ERROR"):
        return {"device": device_name, "error": raw, "timestamp": now_iso()}

    neighbors, flapping = parse_bgp_summary(raw)
    return {
        "device": device_name,
        "timestamp": now_iso(),
        "mock_mode": MOCK_MODE,
        "total_neighbors": len(neighbors),
        "established_count": sum(1 for n in neighbors if n["is_established"]),
        "problem_peers": flapping,
        "neighbors": neighbors,
        "raw_output": raw,
    }


@mcp.tool
def get_interface_errors(device_name: str, interface: str) -> dict[str, Any]:
    """
    MCP Tool: Retrieve physical layer error counters for a specific interface.
    
    Extracts line protocol state, MTU, CRC errors, carrier transitions, and other
    physical layer diagnostics. High error rates are common BGP flap triggers.
    
    Args:
        device_name: Device identifier from inventory
        interface: Interface name (e.g., "Ethernet1/1", "Gi0/0")
        
    Returns:
        Dict with line protocol, MTU, error counters, and problem list
    """
    raw = ssh_run(device_name, f"show interface {interface}")
    if raw.startswith("ERROR"):
        return {
            "device": device_name,
            "interface": interface,
            "error": raw,
            "timestamp": now_iso(),
        }

    parsed = parse_interface_output(raw)
    return {
        "device": device_name,
        "interface": interface,
        "mock_mode": MOCK_MODE,
        **parsed,
        "timestamp": now_iso(),
    }


@mcp.tool
def check_mtu_path(source_device: str, destination_ip: str) -> dict[str, Any]:
    """
    MCP Tool: Discover effective path MTU using progressive ping tests with DF bit.
    
    Tests a range of packet sizes (576 to 9000 bytes) with the DF bit set to identify
    the largest payload size that can traverse the path. MTU mismatches cause TCP/BGP
    connection failures.
    
    Args:
        source_device: Device to run ping tests from
        destination_ip: Target IP address for MTU path discovery
        
    Returns:
        Dict with test results per size, effective MTU, failure points, and diagnosis
    """
    results: dict[int, bool] = {}
    for size in [576, 1400, 1450, 1500, 9000]:
        cmd = f"ping {destination_ip} size {size} df-bit"
        raw = ssh_run(source_device, cmd)
        success = ("100 percent" in raw) or ("Success rate is 100 percent" in raw)
        results[size] = success

    analysis = analyze_mtu_results(results)
    return {
        "source": source_device,
        "destination": destination_ip,
        "mock_mode": MOCK_MODE,
        "test_results": results,
        **analysis,
        "timestamp": now_iso(),
    }


@mcp.tool
def get_syslog_events(
    device_name: str,
    filter_keyword: str = "BGP",
    last_n_lines: int = 50,
) -> dict[str, Any]:
    """
    MCP Tool: Retrieve and correlate syslog events with BGP flap symptoms.
    
    Collects recent logs and filters for BGP-related keywords, then classifies events
    into categories (hold timer, notifications, resets) to identify timing correlations
    with observed flaps.
    
    Args:
        device_name: Device identifier from inventory
        filter_keyword: Syslog keyword filter (default "BGP")
        last_n_lines: Number of recent lines to retrieve (default 50)
        
    Returns:
        Dict with categorized events, analysis comments, and raw output
    """
    cmd = f"show logging last {max(last_n_lines, 10) * 3}"
    raw = ssh_run(device_name, cmd)

    if raw.startswith("ERROR"):
        return {"device": device_name, "error": raw, "timestamp": now_iso()}

    keyword = filter_keyword.upper() if filter_keyword else ""
    events = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and (keyword in line.upper() if keyword else True)
    ][-last_n_lines:]

    hold_timer_events = [e for e in events if "HOLD" in e.upper() or "KEEPALIVE" in e.upper()]
    notification_events = [e for e in events if "NOTIFICATION" in e.upper()]
    reset_events = [e for e in events if "RESET" in e.upper() or "DOWN" in e.upper()]

    analysis: list[str] = []
    if hold_timer_events:
        analysis.append("Hold timer or keepalive patterns seen; possible control-plane delay.")
    if notification_events:
        analysis.append("BGP notifications detected; check policy/auth/capability mismatch.")
    if reset_events:
        analysis.append("Session reset/down events present; correlate with interface and MTU checks.")

    return {
        "device": device_name,
        "filter": filter_keyword,
        "mock_mode": MOCK_MODE,
        "total_matching_events": len(events),
        "hold_timer_events": hold_timer_events,
        "notification_events": notification_events,
        "reset_events": reset_events,
        "all_events": events,
        "analysis": analysis,
        "timestamp": now_iso(),
    }


@mcp.tool
def recommend_fix(
    root_cause: str,
    affected_device: str,
    affected_interface: str | None = None,
    peer_ip: str | None = None,
) -> dict[str, Any]:
    """
    MCP Tool: Generate safe, vendor-agnostic remediation command sequences.
    
    Maps diagnosis root causes to command suggestions. Output is text-only recommendations;
    no commands are auto-executed. Includes safety notes for operational teams.
    
    Supported root causes:
    - mtu_mismatch: Interface MTU configuration
    - hold_timer: BGP timer tuning
    - interface_flap: Physical layer issues (cable/optics)
    - crc_errors: Physical layer quality
    - route_policy: BGP policy validation
    - authentication: BGP password/auth
    - recursive_routing: BGP path loop prevention
    
    Args:
        root_cause: Key identifying the diagnosis (see supported list above)
        affected_device: Device where the issue was detected
        affected_interface: Interface name if issue is interface-specific
        peer_ip: BGP peer IP if issue is neighbor-specific
        
    Returns:
        Dict with remediation steps, safety notes, and human-readable formatting
    """
    normalized = root_cause.strip().lower()
    iface = affected_interface or "<interface>"
    peer = peer_ip or "<peer_ip>"

    fixes: dict[str, list[str]] = {
        "mtu_mismatch": [
            "configure terminal",
            f"interface {iface}",
            "mtu 9216",
            "end",
            "copy running-config startup-config",
        ],
        "hold_timer": [
            "configure terminal",
            f"router bgp <local_as>",
            f"neighbor {peer} timers 10 30",
            "end",
            "copy running-config startup-config",
        ],
        "interface_flap": [
            "show interface transceiver details",
            f"interface {iface}",
            "shutdown",
            "no shutdown",
            "! Replace cable/SFP if flap continues",
        ],
        "crc_errors": [
            f"show interface {iface}",
            "show interface counters errors",
            "! Check speed/duplex and replace cable or optics",
        ],
        "route_policy": [
            "show run | section route-map",
            "show run | section prefix-list",
            "! Verify outbound/inbound policy allows required routes",
        ],
        "authentication": [
            "configure terminal",
            f"router bgp <local_as>",
            f"neighbor {peer} password <shared_secret>",
            "end",
            "copy running-config startup-config",
        ],
        "recursive_routing": [
            f"show ip route {peer}",
            "! Ensure peer reachability is via IGP or connected route, not BGP-learned path",
        ],
    }

    commands = fixes.get(normalized)
    if not commands:
        return {
            "device": affected_device,
            "root_cause": root_cause,
            "error": "Unsupported root cause key",
            "supported_root_causes": sorted(fixes.keys()),
            "timestamp": now_iso(),
        }

    return {
        "device": affected_device,
        "root_cause": normalized,
        "mock_mode": MOCK_MODE,
        "peer_ip": peer_ip,
        "interface": affected_interface,
        "commands": commands,
        "safety_notes": [
            "Validate commands in lab before production.",
            "Use maintenance window for disruptive interface actions.",
            "Capture before/after show command outputs.",
        ],
        "timestamp": now_iso(),
    }


@mcp.tool
def run_mock_investigation(
    device_name: str = "spine-1",
    interface: str = "Ethernet1/1",
    peer_ip: str = "192.168.1.21",
) -> dict[str, Any]:
    """
    MCP Tool: Execute a complete simulated investigation bundle for demos.
    
    Runs all diagnostic tools in sequence using mock CLI output, synthesizes
    a suggested root cause based on findings, and returns full recommendation.
    Useful for team demos and testing without live lab access.
    
    Args:
        device_name: Device to simulate investigation on
        interface: Interface to include in diagnostics
        peer_ip: BGP peer IP to test MTU path and recommend fixes for
        
    Returns:
        Dict with full investigation steps and final recommendation
    """
    bgp = check_bgp_neighbors(device_name)
    intf = get_interface_errors(device_name, interface)
    mtu = check_mtu_path(device_name, peer_ip)
    logs = get_syslog_events(device_name, filter_keyword="BGP", last_n_lines=20)

    if mtu.get("mtu_problem_detected"):
        suggested_cause = "mtu_mismatch"
    elif intf.get("crc_errors", 0) > 100:
        suggested_cause = "crc_errors"
    elif bgp.get("problem_peers"):
        suggested_cause = "hold_timer"
    else:
        suggested_cause = "route_policy"

    recommendation = recommend_fix(
        root_cause=suggested_cause,
        affected_device=device_name,
        affected_interface=interface,
        peer_ip=peer_ip,
    )

    return {
        "scenario": "mock_bgp_flap_demo",
        "mock_mode_active": MOCK_MODE,
        "device": device_name,
        "peer_ip": peer_ip,
        "interface": interface,
        "suggested_root_cause": suggested_cause,
        "steps": {
            "bgp_neighbors": bgp,
            "interface_errors": intf,
            "mtu_check": mtu,
            "syslog_events": logs,
            "recommendation": recommendation,
        },
        "timestamp": now_iso(),
    }


def main() -> None:
    """
    Entry point: Parse arguments and launch MCP server in configured mode.
    
    Supports two transport modes:
    - stdio (default): For local MCP client connections
    - http: For team testing on network interface
    """
    parser = argparse.ArgumentParser(description="Run the BGP Flap Detective MCP server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP transport mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host for HTTP mode")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP mode")
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
