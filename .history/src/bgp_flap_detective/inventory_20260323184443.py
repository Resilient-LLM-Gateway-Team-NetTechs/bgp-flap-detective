import json
import os
from pathlib import Path
from typing import Any

DEFAULT_INVENTORY: dict[str, dict[str, Any]] = {
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
    """Load inventory from JSON file if configured, else return defaults."""
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
