"""Changelog for tracking and auditing operations.

Purpose:
-------
The ChangeLog records every operation executed against BAM, storing before/after
state to enable rollback generation and audit trails. Each import session creates
a new SQLite database file in .changelogs/ directory.

Database Schema:
---------------
```
changelog (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT NOT NULL,       -- Unique session identifier
    timestamp       TEXT NOT NULL,       -- ISO format timestamp
    row_id          TEXT NOT NULL,       -- CSV row ID
    object_type     TEXT NOT NULL,       -- Resource type (ip4_network, etc.)
    operation_type  TEXT NOT NULL,       -- CREATE, UPDATE, DELETE, NOOP
    success         BOOLEAN NOT NULL,    -- Whether operation succeeded
    resource_id     INTEGER,             -- BAM resource ID (if available)
    error_message   TEXT,                -- Error message if failed
    before_state    TEXT,                -- JSON: state before operation
    after_state     TEXT                 -- JSON: state after operation
)
```

Rollback Generation:
-------------------
The before_state and after_state fields enable rollback CSV generation:
- CREATE -> DELETE (using resource_id from after_state)
- UPDATE -> UPDATE (using before_state values)
- DELETE -> CREATE (using before_state values)

Session Isolation:
-----------------
Each session gets its own database file (.changelogs/<session_id>.db) to:
- Prevent concurrent imports from interfering
- Allow independent rollback per session
- Enable historical auditing

Usage:
-----
```python
changelog = ChangeLog(".changelogs/session123.db")

# Record successful CREATE
changelog.record_operation(
    session_id="session123",
    row_id="1",
    object_type="ip4_network",
    operation_type="CREATE",
    success=True,
    resource_id=456,
    after_state={"id": 456, "cidr": "10.1.0.0/24"}
)

# Generate rollback CSV
entries = changelog.get_session_entries("session123")
```
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ChangeLogEntry:
    """Entry in the changelog."""

    id: int | None
    session_id: str
    timestamp: str
    row_id: str
    object_type: str
    operation_type: str
    success: bool
    resource_id: int | None
    error_message: str | None
    before_state: str | None  # JSON
    after_state: str | None  # JSON


class ChangeLog:
    """
    SQLite-based changelog for auditing and rollback.

    Features:
    - Persistent storage of all operations
    - Stores before/after state for rollback
    - Session isolation
    - Query capability
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize ChangeLog.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: sqlite3.Connection = self._initialize_db()

    def _initialize_db(self) -> sqlite3.Connection:
        """Initialize database schema."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS changelog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                row_id TEXT NOT NULL,
                object_type TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                resource_id INTEGER,
                error_message TEXT,
                before_state TEXT,
                after_state TEXT
            )
        """
        )

        # Create indexes
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_id_changelog
            ON changelog(session_id)
        """
        )

        conn.commit()
        return conn

    def record_operation(
        self,
        session_id: str,
        row_id: str | int,
        object_type: str,
        operation_type: str,
        success: bool,
        resource_id: int | None = None,
        error_message: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> int:
        """
        Record an operation in the changelog.

        Args:
            session_id: Session identifier
            row_id: CSV row identifier
            object_type: Type of resource
            operation_type: Type of operation (create, update, delete)
            success: Whether operation succeeded
            resource_id: BAM resource ID
            error_message: Error details if failed
            before_state: Resource state before operation
            after_state: Resource state after operation

        Returns:
            ID of inserted record
        """
        entry = ChangeLogEntry(
            id=None,
            session_id=session_id,
            timestamp=datetime.utcnow().isoformat(),
            row_id=str(row_id),
            object_type=object_type,
            operation_type=operation_type,
            success=success,
            resource_id=resource_id,
            error_message=error_message,
            before_state=json.dumps(before_state) if before_state else None,
            after_state=json.dumps(after_state) if after_state else None,
        )

        cursor = self.conn.execute(
            """
            INSERT INTO changelog (
                session_id, timestamp, row_id, object_type, operation_type,
                success, resource_id, error_message, before_state, after_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.session_id,
                entry.timestamp,
                entry.row_id,
                entry.object_type,
                entry.operation_type,
                entry.success,
                entry.resource_id,
                entry.error_message,
                entry.before_state,
                entry.after_state,
            ),
        )

        self.conn.commit()
        entry_id = cursor.lastrowid
        assert entry_id is not None, "INSERT should always set lastrowid"
        return entry_id

    def get_session_entries(self, session_id: str) -> list[ChangeLogEntry]:
        """
        Get all entries for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of changelog entries
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM changelog
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )

        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        Get list of recent sessions with summary stats.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of session summaries
        """
        query = """
            SELECT
                session_id,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time,
                COUNT(*) as total_operations,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed
            FROM changelog
            GROUP BY session_id
            ORDER BY start_time DESC
            LIMIT ?
        """

        cursor = self.conn.execute(query, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def _row_to_entry(self, row: sqlite3.Row) -> ChangeLogEntry:
        """
        Convert SQLite row to ChangeLogEntry.

        Args:
            row: SQLite row

        Returns:
            ChangeLogEntry object
        """
        return ChangeLogEntry(
            id=row["id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            row_id=row["row_id"],
            object_type=row["object_type"],
            operation_type=row["operation_type"],
            success=bool(row["success"]),
            resource_id=row["resource_id"],
            error_message=row["error_message"],
            before_state=row["before_state"],
            after_state=row["after_state"],
        )

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self) -> "ChangeLog":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.close()
