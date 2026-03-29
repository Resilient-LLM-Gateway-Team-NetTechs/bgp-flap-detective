#!/usr/bin/env python3
"""
Interface Flap Stimulation Script for Linux/FRR Routers

This utility deliberately toggles an interface down and back up to simulate
a BGP flap event for lab testing. Useful for validating that BGP Flap Detective
correctly identifies the physical layer trigger.

Target platforms:
- FRR (Free Range Routing) containers
- Linux-based router images
- Any device where Netmiko "linux" driver works

Usage:
    python stimulate_flap.py --host 10.0.0.1 --username root --password pass \\
        --iface eth1 --down 5
        
This command brings eth1 down for 5 seconds (allowing observation of the flap),
then brings it back up.
"""
import argparse
import time
from typing import Optional
from netmiko import ConnectHandler


def toggle_interface(host: str, username: str, password: str, iface: str, down_seconds: int, port: int = 22) -> None:
    """
    Toggle a network interface down and up via SSH to simulate a flap.
    
    Connects via Netmiko, issues 'ip link set ... down', waits, then 'ip link set ... up'.
    This simulates a sudden physical layer interruption or transceiver reset.
    
    Args:
        host: Target device IP or hostname
        username: SSH username (typically root for lab containers)
        password: SSH password  
        iface: Interface name (e.g., eth0, eth1)
        down_seconds: How long to keep interface down
        port: SSH port (default 22)
    """
    dev = {
        "device_type": "linux",
        "host": host,
        "username": username,
        "password": password,
        "port": port,
    }
    print(f"Connecting to {host}...")
    with ConnectHandler(**dev) as conn:
        print(f"Shutting {iface} down...")
        # Interface down triggers BGP DROP event and clears neighborships
        conn.send_command(f"sudo ip link set dev {iface} down")
        time.sleep(down_seconds)
        print(f"Bringing {iface} up...")
        # Interface up triggers BGP ADJCHANGE UP and route reconvergence
        conn.send_command(f"sudo ip link set dev {iface} up")
    print("Done")


def main():
    """Parse arguments and execute the interface toggle operation."""
    p = argparse.ArgumentParser(description="Toggle interface on a remote Linux/FRR node")
    p.add_argument("--host", required=True)
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--iface", required=True, help="interface name, e.g. eth1")
    p.add_argument("--down", type=int, default=5, help="seconds to keep interface down")
    p.add_argument("--port", type=int, default=22)
    args = p.parse_args()

    toggle_interface(args.host, args.username, args.password, args.iface, args.down, args.port)


if __name__ == "__main__":
    main()
