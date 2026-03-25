#!/usr/bin/env python3
"""Netmiko stimulator for vendor images (Cisco NX-OS / IOS-like)

Will issue `interface <iface>` + `shutdown` / sleep / `no shutdown` or `clear ip bgp` depending on options.
"""
import argparse
import time
from netmiko import ConnectHandler


def toggle_interface(host: str, username: str, password: str, platform: str, iface: str, down_seconds: int, port: int = 22):
    dev = {
        "device_type": platform,
        "host": host,
        "username": username,
        "password": password,
        "port": port,
    }
    print(f"Connecting to {host} as {platform}...")
    with ConnectHandler(**dev) as conn:
        cmds = [f"interface {iface}", "shutdown"]
        print(f"Sending shutdown to {iface}...")
        conn.send_config_set(cmds)
        time.sleep(down_seconds)
        print(f"Sending no shutdown to {iface}...")
        conn.send_config_set([f"interface {iface}", "no shutdown"]) 
    print("Done")


def main():
    p = argparse.ArgumentParser(description="Toggle interface on vendor device via Netmiko")
    p.add_argument("--host", required=True)
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--platform", required=True, help="netmiko platform like cisco_nxos or cisco_ios")
    p.add_argument("--iface", required=True, help="interface name, e.g. Ethernet1/1 or GigabitEthernet0/1")
    p.add_argument("--down", type=int, default=5, help="seconds to keep interface down")
    p.add_argument("--port", type=int, default=22)
    args = p.parse_args()

    toggle_interface(args.host, args.username, args.password, args.platform, args.iface, args.down, args.port)


if __name__ == "__main__":
    main()
