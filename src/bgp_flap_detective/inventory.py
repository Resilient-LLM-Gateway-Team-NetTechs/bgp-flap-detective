"""
Network Device Inventory Module

Manages device connection parameters and provides flexible sourcing from
default hardcoded inventory or external JSON files. Supports environment
variable overrides for credentials and connection attributes.
"""

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_INVENTORY: dict[str, dict[str, Any]] = {
    # Default spine-leaf test topology devices with environment variable overrides
    "spine-1": {
        "host": "192.168.1.10",
        "device_type": os.getenv("BFD_DEFAULT_DEVICE_TYPE", "cisco_nxos"),
        "username": os.getenv("BFD_DEFAULT_USERNAME", "admin"),
        "password": os.getenv("BFD_DEFAULT_PASSWORD", "admin"),
        "port": int(os.getenv("BFD_DEFAULT_PORT", "22")),
    },
    "spine-2": {
        "host": "192.168.1.11",
        "device_type": os.getenv("BFD_DEFAULT_DEVICE_TYPE", "cisco_nxos"),
        "username": os.getenv("BFD_DEFAULT_USERNAME", "admin"),
        "password": os.getenv("BFD_DEFAULT_PASSWORD", "admin"),
        "port": int(os.getenv("BFD_DEFAULT_PORT", "22")),
    },
    "leaf-01": {
        "host": "192.168.1.20",
        "device_type": os.getenv("BFD_DEFAULT_DEVICE_TYPE", "cisco_nxos"),
        "username": os.getenv("BFD_DEFAULT_USERNAME", "admin"),
        "password": os.getenv("BFD_DEFAULT_PASSWORD", "admin"),
        "port": int(os.getenv("BFD_DEFAULT_PORT", "22")),
    },
    "leaf-02": {
        "host": "192.168.1.21",
        "device_type": os.getenv("BFD_DEFAULT_DEVICE_TYPE", "cisco_nxos"),
        "username": os.getenv("BFD_DEFAULT_USERNAME", "admin"),
        "password": os.getenv("BFD_DEFAULT_PASSWORD", "admin"),
        "port": int(os.getenv("BFD_DEFAULT_PORT", "22")),
    },
}


def load_inventory() -> dict[str, dict[str, Any]]:
    """
    Load device inventory from JSON file or return hardcoded defaults.
    
    This function provides flexible device sourcing:
    - Uses external JSON file if BFD_INVENTORY_FILE environment variable points to valid file
    - Falls back to DEFAULT_INVENTORY if file missing or invalid
    - External file should be valid JSON mapping device names to Netmiko connection dicts
    
    Environment Variables:
        BFD_INVENTORY_FILE: Path to JSON inventory file, e.g., "/etc/bgp-flap/inventory.json"
        
    Returns:
        Dict mapping device names (strings) to connection parameter dicts for Netmiko
        
    Example JSON format:
    {
        "my-switch": {
            "host": "10.0.0.1",
            "device_type": "cisco_nxos",
            "username": "admin",
            "password": "secret",
            "port": 22
        }
    }
    """
    inventory_file = os.getenv("BFD_INVENTORY_FILE", "").strip()
    if not inventory_file:
        return DEFAULT_INVENTORY

    path = Path(inventory_file)
    if not path.exists():
        return DEFAULT_INVENTORY

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_INVENTORY

    if not isinstance(data, dict):
        return DEFAULT_INVENTORY

    return data
