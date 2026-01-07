"""Checkpoint manager for resumable imports."""

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
class Checkpoint:
    """Checkpoint representing a resumable point in execution."""

    id: int | None
    session_id: str
    timestamp: str
    batch_id: int
    operation_index: int
    completed_operations: int
    total_operations: int
    status: str  # in_progress, completed, failed
    input_hash: str | None
    metadata: str | None  # JSON


class CheckpointManager:
    """
    SQLite-based checkpoint manager for resume support.

    Features:
    - Save checkpoints after each batch
    - Resume from last successful checkpoint
    - Track session progress
    - Automatic cleanup of old checkpoints
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize CheckpointManager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn: sqlite3.Connection = self._initialize_db()

        logger.info("CheckpointManager initialized", db_path=str(self.db_path))

    def _initialize_db(self) -> sqlite3.Connection:
        """Initialize database schema."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Create checkpoints table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                batch_id INTEGER NOT NULL,
                operation_index INTEGER NOT NULL,
                completed_operations INTEGER NOT NULL,
                total_operations INTEGER NOT NULL,
                status TEXT NOT NULL,
                input_hash TEXT,
                metadata TEXT
            )
        """
        )

        # Add input_hash column if it doesn't exist (migration for existing DBs)
        try:
            conn.execute("ALTER TABLE checkpoints ADD COLUMN input_hash TEXT")
            logger.info("Added input_hash column to checkpoints table")
        except sqlite3.OperationalError:
            # Column likely already exists
            pass

        # Create created_resources table for deferred resolution on resume
        # This stores the mapping of resource keys (CIDRs, names) to BAM IDs
        # so that when resuming an interrupted session, deferred resolutions
        # for resources created in skipped batches can still be satisfied.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS created_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_key TEXT NOT NULL,
                bam_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(session_id, resource_type, resource_key)
            )
        """
        )

        # Create indexes
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_session_id
            ON checkpoints(session_id)
        """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON checkpoints(timestamp)
        """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_created_resources_session
            ON created_resources(session_id)
        """
        )

        conn.commit()

        logger.debug("Database schema initialized")
        return conn

    def save_checkpoint(
        self,
        session_id: str,
        batch_id: int,
        operation_index: int,
        completed_operations: int,
        total_operations: int,
        status: str = "in_progress",
        input_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """
        Save a checkpoint.

        Args:
            session_id: Session identifier
            batch_id: Current batch ID
            operation_index: Current operation index within batch
            completed_operations: Number of completed operations
            total_operations: Total operations in plan
            status: Checkpoint status
            metadata: Additional metadata

        Returns:
            Checkpoint ID
        """
        checkpoint = Checkpoint(
            id=None,
            session_id=session_id,
            timestamp=datetime.utcnow().isoformat(),
            batch_id=batch_id,
            operation_index=operation_index,
            completed_operations=completed_operations,
            total_operations=total_operations,
            status=status,
            metadata=json.dumps(metadata) if metadata else None,
            input_hash=input_hash,
        )

        cursor = self.conn.execute(
            """
            INSERT INTO checkpoints (
                session_id, timestamp, batch_id, operation_index,
                completed_operations, total_operations, status, input_hash, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint.session_id,
                checkpoint.timestamp,
                checkpoint.batch_id,
                checkpoint.operation_index,
                checkpoint.completed_operations,
                checkpoint.total_operations,
                checkpoint.status,
                checkpoint.input_hash,
                checkpoint.metadata,
            ),
        )

        self.conn.commit()
        checkpoint_id = cursor.lastrowid
        assert checkpoint_id is not None, "INSERT should always set lastrowid"

        logger.debug(
            "Checkpoint saved",
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            batch_id=batch_id,
            completed=completed_operations,
            total=total_operations,
        )

        return checkpoint_id

    def get_latest_checkpoint(self, session_id: str) -> Checkpoint | None:
        """
        Get the latest checkpoint for a session.

        Args:
            session_id: Session identifier

        Returns:
            Last checkpoint or None
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM checkpoints
            WHERE session_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        checkpoint = self._row_to_checkpoint(row)

        logger.debug(
            "Retrieved latest checkpoint",
            session_id=session_id,
            batch_id=checkpoint.batch_id,
            status=checkpoint.status,
        )

        return checkpoint

    def can_resume(self, session_id: str) -> bool:
        """
        Check if a session can be resumed.

        Args:
            session_id: Session identifier

        Returns:
            True if session can be resumed
        """
        checkpoint = self.get_latest_checkpoint(session_id)

        if not checkpoint:
            return False

        # Can resume if last checkpoint was in_progress
        can_resume = checkpoint.status == "in_progress"

        logger.debug(
            "Resume check",
            session_id=session_id,
            can_resume=can_resume,
            status=checkpoint.status if checkpoint else None,
        )

        return can_resume

    def find_resumable_session(self, input_hash: str) -> Checkpoint | None:
        """
        Find a resumable session for the given input hash.

        Args:
            input_hash: Hash of the input file content

        Returns:
            Latest checkpoint for a resumable session, or None
        """
        if not input_hash:
            return None

        cursor = self.conn.execute(
            """
            SELECT * FROM checkpoints
            WHERE input_hash = ? AND status = 'in_progress'
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (input_hash,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        checkpoint = self._row_to_checkpoint(row)
        logger.debug(
            "Found resumable session",
            session_id=checkpoint.session_id,
            batch=checkpoint.batch_id,
            input_hash=input_hash,
        )
        return checkpoint

    def mark_session_completed(self, session_id: str) -> None:
        """
        Mark a session as completed.

        Also cleans up the created_resources table since they're no longer needed
        for resume (the session completed successfully).

        Args:
            session_id: Session identifier
        """
        checkpoint = self.get_latest_checkpoint(session_id)

        if checkpoint:
            self.save_checkpoint(
                session_id=session_id,
                batch_id=checkpoint.batch_id,
                operation_index=checkpoint.operation_index,
                completed_operations=checkpoint.completed_operations,
                total_operations=checkpoint.total_operations,
                status="completed",
            )

            # Clean up created resources - no longer needed for completed sessions
            self.clear_created_resources(session_id)

            logger.info("Session marked as completed", session_id=session_id)

    def mark_session_failed(self, session_id: str, error: str) -> None:
        """
        Mark a session as failed.

        Args:
            session_id: Session identifier
            error: Error message
        """
        checkpoint = self.get_latest_checkpoint(session_id)

        if checkpoint:
            self.save_checkpoint(
                session_id=session_id,
                batch_id=checkpoint.batch_id,
                operation_index=checkpoint.operation_index,
                completed_operations=checkpoint.completed_operations,
                total_operations=checkpoint.total_operations,
                status="failed",
                metadata={"error": error},
            )

            logger.error("Session marked as failed", session_id=session_id, error=error)

    def get_session_checkpoints(self, session_id: str) -> list[Checkpoint]:
        """
        Get all checkpoints for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of checkpoints
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM checkpoints
            WHERE session_id = ?
            ORDER BY timestamp ASC
            """,
            (session_id,),
        )

        checkpoints = [self._row_to_checkpoint(row) for row in cursor.fetchall()]

        logger.debug("Retrieved session checkpoints", session_id=session_id, count=len(checkpoints))

        return checkpoints

    def cleanup_old_checkpoints(self, retention_days: int = 30) -> int:
        """
        Clean up checkpoints older than specified days.

        Args:
            retention_days: Age threshold in days

        Returns:
            Number of deleted checkpoints
        """
        cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff.replace(day=cutoff.day - retention_days)
        cutoff_str = cutoff.isoformat()

        cursor = self.conn.execute(
            """
            DELETE FROM checkpoints
            WHERE timestamp < ?
              AND status IN ('completed', 'failed')
            """,
            (cutoff_str,),
        )

        self.conn.commit()
        deleted = cursor.rowcount

        logger.info("Cleaned up old checkpoints", deleted=deleted, retention_days=retention_days)

        return deleted

    def save_created_resource(
        self,
        session_id: str,
        resource_type: str,
        resource_key: str,
        bam_id: int,
    ) -> None:
        """
        Save a created resource for deferred resolution on resume.

        This persists the mapping from resource key (CIDR, zone name, etc.) to BAM ID
        so that when a session is resumed, operations with deferred dependencies on
        resources created in earlier (now skipped) batches can still be resolved.

        Args:
            session_id: Session identifier
            resource_type: Type of resource ('block', 'network', 'zone', 'location')
            resource_key: Resource key (CIDR for blocks/networks, name for zones/locations)
            bam_id: BAM ID of the created resource
        """
        self.conn.execute(
            """
            INSERT OR REPLACE INTO created_resources
            (session_id, resource_type, resource_key, bam_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                resource_type,
                resource_key,
                bam_id,
                datetime.utcnow().isoformat(),
            ),
        )
        self.conn.commit()

        logger.debug(
            "Saved created resource for resume",
            session_id=session_id,
            resource_type=resource_type,
            resource_key=resource_key,
            bam_id=bam_id,
        )

    def load_created_resources(self, session_id: str) -> dict[str, dict[str, int]]:
        """
        Load all created resources for a session.

        Returns a nested dictionary structure compatible with OperationExecutor's
        created_* maps:
        {
            'block': {'10.0.0.0/8': 123, ...},
            'network': {'10.1.0.0/24': 456, ...},
            'zone': {'example.com': 789, ...},
            'location': {'NYC': 101, ...},
        }

        Args:
            session_id: Session identifier

        Returns:
            Dictionary mapping resource_type -> {resource_key -> bam_id}
        """
        cursor = self.conn.execute(
            """
            SELECT resource_type, resource_key, bam_id
            FROM created_resources
            WHERE session_id = ?
            """,
            (session_id,),
        )

        result: dict[str, dict[str, int]] = {
            "block": {},
            "network": {},
            "zone": {},
            "location": {},
        }

        for row in cursor.fetchall():
            resource_type = row["resource_type"]
            if resource_type in result:
                result[resource_type][row["resource_key"]] = row["bam_id"]

        total_count = sum(len(v) for v in result.values())
        if total_count > 0:
            logger.info(
                "Loaded created resources for resume",
                session_id=session_id,
                blocks=len(result["block"]),
                networks=len(result["network"]),
                zones=len(result["zone"]),
                locations=len(result["location"]),
            )

        return result

    def clear_created_resources(self, session_id: str) -> int:
        """
        Clear all created resources for a session.

        Called when a session completes successfully or is abandoned.

        Args:
            session_id: Session identifier

        Returns:
            Number of records deleted
        """
        cursor = self.conn.execute(
            """
            DELETE FROM created_resources
            WHERE session_id = ?
            """,
            (session_id,),
        )
        self.conn.commit()
        deleted = cursor.rowcount

        if deleted > 0:
            logger.debug(
                "Cleared created resources",
                session_id=session_id,
                deleted=deleted,
            )

        return deleted

    def _row_to_checkpoint(self, row: sqlite3.Row) -> Checkpoint:
        """
        Convert SQLite row to Checkpoint.

        Args:
            row: SQLite row object.

        Returns:
            Checkpoint object.
        """
        return Checkpoint(
            id=row["id"],
            session_id=row["session_id"],
            timestamp=row["timestamp"],
            batch_id=row["batch_id"],
            operation_index=row["operation_index"],
            completed_operations=row["completed_operations"],
            total_operations=row["total_operations"],
            status=row["status"],
            input_hash=row["input_hash"] if "input_hash" in row.keys() else None,
            metadata=row["metadata"],
        )

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("CheckpointManager closed")

    def __enter__(self) -> "CheckpointManager":
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
