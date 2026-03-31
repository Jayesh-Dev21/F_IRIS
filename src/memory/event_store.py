"""Event storage module using SQLite for IRIS Security Agent."""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from src.config import StorageConfig

logger = logging.getLogger(__name__)


class SecurityEvent:
    """Represents a security event."""

    def __init__(
        self,
        scene_description: str,
        people_count: int,
        activity: str,
        threat_level: str,
        reasoning: str,
        snapshot_path: Optional[str] = None,
        metadata: Optional[Dict] = None,
        event_id: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ):
        self.event_id = event_id
        self.timestamp = timestamp or datetime.now()
        self.scene_description = scene_description
        self.people_count = people_count
        self.activity = activity  # normal, suspicious, alert
        self.threat_level = threat_level  # none, low, medium, high
        self.reasoning = reasoning
        self.snapshot_path = snapshot_path
        self.metadata = metadata or {}

    def to_dict(self) -> Dict:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "scene_description": self.scene_description,
            "people_count": self.people_count,
            "activity": self.activity,
            "threat_level": self.threat_level,
            "reasoning": self.reasoning,
            "snapshot_path": self.snapshot_path,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SecurityEvent":
        """Create event from dictionary."""
        timestamp = None
        if data.get("timestamp"):
            timestamp = datetime.fromisoformat(data["timestamp"])

        return cls(
            event_id=data.get("event_id"),
            timestamp=timestamp,
            scene_description=data["scene_description"],
            people_count=data["people_count"],
            activity=data["activity"],
            threat_level=data["threat_level"],
            reasoning=data["reasoning"],
            snapshot_path=data.get("snapshot_path"),
            metadata=data.get("metadata", {}),
        )


class EventStore:
    """SQLite-based event storage."""

    def __init__(self, config: StorageConfig):
        """
        Initialize event store.

        Args:
            config: Storage configuration
        """
        self.config = config
        self.db_path = Path(config.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_db()

    def _initialize_db(self):
        """Create database tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        cursor = self.conn.cursor()

        # Create events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                scene_description TEXT NOT NULL,
                people_count INTEGER DEFAULT 0,
                activity VARCHAR(50) NOT NULL,
                threat_level VARCHAR(20) NOT NULL,
                reasoning TEXT,
                snapshot_path TEXT,
                metadata JSON
            )
        """)

        # Create indices for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON events(timestamp)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_threat_level 
            ON events(threat_level)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_activity 
            ON events(activity)
        """)

        self.conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def add_event(self, event: SecurityEvent) -> int:
        """
        Add a new event to the database.

        Args:
            event: SecurityEvent to store

        Returns:
            Event ID of the inserted event
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO events (
                timestamp, scene_description, people_count, 
                activity, threat_level, reasoning, 
                snapshot_path, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                event.timestamp.isoformat(),
                event.scene_description,
                event.people_count,
                event.activity,
                event.threat_level,
                event.reasoning,
                event.snapshot_path,
                json.dumps(event.metadata),
            ),
        )

        self.conn.commit()
        event_id = cursor.lastrowid

        logger.info(
            f"Event #{event_id} stored: {event.threat_level} - {event.scene_description}"
        )

        return event_id

    def get_event(self, event_id: int) -> Optional[SecurityEvent]:
        """
        Get event by ID.

        Args:
            event_id: Event ID

        Returns:
            SecurityEvent or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_event(row)

    def get_recent_events(self, limit: int = 10) -> List[SecurityEvent]:
        """
        Get most recent events.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of SecurityEvents
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM events 
            ORDER BY timestamp DESC 
            LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_events_by_timerange(
        self, start: datetime, end: datetime
    ) -> List[SecurityEvent]:
        """
        Get events within a time range.

        Args:
            start: Start datetime
            end: End datetime

        Returns:
            List of SecurityEvents
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM events 
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC
        """,
            (start.isoformat(), end.isoformat()),
        )

        rows = cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_events_by_threat_level(
        self, threat_level: str, limit: Optional[int] = None
    ) -> List[SecurityEvent]:
        """
        Get events by threat level.

        Args:
            threat_level: Threat level to filter by
            limit: Maximum number of events

        Returns:
            List of SecurityEvents
        """
        cursor = self.conn.cursor()

        query = """
            SELECT * FROM events 
            WHERE threat_level = ?
            ORDER BY timestamp DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query, (threat_level,))

        rows = cursor.fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_events_today(self) -> List[SecurityEvent]:
        """Get all events from today."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.now()
        return self.get_events_by_timerange(today_start, today_end)

    def get_statistics(self) -> Dict:
        """
        Get statistics about stored events.

        Returns:
            Dictionary with statistics
        """
        cursor = self.conn.cursor()

        # Total events
        cursor.execute("SELECT COUNT(*) as count FROM events")
        total = cursor.fetchone()["count"]

        # Events by threat level
        cursor.execute("""
            SELECT threat_level, COUNT(*) as count 
            FROM events 
            GROUP BY threat_level
        """)
        threat_counts = {row["threat_level"]: row["count"] for row in cursor.fetchall()}

        # Events today
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cursor.execute(
            """
            SELECT COUNT(*) as count 
            FROM events 
            WHERE timestamp >= ?
        """,
            (today_start.isoformat(),),
        )
        today_count = cursor.fetchone()["count"]

        # Average people count
        cursor.execute("SELECT AVG(people_count) as avg FROM events")
        avg_people = cursor.fetchone()["avg"] or 0

        return {
            "total_events": total,
            "events_today": today_count,
            "threat_level_distribution": threat_counts,
            "average_people_count": round(avg_people, 2),
        }

    def cleanup_old_snapshots(self):
        """Delete snapshot files older than configured age."""
        cutoff_date = datetime.now() - timedelta(days=self.config.max_snapshot_age_days)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT snapshot_path FROM events 
            WHERE timestamp < ? AND snapshot_path IS NOT NULL
        """,
            (cutoff_date.isoformat(),),
        )

        rows = cursor.fetchall()
        deleted_count = 0

        for row in rows:
            snapshot_path = Path(row["snapshot_path"])
            if snapshot_path.exists():
                try:
                    snapshot_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete {snapshot_path}: {e}")

        logger.info(f"Cleaned up {deleted_count} old snapshots")
        return deleted_count

    def _row_to_event(self, row: sqlite3.Row) -> SecurityEvent:
        """Convert database row to SecurityEvent."""
        metadata = {}
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse metadata for event {row['id']}")

        return SecurityEvent(
            event_id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            scene_description=row["scene_description"],
            people_count=row["people_count"],
            activity=row["activity"],
            threat_level=row["threat_level"],
            reasoning=row["reasoning"],
            snapshot_path=row["snapshot_path"],
            metadata=metadata,
        )

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
