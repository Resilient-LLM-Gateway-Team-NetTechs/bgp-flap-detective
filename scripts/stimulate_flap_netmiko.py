#!/usr/bin/env python3
"""
Vendor Network Device Interface Flap Stimulator

This utility deliberately toggles an interface down and back up on vendor
network devices (Cisco NX-OS, IOS, etc.) to simulate a BGP flap event for
lab testing and validation of BGP Flap Detective diagnostics.

Target platforms with Netmiko support:
- Cisco NX-OS (device_type='cisco_nxos')
- Cisco IOS/IOS-XE (device_type='cisco_ios')
- Arista EOS (device_type='arista_eos')
- Juniper JunOS (device_type='juniper_junos')

The script uses send_config_set() to enter configuration mode, issue shutdown,
wait for BGP to drop and detect the flap, then issue 'no shutdown' to bring the
interface back up and trigger reconvergence.

Usage:
    python stimulate_flap_netmiko.py --host 10.0.0.1 --username admin \\
        --password admin --platform cisco_nxos --iface Ethernet1/1 --down 5
"""
import argparse
import time
from netmiko import ConnectHandler


def toggle_interface(host: str, username: str, password: str, platform: str, iface: str, down_seconds: int, port: int = 22):
    """
    Toggle a vendor network interface down and back up via Netmiko configuration mode.
    
    This method uses proper configuration mode entry/exit via send_config_set()
    which is safer and cleaner than raw command strings for vendor devices.
    
    Args:
        host: Device IP or hostname
        username: SSH username
        password: SSH password
        platform: Netmiko device_type (e.g., 'cisco_nxos', 'arista_eos')
        iface: Interface name (e.g., 'Ethernet1/1', 'GigabitEthernet0/0/0')
        down_seconds: Seconds to keep interface down before bringing up
        port: SSH port (default 22)
    """
    dev = {
        "device_type": platform,
        "host": host,
        "username": username,
        "password": password,
        "port": port,
    }
    print(f"Connecting to {host} as {platform}...")
    with ConnectHandler(**dev) as conn:
        # Configuration commands to bring interface down
        # This triggers ADJCHANGE DOWN and BGP neighbor state drop
        cmds = [f"interface {iface}", "shutdown"]
        print(f"Sending shutdown to {iface}...")
        conn.send_config_set(cmds)
        time.sleep(down_seconds)
        # Bring interface back up; triggers ADJCHANGE UP and reconvergence
        print(f"Sending no shutdown to {iface}...")
        conn.send_config_set([f"interface {iface}", "no shutdown"]) 
    print("Done")


def main():
    """Parse CLI arguments and execute vendor device interface toggle."""
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
