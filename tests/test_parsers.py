"""
Unit tests for BGP Flap Detective parsing and analysis functions.

This test suite validates the correctness of CLI output parsing logic and
diagnostic heuristics without requiring live devices. Tests use synthetic
output fixtures that mimic real Cisco NX-OS and similar platforms.
"""

from bgp_flap_detective import server
from bgp_flap_detective.server import analyze_mtu_results, parse_bgp_summary, parse_interface_output


# Fixture: Sample BGP neighbor summary output from Cisco NX-OS
BGP_SAMPLE = """
Neighbor        V    AS MsgRcvd MsgSent TblVer InQ OutQ Up/Down  State/PfxRcd
192.168.1.20    4 65001   1000    1200    124   0    0 1d02h     224
192.168.1.21    4 65002    100     120    124   0    0 00:00:12  Active
"""

# Fixture: Sample interface output with errors
INTF_SAMPLE = """
Ethernet1/1 is up, line protocol is up
  MTU 9216 bytes
  3 input error, 150 CRC, 0 frame, 0 overrun, 0 ignored
  0 output drop
  8 carrier transition
  2 interface reset
"""


def test_parse_bgp_summary_detects_problem_peer() -> None:
    """Verify that non-established neighbors are correctly identified as problematic."""
    neighbors, flapping = parse_bgp_summary(BGP_SAMPLE)
    assert len(neighbors) == 2
    assert neighbors[0]["is_established"] is True
    assert neighbors[1]["is_established"] is False
    assert flapping[0]["peer_ip"] == "192.168.1.21"


def test_parse_interface_output_detects_errors() -> None:
    """Verify that high error counters trigger problem detection logic."""
    parsed = parse_interface_output(INTF_SAMPLE)
    assert parsed["line_protocol"] == "up"
    assert parsed["crc_errors"] == 150
    assert parsed["has_problems"] is True
    assert any("CRC" in msg for msg in parsed["problems_detected"])


def test_analyze_mtu_results() -> None:
    """Verify MTU path discovery correctly identifies breakpoints."""
    analyzed = analyze_mtu_results({576: True, 1400: True, 1450: False, 1500: False})
    assert analyzed["effective_path_mtu"] == 1400
    assert analyzed["mtu_problem_detected"] is True


def test_mock_command_output_bgp_summary() -> None:
    """Verify mock mode returns realistic BGP summary data for demo purposes."""
    output = server._mock_command_output("spine-1", "show bgp ipv4 unicast summary")
    neighbors, flapping = parse_bgp_summary(output)
    assert len(neighbors) == 2
    assert len(flapping) == 1


def test_run_mock_investigation_returns_full_bundle(monkeypatch) -> None:
    """Verify the full investigation bundle can be generated in mock mode for demos."""
    monkeypatch.setattr(server, "MOCK_MODE", True)
    result = server.run_mock_investigation()

    assert result["scenario"] == "mock_bgp_flap_demo"
    assert result["mock_mode_active"] is True
    assert result["suggested_root_cause"] in {"mtu_mismatch", "crc_errors", "hold_timer", "route_policy"}
    assert "steps" in result
    assert "recommendation" in result["steps"]
