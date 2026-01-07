"""Unit tests for Changelog persistence."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from src.importer.models.csv_row import IP4AddressRow
from src.importer.models.operations import Operation, OperationType
from src.importer.models.results import OperationResult
from src.importer.persistence.changelog import ChangeLog


class TestChangeLog:
    """Test ChangeLog class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Set up test fixtures."""
        self.temp_dir = tmp_path
        self.db_path = self.temp_dir / "test_changelog.db"
        self.changelog = ChangeLog(str(self.db_path))

        yield

        self.changelog.close()

    def test_init(self):
        """Test initialization creates database table."""
        # Verify database file exists
        assert self.db_path.exists()

        # Verify schema
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='changelog'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_record_operation_create(self):
        """Test recording a CREATE operation."""
        session_id = "test_session_1"
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"address": "10.1.0.1"},
            csv_row=csv_row,
        )
        result = OperationResult(
            row_id=1,
            operation=OperationType.CREATE,
            success=True,
            resource_id=101,
        )
        after_state = {"address": "10.1.0.1", "id": 101}

        entry_id = self.changelog.record_operation(
            session_id=session_id,
            row_id=operation.row_id,
            object_type=operation.object_type,
            operation_type=result.operation,
            success=result.success,
            resource_id=result.resource_id,
            before_state=None,
            after_state=after_state,
        )

        assert entry_id > 0

        # Verify entry in DB
        entries = self.changelog.get_session_entries(session_id)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.id == entry_id
        assert entry.session_id == session_id
        assert entry.operation_type == "create"
        assert entry.resource_id == 101
        assert entry.before_state is None
        assert json.loads(entry.after_state) == after_state
        assert entry.success is True

    def test_record_operation_update(self):
        """Test recording an UPDATE operation."""
        session_id = "test_session_1"
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="update",
            config="Default",
            address="10.1.0.1",
            name="new_name",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="ip4_address",
            resource_id=101,
            payload={"name": "new_name"},
            csv_row=csv_row,
        )
        result = OperationResult(
            row_id=1,
            operation=OperationType.UPDATE,
            success=True,
            resource_id=101,
        )
        before_state = {"address": "10.1.0.1", "name": "old_name", "id": 101}
        after_state = {"address": "10.1.0.1", "name": "new_name", "id": 101}

        self.changelog.record_operation(
            session_id=session_id,
            row_id=operation.row_id,
            object_type=operation.object_type,
            operation_type=result.operation,
            success=result.success,
            resource_id=result.resource_id,
            before_state=before_state,
            after_state=after_state,
        )

        entries = self.changelog.get_session_entries(session_id)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.operation_type == "update"
        assert json.loads(entry.before_state) == before_state
        assert json.loads(entry.after_state) == after_state

    def test_record_operation_failed(self):
        """Test recording a failed operation."""
        session_id = "test_session_failed"
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"address": "10.1.0.1"},
            csv_row=csv_row,
        )
        result = OperationResult(
            row_id=1,
            operation=OperationType.CREATE,
            success=False,
            resource_id=None,
            error_message="API Error",
        )

        self.changelog.record_operation(
            session_id=session_id,
            row_id=operation.row_id,
            object_type=operation.object_type,
            operation_type=result.operation,
            success=result.success,
            resource_id=result.resource_id,
            error_message=result.error_message,
        )

        entries = self.changelog.get_session_entries(session_id)
        assert len(entries) == 1
        entry = entries[0]
        assert entry.success is False
        assert entry.error_message == "API Error"
        assert entry.resource_id is None

    def test_get_session_entries_multiple_operations(self):
        """Test retrieving multiple entries for a session."""
        session_id = "multi_op_session"
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        op1 = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        res1 = OperationResult(
            row_id=1, operation=OperationType.CREATE, success=True, resource_id=101
        )

        op2 = Operation(
            row_id=2,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        res2 = OperationResult(
            row_id=2, operation=OperationType.CREATE, success=True, resource_id=102
        )

        self.changelog.record_operation(
            session_id=session_id,
            row_id=op1.row_id,
            object_type=op1.object_type,
            operation_type=res1.operation,
            success=res1.success,
            resource_id=res1.resource_id,
        )
        self.changelog.record_operation(
            session_id=session_id,
            row_id=op2.row_id,
            object_type=op2.object_type,
            operation_type=res2.operation,
            success=res2.success,
            resource_id=res2.resource_id,
        )

        entries = self.changelog.get_session_entries(session_id)
        assert len(entries) == 2
        assert entries[0].row_id == "1"
        assert entries[1].row_id == "2"

    def test_get_sessions(self):
        """Test retrieving session summaries."""
        session1 = "session_A"
        session2 = "session_B"
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )

        # Session 1: 1 success
        op = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        res = OperationResult(row_id=1, operation=OperationType.CREATE, success=True, resource_id=1)
        self.changelog.record_operation(
            session_id=session1,
            row_id=op.row_id,
            object_type=op.object_type,
            operation_type=res.operation,
            success=res.success,
            resource_id=res.resource_id,
        )

        # Session 2: 1 success, 1 failure
        self.changelog.record_operation(
            session_id=session2,
            row_id=op.row_id,
            object_type=op.object_type,
            operation_type=res.operation,
            success=res.success,
            resource_id=res.resource_id,
        )
        res_fail = OperationResult(
            row_id=1, operation=OperationType.CREATE, success=False, resource_id=None
        )
        self.changelog.record_operation(
            session_id=session2,
            row_id=op.row_id,
            object_type=op.object_type,
            operation_type=res_fail.operation,
            success=res_fail.success,
            resource_id=res_fail.resource_id,
        )

        sessions = self.changelog.get_sessions()
        assert len(sessions) == 2

        # Order is by start_time desc (session2 was later)
        s2 = sessions[0]
        assert s2["session_id"] == session2
        assert s2["total_operations"] == 2
        assert s2["successful"] == 1
        assert s2["failed"] == 1

        s1 = sessions[1]
        assert s1["session_id"] == session1
        assert s1["total_operations"] == 1
        assert s1["successful"] == 1
        assert s1["failed"] == 0

    def test_get_sessions_limit(self):
        """Test limit on get_sessions."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        op = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        res = OperationResult(row_id=1, operation=OperationType.CREATE, success=True, resource_id=1)

        for i in range(5):
            self.changelog.record_operation(
                session_id=f"session_{i}",
                row_id=op.row_id,
                object_type=op.object_type,
                operation_type=res.operation,
                success=res.success,
                resource_id=res.resource_id,
            )

        sessions = self.changelog.get_sessions(limit=3)
        assert len(sessions) == 3

    def test_context_manager(self):
        """Test context manager support."""
        db_path = str(self.temp_dir / "context_test.db")
        with ChangeLog(db_path) as cl:
            assert cl.conn is not None
        # Should be closed after exit (though conn attribute might still exist, it should be closed)
        # We can't easily check if closed on the object without accessing private state or trying to use it.
        # But we can verify no exception raised.

    def test_close(self):
        """Test closing database connection."""
        assert self.changelog.conn is not None

        self.changelog.close()

        # In SQLite, closing doesn't set conn to None automatically in the object unless we do it.
        # But we can check if we can execute queries.
        with pytest.raises(sqlite3.ProgrammingError):
            self.changelog.conn.execute("SELECT 1")

    @patch("src.importer.persistence.changelog.datetime")
    def test_timestamp_generation(self, mock_datetime):
        """Test that timestamps are generated correctly."""
        fixed_time = MagicMock()
        fixed_time.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"
        mock_datetime.datetime = fixed_time
        # Fix: datetime.utcnow needs to be callable directly if imported as datetime
        # Actually we mocked the module, so mock_datetime.utcnow is what we need.
        mock_datetime.utcnow.return_value.isoformat.return_value = "2023-01-01T12:00:00"

        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        result = OperationResult(
            row_id=1, operation=OperationType.CREATE, success=True, resource_id=1
        )

        self.changelog.record_operation(
            session_id="sess1",
            row_id=operation.row_id,
            object_type=operation.object_type,
            operation_type=result.operation,
            success=result.success,
            resource_id=result.resource_id,
        )
        entries = self.changelog.get_session_entries("sess1")
        assert entries[0].timestamp == "2023-01-01T12:00:00"

    def test_json_serialization_handling(self):
        """Test JSON serialization of complex data structures."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        result = OperationResult(
            row_id=1, operation=OperationType.CREATE, success=True, resource_id=1
        )

        # Test with nested dicts and lists
        before_state = {"config": {"id": 1, "tags": ["a", "b"]}}

        self.changelog.record_operation(
            session_id="sess1",
            row_id=operation.row_id,
            object_type=operation.object_type,
            operation_type=result.operation,
            success=result.success,
            resource_id=result.resource_id,
            before_state=before_state,
        )

        entries = self.changelog.get_session_entries("sess1")
        loaded_state = json.loads(entries[0].before_state)
        assert loaded_state == before_state
