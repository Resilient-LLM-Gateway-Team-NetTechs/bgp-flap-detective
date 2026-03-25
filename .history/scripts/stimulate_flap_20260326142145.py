#!/usr/bin/env python3
"""Generic stimulator: SSH to host and toggle an interface (uses paramiko/netmiko).

Works with FRR containers (uses shell `ip link set dev ... down`/`up`) and other Linux-based router images.
"""
import argparse
import time
from typing import Optional
from netmiko import ConnectHandler


def toggle_interface(host: str, username: str, password: str, iface: str, down_seconds: int, port: int = 22) -> None:
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
        conn.send_command(f"sudo ip link set dev {iface} down")
        time.sleep(down_seconds)
        print(f"Bringing {iface} up...")
        conn.send_command(f"sudo ip link set dev {iface} up")
    print("Done")


def main():
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
