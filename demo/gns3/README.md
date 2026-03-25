# GNS3: FRR Docker 3-node BGP topology and Netmiko stimulator

This file describes how to import an FRR Docker template into GNS3, build a 3-node BGP topology, and run a Netmiko stimulator to cause interface flaps.

Requirements
- GNS3 installed (desktop + server) on your machine or VM.
- Docker available for GNS3 to run FRR Docker containers.
- Python 3.10+ on your control host and `netmiko` installed.

Import FRR Docker template
1. In GNS3, open `File > Preferences > Docker > Images` and add the `frrouting/frr:latest` image (pull from Docker Hub).
2. Create a Docker template from the image and expose needed interfaces.

Create topology
1. New project: add three FRR Docker nodes (r1, r2, r3).
2. Connect r1-r2, r2-r3, r3-r1 (triangle). Start them.

Configure FRR on each node
- Use the GNS3 console to open a shell on each FRR node and configure `vtysh` with IPs and BGP neighbors.

Netmiko stimulator script
- Use `scripts/stimulate_flap_netmiko.py` to connect to a node and issue `shutdown`/`no shutdown` on a specific interface or `clear ip bgp` to force flaps.

Example run (repo root):

```bash
source ./.venv/bin/activate
pip install -r requirements.txt
./scripts/stimulate_flap_netmiko.py --host 192.168.122.10 --username admin --password pass --platform cisco_nxos --iface Ethernet1/1 --down 5
```

This will shutdown `Ethernet1/1` for 5 seconds then bring it up.

Notes and tips
- FRR on Docker often uses Linux interface names (eth0, eth1); on vendor images use platform-specific interface names.
- If your FRR Docker nodes are accessible only from the GNS3 VM, run the stimulator from inside the VM or use NAT/port forwarding.
