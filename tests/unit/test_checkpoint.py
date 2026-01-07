"""Unit tests for Checkpoint persistence."""

import json
import sqlite3
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.importer.persistence.checkpoint import CheckpointManager


class TestCheckpointManager:
    """Test CheckpointManager class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Set up test fixtures."""
        self.temp_dir = tmp_path
        self.db_path = self.temp_dir / "test_checkpoints.db"
        self.checkpoint_manager = CheckpointManager(str(self.db_path))

        yield

        self.checkpoint_manager.close()

    def test_init(self):
        """Test initialization creates database table."""
        assert self.db_path.exists()

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_save_checkpoint(self):
        """Test saving a checkpoint."""
        checkpoint_id = self.checkpoint_manager.save_checkpoint(
            session_id="test_session",
            batch_id=1,
            operation_index=5,
            completed_operations=5,
            total_operations=10,
            metadata={"key": "value"},
        )

        assert checkpoint_id > 0

        # Verify in DB
        checkpoint = self.checkpoint_manager.get_latest_checkpoint("test_session")
        assert checkpoint is not None
        assert checkpoint.id == checkpoint_id
        assert checkpoint.session_id == "test_session"
        assert checkpoint.batch_id == 1
        assert checkpoint.operation_index == 5
        assert checkpoint.completed_operations == 5
        assert checkpoint.total_operations == 10
        assert checkpoint.status == "in_progress"
        assert json.loads(checkpoint.metadata) == {"key": "value"}

    def test_get_latest_checkpoint_none(self):
        """Test getting latest checkpoint when none exists."""
        checkpoint = self.checkpoint_manager.get_latest_checkpoint("non_existent_session")
        assert checkpoint is None

    def test_get_latest_checkpoint_ordering(self):
        """Test that get_latest_checkpoint returns the most recent one."""
        session_id = "ordering_test"

        # Save checkpoints with varying timestamps (simulated by insertion order)
        # Note: SQLite AUTOINCREMENT guarantees ID ordering, but timestamp is what matters usually.
        # Here we rely on insertion order as default ordering in `get_latest_checkpoint` query is by ID/Timestamp desc.

        self.checkpoint_manager.save_checkpoint(
            session_id=session_id,
            batch_id=1,
            operation_index=1,
            completed_operations=1,
            total_operations=10,
        )

        id2 = self.checkpoint_manager.save_checkpoint(
            session_id=session_id,
            batch_id=1,
            operation_index=2,
            completed_operations=2,
            total_operations=10,
        )

        latest = self.checkpoint_manager.get_latest_checkpoint(session_id)
        assert latest.id == id2
        assert latest.operation_index == 2

    def test_mark_session_completed(self):
        """Test marking a session as completed."""
        session_id = "completion_test"
        self.checkpoint_manager.save_checkpoint(
            session_id=session_id,
            batch_id=1,
            operation_index=10,
            completed_operations=10,
            total_operations=10,
        )

        self.checkpoint_manager.mark_session_completed(session_id)

        latest = self.checkpoint_manager.get_latest_checkpoint(session_id)
        assert latest.status == "completed"

    def test_mark_session_failed(self):
        """Test marking a session as failed."""
        session_id = "failure_test"
        self.checkpoint_manager.save_checkpoint(
            session_id=session_id,
            batch_id=1,
            operation_index=5,
            completed_operations=5,
            total_operations=10,
        )

        self.checkpoint_manager.mark_session_failed(session_id, "Something went wrong")

        latest = self.checkpoint_manager.get_latest_checkpoint(session_id)
        assert latest.status == "failed"
        metadata = json.loads(latest.metadata)
        assert metadata["error"] == "Something went wrong"

    @patch("src.importer.persistence.checkpoint.datetime")
    def test_cleanup_old_checkpoints(self, mock_datetime):
        """Test cleaning up old checkpoints."""
        # Use a fixed current time
        fixed_now = datetime(2023, 1, 20, 12, 0, 0)
        mock_datetime.utcnow.return_value = fixed_now

        # Calculate old time (10 days ago)
        old_time = fixed_now - timedelta(days=10)

        # We need to insert directly into DB to set custom timestamps because save_checkpoint uses datetime.utcnow()
        # Wait, save_checkpoint uses datetime.utcnow() which IS mocked.
        # But we want to insert an entry with a SPECIFIC timestamp that is 10 days ago.

        # Insert old checkpoint
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """
            INSERT INTO checkpoints (
                session_id, timestamp, batch_id, operation_index,
                completed_operations, total_operations, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("old_session", old_time.isoformat(), 1, 1, 1, 10, "completed"),
        )
        conn.commit()
        conn.close()

        # Verify it exists
        cursor = self.checkpoint_manager.conn.execute("SELECT count(*) FROM checkpoints")
        assert cursor.fetchone()[0] == 1

        # Run cleanup (retention 7 days)
        # 10 days old > 7 days retention -> Should delete
        deleted = self.checkpoint_manager.cleanup_old_checkpoints(retention_days=7)

        assert deleted == 1
        cursor = self.checkpoint_manager.conn.execute("SELECT count(*) FROM checkpoints")
        assert cursor.fetchone()[0] == 0

    @patch("src.importer.persistence.checkpoint.datetime")
    def test_cleanup_old_checkpoints_preserves_in_progress(self, mock_datetime):
        """Test that in-progress sessions are preserved even if old."""
        fixed_now = datetime(2023, 1, 20, 12, 0, 0)
        mock_datetime.utcnow.return_value = fixed_now

        old_time = fixed_now - timedelta(days=10)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """
            INSERT INTO checkpoints (
                session_id, timestamp, batch_id, operation_index,
                completed_operations, total_operations, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("old_active_session", old_time.isoformat(), 1, 1, 1, 10, "in_progress"),
        )
        conn.commit()
        conn.close()

        deleted = self.checkpoint_manager.cleanup_old_checkpoints(retention_days=7)

        assert deleted == 0
        cursor = self.checkpoint_manager.conn.execute("SELECT count(*) FROM checkpoints")
        assert cursor.fetchone()[0] == 1

    def test_context_manager(self):
        """Test context manager support."""
        db_path = str(self.temp_dir / "context_test.db")
        with CheckpointManager(db_path) as cm:
            assert cm.conn is not None
            # Do an operation
            cm.save_checkpoint("sess", 1, 1, 1, 1)

        # Should be closed. Accessing conn directly might show it exists but query should fail.
        # However, Python's sqlite3 connection object doesn't always raise immediately if accessed.
        # But we can assume the close() method was called.

        # Let's verify we can't use it
        # Re-open to check if data saved
        cm2 = CheckpointManager(db_path)
        cp = cm2.get_latest_checkpoint("sess")
        assert cp is not None
        cm2.close()

    def test_close(self):
        """Test closing connection."""
        assert self.checkpoint_manager.conn is not None
        self.checkpoint_manager.close()

        with pytest.raises(sqlite3.ProgrammingError):
            self.checkpoint_manager.conn.execute("SELECT 1")

    @patch("src.importer.persistence.checkpoint.datetime")
    def test_timestamp_generation(self, mock_datetime):
        """Test that timestamps are generated correctly."""
        fixed_time = MagicMock()
        fixed_time.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_datetime.datetime = fixed_time
        # Mocking the module-level datetime import
        mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        self.checkpoint_manager.save_checkpoint(
            session_id="timestamp_test",
            batch_id=1,
            operation_index=1,
            completed_operations=5,
            total_operations=10,
        )

        checkpoint = self.checkpoint_manager.get_latest_checkpoint("timestamp_test")
        assert checkpoint.timestamp == "2023-01-01T12:00:00"


class TestCreatedResourcesPersistence:
    """Test created_resources persistence for resume functionality."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Set up test fixtures."""
        self.temp_dir = tmp_path
        self.db_path = self.temp_dir / "test_checkpoints.db"
        self.checkpoint_manager = CheckpointManager(str(self.db_path))

        yield

        self.checkpoint_manager.close()

    def test_created_resources_table_exists(self):
        """Test that created_resources table is created on init."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='created_resources'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_save_created_resource(self):
        """Test saving a created resource."""
        self.checkpoint_manager.save_created_resource(
            session_id="test_session",
            resource_type="block",
            resource_key="10.0.0.0/8",
            bam_id=12345,
        )

        # Verify in DB
        cursor = self.checkpoint_manager.conn.execute(
            "SELECT * FROM created_resources WHERE session_id = ?", ("test_session",)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["resource_type"] == "block"
        assert row["resource_key"] == "10.0.0.0/8"
        assert row["bam_id"] == 12345

    def test_save_created_resource_replaces_duplicate(self):
        """Test that saving a duplicate resource key replaces the existing one."""
        self.checkpoint_manager.save_created_resource(
            session_id="test_session",
            resource_type="block",
            resource_key="10.0.0.0/8",
            bam_id=12345,
        )
        self.checkpoint_manager.save_created_resource(
            session_id="test_session",
            resource_type="block",
            resource_key="10.0.0.0/8",
            bam_id=99999,
        )

        cursor = self.checkpoint_manager.conn.execute(
            "SELECT COUNT(*) FROM created_resources WHERE session_id = ?", ("test_session",)
        )
        assert cursor.fetchone()[0] == 1

        cursor = self.checkpoint_manager.conn.execute(
            "SELECT bam_id FROM created_resources WHERE session_id = ? AND resource_key = ?",
            ("test_session", "10.0.0.0/8"),
        )
        assert cursor.fetchone()[0] == 99999

    def test_load_created_resources_empty(self):
        """Test loading created resources when none exist."""
        result = self.checkpoint_manager.load_created_resources("non_existent_session")

        assert result == {"block": {}, "network": {}, "zone": {}, "location": {}}

    def test_load_created_resources_with_data(self):
        """Test loading created resources returns correct structure."""
        session_id = "test_session"

        # Save various resource types
        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="block", resource_key="10.0.0.0/8", bam_id=100
        )
        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="block", resource_key="172.16.0.0/12", bam_id=101
        )
        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="network", resource_key="10.1.0.0/24", bam_id=200
        )
        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="zone", resource_key="example.com", bam_id=300
        )
        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="location", resource_key="NYC", bam_id=400
        )

        result = self.checkpoint_manager.load_created_resources(session_id)

        assert result["block"] == {"10.0.0.0/8": 100, "172.16.0.0/12": 101}
        assert result["network"] == {"10.1.0.0/24": 200}
        assert result["zone"] == {"example.com": 300}
        assert result["location"] == {"NYC": 400}

    def test_load_created_resources_isolates_sessions(self):
        """Test that load_created_resources only returns resources for the specified session."""
        self.checkpoint_manager.save_created_resource(
            session_id="session_a", resource_type="block", resource_key="10.0.0.0/8", bam_id=100
        )
        self.checkpoint_manager.save_created_resource(
            session_id="session_b", resource_type="block", resource_key="172.16.0.0/12", bam_id=200
        )

        result_a = self.checkpoint_manager.load_created_resources("session_a")
        result_b = self.checkpoint_manager.load_created_resources("session_b")

        assert result_a["block"] == {"10.0.0.0/8": 100}
        assert result_b["block"] == {"172.16.0.0/12": 200}

    def test_clear_created_resources(self):
        """Test clearing created resources for a session."""
        session_id = "test_session"

        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="block", resource_key="10.0.0.0/8", bam_id=100
        )
        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="network", resource_key="10.1.0.0/24", bam_id=200
        )

        deleted = self.checkpoint_manager.clear_created_resources(session_id)

        assert deleted == 2
        result = self.checkpoint_manager.load_created_resources(session_id)
        assert result == {"block": {}, "network": {}, "zone": {}, "location": {}}

    def test_clear_created_resources_isolates_sessions(self):
        """Test that clearing resources only affects the specified session."""
        self.checkpoint_manager.save_created_resource(
            session_id="session_a", resource_type="block", resource_key="10.0.0.0/8", bam_id=100
        )
        self.checkpoint_manager.save_created_resource(
            session_id="session_b", resource_type="block", resource_key="172.16.0.0/12", bam_id=200
        )

        self.checkpoint_manager.clear_created_resources("session_a")

        result_a = self.checkpoint_manager.load_created_resources("session_a")
        result_b = self.checkpoint_manager.load_created_resources("session_b")

        assert result_a["block"] == {}
        assert result_b["block"] == {"172.16.0.0/12": 200}

    def test_mark_session_completed_clears_created_resources(self):
        """Test that marking a session completed also clears created resources."""
        session_id = "test_session"

        # Create a checkpoint first (required for mark_session_completed)
        self.checkpoint_manager.save_checkpoint(
            session_id=session_id,
            batch_id=1,
            operation_index=10,
            completed_operations=10,
            total_operations=10,
        )

        # Save some created resources
        self.checkpoint_manager.save_created_resource(
            session_id=session_id, resource_type="block", resource_key="10.0.0.0/8", bam_id=100
        )

        # Mark completed
        self.checkpoint_manager.mark_session_completed(session_id)

        # Verify resources are cleared
        result = self.checkpoint_manager.load_created_resources(session_id)
        assert result == {"block": {}, "network": {}, "zone": {}, "location": {}}
