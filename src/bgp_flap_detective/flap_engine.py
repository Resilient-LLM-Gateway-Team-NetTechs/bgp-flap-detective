"""Stateful BGP flap detection and incident persistence.

This module keeps detection logic separate from MCP transport concerns.
It stores neighbor snapshots in SQLite and manages incident lifecycle.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class DetectionConfig:
    """Runtime settings for flap detection behavior."""

    flap_window_seconds: int = 300
    flap_threshold: int = 3
    close_stable_seconds: int = 300


@dataclass(slots=True)
class IncidentUpdate:
    """Result of processing one device snapshot."""

    opened: list[dict[str, Any]]
    closed: list[dict[str, Any]]
    active: list[dict[str, Any]]


class EventStore:
    """SQLite-backed store for snapshots and incidents."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        if self.db_path.parent != Path(""):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS peer_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    peer_ip TEXT NOT NULL,
                    is_established INTEGER NOT NULL,
                    state_or_prefixes TEXT,
                    up_down TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    device_name TEXT NOT NULL,
                    peer_ip TEXT NOT NULL,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    flap_count INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    close_reason TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_peer_snapshots_lookup
                ON peer_snapshots (device_name, peer_ip, created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_incidents_status_lookup
                ON incidents (status, device_name, peer_ip, updated_at)
                """
            )

    def insert_snapshot(self, created_at: str, device_name: str, neighbor: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO peer_snapshots (
                    created_at, device_name, peer_ip, is_established, state_or_prefixes, up_down
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    device_name,
                    str(neighbor.get("peer_ip", "")),
                    1 if neighbor.get("is_established") else 0,
                    str(neighbor.get("state_or_prefixes", "")),
                    str(neighbor.get("up_down", "")),
                ),
            )

    def get_recent_peer_states(
        self,
        device_name: str,
        peer_ip: str,
        since_time: str,
    ) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT created_at, is_established
                FROM peer_snapshots
                WHERE device_name = ? AND peer_ip = ? AND created_at >= ?
                ORDER BY created_at ASC
                """,
                (device_name, peer_ip, since_time),
            ).fetchall()
        return rows

    def get_latest_peer_state(self, device_name: str, peer_ip: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT created_at, is_established
                FROM peer_snapshots
                WHERE device_name = ? AND peer_ip = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (device_name, peer_ip),
            ).fetchone()
        return row

    def get_open_incident(self, device_name: str, peer_ip: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM incidents
                WHERE device_name = ? AND peer_ip = ? AND status = 'open'
                ORDER BY id DESC
                LIMIT 1
                """,
                (device_name, peer_ip),
            ).fetchone()
        return row

    def open_incident(
        self,
        created_at: str,
        device_name: str,
        peer_ip: str,
        flap_count: int,
        severity: str,
        summary: str,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO incidents (
                    created_at,
                    updated_at,
                    device_name,
                    peer_ip,
                    status,
                    start_time,
                    flap_count,
                    severity,
                    summary
                )
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
                """,
                (
                    created_at,
                    created_at,
                    device_name,
                    peer_ip,
                    created_at,
                    flap_count,
                    severity,
                    summary,
                ),
            )
            return int(cur.lastrowid)

    def refresh_open_incident(self, incident_id: int, updated_at: str, flap_count: int, severity: str, summary: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE incidents
                SET updated_at = ?, flap_count = ?, severity = ?, summary = ?
                WHERE id = ?
                """,
                (updated_at, flap_count, severity, summary, incident_id),
            )

    def close_incident(self, incident_id: int, closed_at: str, reason: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE incidents
                SET status = 'closed', updated_at = ?, end_time = ?, close_reason = ?
                WHERE id = ?
                """,
                (closed_at, closed_at, reason, incident_id),
            )

    def get_incidents(self, status: str = "all", limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM incidents"
        params: tuple[Any, ...] = ()
        if status in {"open", "closed"}:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params = (*params, max(1, min(limit, 500)))

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_peer_stats(self, device_name: str, since_time: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            peers = conn.execute(
                """
                SELECT DISTINCT peer_ip
                FROM peer_snapshots
                WHERE device_name = ? AND created_at >= ?
                """,
                (device_name, since_time),
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in peers:
            peer_ip = str(row["peer_ip"])
            states = self.get_recent_peer_states(device_name, peer_ip, since_time)
            transitions = _count_state_transitions(states)
            down_count = sum(1 for s in states if int(s["is_established"]) == 0)
            results.append(
                {
                    "peer_ip": peer_ip,
                    "snapshots": len(states),
                    "transitions": transitions,
                    "down_samples": down_count,
                }
            )

        results.sort(key=lambda item: (item["transitions"], item["down_samples"]), reverse=True)
        return results


def _count_state_transitions(states: list[sqlite3.Row]) -> int:
    transitions = 0
    previous: int | None = None
    for state in states:
        current = int(state["is_established"])
        if previous is not None and previous != current:
            transitions += 1
        previous = current
    return transitions


def _severity_for_flaps(flap_count: int) -> str:
    if flap_count >= 8:
        return "critical"
    if flap_count >= 5:
        return "high"
    if flap_count >= 3:
        return "medium"
    return "low"


class FlapDetector:
    """Stateful detector for BGP peer instability."""

    def __init__(self, store: EventStore, config: DetectionConfig) -> None:
        self.store = store
        self.config = config

    def process_snapshot(self, device_name: str, neighbors: list[dict[str, Any]]) -> IncidentUpdate:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        opened: list[dict[str, Any]] = []
        closed: list[dict[str, Any]] = []
        active: list[dict[str, Any]] = []

        for neighbor in neighbors:
            peer_ip = str(neighbor.get("peer_ip", "")).strip()
            if not peer_ip:
                continue

            self.store.insert_snapshot(now_iso, device_name, neighbor)
            since = (now - timedelta(seconds=self.config.flap_window_seconds)).isoformat()
            recent_states = self.store.get_recent_peer_states(device_name, peer_ip, since)
            transitions = _count_state_transitions(recent_states)
            flap_count = transitions
            severity = _severity_for_flaps(flap_count)
            is_established = bool(neighbor.get("is_established"))

            summary = (
                f"Peer {peer_ip} had {flap_count} state transitions in the last "
                f"{self.config.flap_window_seconds}s"
            )

            open_incident = self.store.get_open_incident(device_name, peer_ip)
            if flap_count >= self.config.flap_threshold:
                if open_incident is None:
                    incident_id = self.store.open_incident(
                        created_at=now_iso,
                        device_name=device_name,
                        peer_ip=peer_ip,
                        flap_count=flap_count,
                        severity=severity,
                        summary=summary,
                    )
                    opened.append(
                        {
                            "id": incident_id,
                            "device_name": device_name,
                            "peer_ip": peer_ip,
                            "flap_count": flap_count,
                            "severity": severity,
                            "summary": summary,
                        }
                    )
                else:
                    self.store.refresh_open_incident(
                        incident_id=int(open_incident["id"]),
                        updated_at=now_iso,
                        flap_count=flap_count,
                        severity=severity,
                        summary=summary,
                    )
                active.append(
                    {
                        "device_name": device_name,
                        "peer_ip": peer_ip,
                        "flap_count": flap_count,
                        "severity": severity,
                        "is_established": is_established,
                    }
                )
                continue

            if open_incident is None:
                continue

            stable_since = (now - timedelta(seconds=self.config.close_stable_seconds)).isoformat()
            stability_window = self.store.get_recent_peer_states(device_name, peer_ip, stable_since)
            has_down_state = any(int(state["is_established"]) == 0 for state in stability_window)

            if is_established and not has_down_state:
                self.store.close_incident(
                    incident_id=int(open_incident["id"]),
                    closed_at=now_iso,
                    reason="peer stable in close window",
                )
                closed.append(
                    {
                        "id": int(open_incident["id"]),
                        "device_name": device_name,
                        "peer_ip": peer_ip,
                        "reason": "peer stable in close window",
                    }
                )

        return IncidentUpdate(opened=opened, closed=closed, active=active)
