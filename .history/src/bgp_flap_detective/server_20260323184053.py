import argparse
import re
from datetime import datetime
from typing import Any

from fastmcp import FastMCP
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from .inventory import load_inventory

SWITCH_INVENTORY = load_inventory()

mcp = FastMCP(
    "BGP Flap Detective",
    instructions=(
        "You are a senior network engineer specializing in BGP troubleshooting. "
        "For BGP issues, call check_bgp_neighbors first, then inspect interface errors, "
        "then run MTU checks and syslog correlation before recommending a fix."
    ),
)


def now_iso() -> str:
    return datetime.now().isoformat()


def ssh_run(device_name: str, command: str) -> str:
    if device_name not in SWITCH_INVENTORY:
        return (
            f"ERROR: '{device_name}' not found in inventory. "
            f"Known devices: {list(SWITCH_INVENTORY.keys())}"
        )

    params = SWITCH_INVENTORY[device_name]
    try:
        with ConnectHandler(**params) as conn:
            return conn.send_command(command, read_timeout=30)
    except NetmikoAuthenticationException:
        return f"ERROR: Authentication failed for {device_name} ({params['host']})."
    except NetmikoTimeoutException:
        return f"ERROR: Connection timed out for {device_name} ({params['host']})."
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {type(exc).__name__}: {exc}"


def parse_bgp_summary(raw: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
    def extract(pattern: str, default: str = "0") -> str:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        return match.group(1) if match else default

    line_protocol = extract(r"line protocol is (\w+)", "unknown")
    crc_errors = int(extract(r"(\d+)\s+CRC"))
    input_errors = int(extract(r"(\d+)\s+input error"))
    output_drops = int(extract(r"(\d+)\s+output drop"))
    carrier_transitions = int(extract(r"(\d+)\s+carrier transition"))
    interface_resets = int(extract(r"(\d+)\s+interface reset"))
    mtu = extract(r"MTU\s+(\d+)\s+bytes", "unknown")

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
    effective_mtu = 0
    failed_at: list[int] = []

    for size in sorted(results.keys()):
        if results[size]:
            effective_mtu = size
        else:
            failed_at.append(size)

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
    }


@mcp.tool
def check_bgp_neighbors(device_name: str) -> dict[str, Any]:
    device_type = SWITCH_INVENTORY.get(device_name, {}).get("device_type", "cisco_nxos")
    cmd = "show ip bgp summary" if "arista" in device_type else "show bgp ipv4 unicast summary"
    raw = ssh_run(device_name, cmd)

    if raw.startswith("ERROR"):
        return {"device": device_name, "error": raw, "timestamp": now_iso()}

    neighbors, flapping = parse_bgp_summary(raw)
    return {
        "device": device_name,
        "timestamp": now_iso(),
        "total_neighbors": len(neighbors),
        "established_count": sum(1 for n in neighbors if n["is_established"]),
        "problem_peers": flapping,
        "neighbors": neighbors,
        "raw_output": raw,
    }


@mcp.tool
def get_interface_errors(device_name: str, interface: str) -> dict[str, Any]:
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
        **parsed,
        "timestamp": now_iso(),
    }


@mcp.tool
def check_mtu_path(source_device: str, destination_ip: str) -> dict[str, Any]:
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


def main() -> None:
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
