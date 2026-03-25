# EVE-NG: FRR-based BGP topology for BGP Flap Detective

This guide shows how to build a simple 3-node FRR BGP topology in EVE-NG and how to trigger interface flaps from your control host.

Overview
- Topology: 3 FRR routers in a triangle (r1, r2, r3) running BGP. The MCP server runs on your laptop/host and watches for BGP/route events.
- We'll use the official FRRouting Docker image (frrouting/frr) as the router nodes.

What you need
- EVE-NG (community or pro) installed and accessible.
- Access to EVE-NG filesystem (SSH into the EVE host) to create a Docker template (or use the GUI template wizard).
- Python 3.10+ on your control host and `netmiko` installed for the stimulator script.

Create a Docker template for FRR (short version)
1. On the EVE host, pull the FRR image (or upload a prepared image):

```bash
docker pull frrouting/frr:latest
```

2. Create an EVE Docker template following EVE docs (example paths):
- Create folder: `/opt/unetlab/addons/docker/frr` and copy a small wrapper or use the GUI to add a Docker template.

3. In the EVE GUI create a new lab, add three `frr` Docker nodes and connect them in a triangle.

Basic FRR configuration (on each node)
- Configure interfaces with addresses and add BGP neighbors. Example snippet for `vtysh`:

```
configure terminal
interface eth0
 ip address 10.0.0.1/24
exit
router bgp 65001
 neighbor 10.0.0.2 remote-as 65002
 neighbor 10.0.0.3 remote-as 65003
exit
write
```

Stimulate a flap from your control host
- Use the `scripts/stimulate_flap.py` script (below) to SSH into a node and toggle an interface using `ip` commands.

Example usage (from repo root):

```bash
source ./.venv/bin/activate
pip install -r requirements.txt  # ensure netmiko/paramiko installed
./scripts/stimulate_flap.py --host 192.168.1.100 --username root --password pass --iface eth1 --down 5
```

This will bring `eth1` down for 5 seconds then bring it up again, producing a BGP flap.

Notes
- See `demo/gns3/README.md` for parallel GNS3 instructions.
- If you prefer automation, export a prepared lab file from EVE and I can provide a lab export template (requires generating the EVE lab file on the EVE host).
