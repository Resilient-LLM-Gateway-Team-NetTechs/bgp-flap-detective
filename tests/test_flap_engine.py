"""Tests for persistent flap detection and incident lifecycle."""

from __future__ import annotations

import sqlite3

from bgp_flap_detective.flap_engine import DetectionConfig, EventStore, FlapDetector


class _ClockedDetector:
    """Helper wrapper to avoid importing server globals in these tests."""

    def __init__(self, store: EventStore) -> None:
        self.detector = FlapDetector(
            store=store,
            config=DetectionConfig(flap_window_seconds=300, flap_threshold=2, close_stable_seconds=120),
        )

    def process(self, is_established: bool) -> None:
        self.detector.process_snapshot(
            device_name="spine-1",
            neighbors=[
                {
                    "peer_ip": "192.0.2.1",
                    "peer_as": "65001",
                    "state_or_prefixes": "224" if is_established else "Active",
                    "up_down": "00:00:10",
                    "is_established": is_established,
                }
            ],
        )


def test_incident_opens_after_threshold(tmp_path) -> None:
    store = EventStore(str(tmp_path / "events.db"))
    engine = _ClockedDetector(store)

    engine.process(True)
    engine.process(False)
    engine.process(True)

    incidents = store.get_incidents(status="open", limit=10)
    assert len(incidents) == 1
    assert incidents[0]["device_name"] == "spine-1"
    assert incidents[0]["peer_ip"] == "192.0.2.1"
    assert incidents[0]["flap_count"] >= 2


def test_incident_closes_when_stable(tmp_path) -> None:
    db_path = tmp_path / "events.db"
    store = EventStore(str(db_path))
    detector = FlapDetector(
        store=store,
        config=DetectionConfig(flap_window_seconds=300, flap_threshold=2, close_stable_seconds=1),
    )

    # Trigger open incident.
    detector.process_snapshot(
        "spine-1",
        [
            {"peer_ip": "192.0.2.1", "is_established": True, "state_or_prefixes": "200", "up_down": "1d"},
        ],
    )
    detector.process_snapshot(
        "spine-1",
        [
            {"peer_ip": "192.0.2.1", "is_established": False, "state_or_prefixes": "Active", "up_down": "00:00:01"},
        ],
    )
    detector.process_snapshot(
        "spine-1",
        [
            {"peer_ip": "192.0.2.1", "is_established": True, "state_or_prefixes": "200", "up_down": "00:00:01"},
        ],
    )

    # Age previous snapshots so stability window sees only fresh "up" state.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE peer_snapshots
            SET created_at = '1970-01-01T00:00:00+00:00'
            WHERE device_name = 'spine-1' AND peer_ip = '192.0.2.1'
            """
        )

    # Repeated stable snapshots should close the incident quickly due to short close window.
    detector.process_snapshot(
        "spine-1",
        [
            {"peer_ip": "192.0.2.1", "is_established": True, "state_or_prefixes": "200", "up_down": "00:00:02"},
        ],
    )

    all_incidents = store.get_incidents(status="all", limit=20)
    assert len(all_incidents) == 1
    assert all_incidents[0]["status"] == "closed"


def test_peer_stats_sort_by_instability(tmp_path) -> None:
    store = EventStore(str(tmp_path / "events.db"))
    detector = FlapDetector(
        store=store,
        config=DetectionConfig(flap_window_seconds=300, flap_threshold=3, close_stable_seconds=60),
    )

    for state in [True, False, True, False, True]:
        detector.process_snapshot(
            "spine-1",
            [
                {"peer_ip": "192.0.2.10", "is_established": state, "state_or_prefixes": "200", "up_down": "00:00:10"},
                {"peer_ip": "192.0.2.20", "is_established": True, "state_or_prefixes": "200", "up_down": "1d"},
            ],
        )

    stats = store.get_peer_stats("spine-1", "1970-01-01T00:00:00+00:00")
    assert len(stats) == 2
    assert stats[0]["peer_ip"] == "192.0.2.10"
    assert stats[0]["transitions"] >= stats[1]["transitions"]
