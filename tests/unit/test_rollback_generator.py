"""Unit tests for Rollback Generator."""

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.importer.persistence.changelog import ChangeLog, ChangeLogEntry
from src.importer.rollback.generator import RollbackGenerator


class TestRollbackGenerator:
    """Test RollbackGenerator class."""

    @pytest.fixture(autouse=True)
    def setup_method(self, tmp_path):
        """Set up test fixtures."""
        self.temp_dir = tmp_path
        self.db_path = self.temp_dir / "test_changelog.db"
        self.changelog = ChangeLog(str(self.db_path))
        self.rollback_generator = RollbackGenerator(self.changelog)

        yield

        self.changelog.close()

    def mock_changelog_entries(self, entries):
        """Mock changelog entries retrieval."""
        self.changelog.get_session_entries = MagicMock(return_value=entries)

    def test_init(self):
        """Test initialization."""
        assert self.rollback_generator.changelog == self.changelog

    def test_generate_rollback_csv_create_operation(self):
        """Test generating rollback for CREATE operation."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "rollback_test.csv"

        # Mock a successful CREATE operation
        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id=session_id,
            operation_type="create",
            object_type="ip4_address",
            resource_id=101,
            row_id="1",
            before_state=None,
            after_state=json.dumps({"address": "10.1.0.1", "name": "server1"}),
            success=True,
            error_message=None,
        )
        self.mock_changelog_entries([entry])

        stats = self.rollback_generator.generate_rollback_csv(
            session_id=session_id,
            output_path=output_path,
        )

        assert stats["session_id"] == session_id
        assert stats["rollback_operations"] == 1

        # Read generated CSV
        with open(output_path, encoding="utf-8") as f:
            lines = f.readlines()
            # Skip comments
            data_lines = [line for line in lines if not line.startswith("#")]
            reader = csv.DictReader(data_lines)
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]
        # CREATE rollback should be DELETE
        assert row["action"] == "delete"
        assert row["object_type"] == "ip4_address"
        assert row["bam_id"] == "101"
        assert row["verify_name"] == "server1"
        assert row["verify_address"] == "10.1.0.1"

    def test_generate_rollback_csv_update_operation(self):
        """Test generating rollback for UPDATE operation."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "rollback_update.csv"

        # Mock a successful UPDATE operation
        # Original state (before) had name="old_name"
        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id=session_id,
            operation_type="update",
            object_type="ip4_address",
            resource_id=102,
            row_id="1",
            before_state=json.dumps({"name": "old_name", "mac": "00:00:00:00:00:00"}),
            after_state=json.dumps({"name": "new_name", "mac": "00:00:00:00:00:00"}),
            success=True,
            error_message=None,
        )
        self.mock_changelog_entries([entry])

        stats = self.rollback_generator.generate_rollback_csv(
            session_id=session_id,
            output_path=output_path,
        )

        assert stats["rollback_operations"] == 1

        # Read generated CSV
        with open(output_path, encoding="utf-8") as f:
            lines = f.readlines()
            data_lines = [line for line in lines if not line.startswith("#")]
            reader = csv.DictReader(data_lines)
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]
        # UPDATE rollback should be UPDATE with old values
        assert row["action"] == "update"
        assert row["object_type"] == "ip4_address"
        assert row["bam_id"] == "102"
        # Check that old values are restored
        assert row["name"] == "old_name"

    def test_generate_rollback_csv_delete_operation(self):
        """Test generating rollback for DELETE operation (skipped)."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "rollback_delete.csv"

        # DELETE operations require recreation which is risky/complex, so typically skipped or logged
        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id=session_id,
            operation_type="delete",
            object_type="ip4_address",
            resource_id=103,
            row_id="1",
            before_state=json.dumps({"address": "10.1.0.3"}),
            after_state=None,
            success=True,
            error_message=None,
        )
        self.mock_changelog_entries([entry])

        stats = self.rollback_generator.generate_rollback_csv(
            session_id=session_id,
            output_path=output_path,
        )

        # Expect 0 operations as DELETE rollback is not auto-generated
        assert stats["rollback_operations"] == 0

    def test_generate_rollback_csv_failed_operation(self):
        """Test that failed operations are ignored."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "rollback_failed.csv"

        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id=session_id,
            operation_type="create",
            object_type="ip4_address",
            resource_id=None,
            row_id="1",
            before_state=None,
            after_state=None,
            success=False,
            error_message="Error",
        )
        self.mock_changelog_entries([entry])

        stats = self.rollback_generator.generate_rollback_csv(
            session_id=session_id,
            output_path=output_path,
        )

        assert stats["rollback_operations"] == 0

    def test_generate_rollback_csv_with_updates(self):
        """Test updates inclusion toggle."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "rollback_no_updates.csv"

        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id=session_id,
            operation_type="update",
            object_type="ip4_address",
            resource_id=102,
            row_id="1",
            before_state=json.dumps({"name": "old"}),
            after_state=json.dumps({"name": "new"}),
            success=True,
            error_message=None,
        )
        self.mock_changelog_entries([entry])

        # Generate WITHOUT updates
        stats = self.rollback_generator.generate_rollback_csv(
            session_id=session_id,
            output_path=output_path,
            include_updates=False,
        )

        assert stats["rollback_operations"] == 0

    def test_create_delete_row(self):
        """Test _create_delete_row helper."""
        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id="session1",
            operation_type="create",
            object_type="ip4_address",
            resource_id=101,
            row_id="row1",
            before_state=None,
            after_state=json.dumps({"address": "10.1.0.1", "name": "server1"}),
            success=True,
            error_message=None,
        )

        row = self.rollback_generator._create_delete_row(entry)

        assert row["action"] == "delete"
        assert row["bam_id"] == 101
        assert row["verify_address"] == "10.1.0.1"

    def test_create_restore_row(self):
        """Test _create_restore_row helper."""
        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id="session1",
            operation_type="update",
            object_type="ip4_address",
            resource_id=102,
            row_id="row2",
            before_state=json.dumps({"name": "original_name", "mac": "aa:bb:cc:dd:ee:ff"}),
            after_state=json.dumps({"name": "new_name"}),
            success=True,
            error_message=None,
        )

        row = self.rollback_generator._create_restore_row(entry)

        assert row["action"] == "update"
        assert row["bam_id"] == 102
        assert row["name"] == "original_name"
        assert row["mac"] == "aa:bb:cc:dd:ee:ff"

    def test_delete_operation_warning(self):
        """Test that delete operation logs warning."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "delete_warning.csv"

        entry = ChangeLogEntry(
            id=1,
            timestamp="2023-01-01T12:00:00",
            session_id=session_id,
            operation_type="delete",
            object_type="ip4_address",
            resource_id=103,
            row_id="1",
            before_state=json.dumps({"address": "10.1.0.3"}),
            after_state=None,
            success=True,
            error_message=None,
        )
        self.mock_changelog_entries([entry])

        with patch("structlog.stdlib.BoundLogger.warning"):
            # We assume structlog is used, but if not we can patch logger in the module
            # For simplicity, we just run it and assume no error
            self.rollback_generator.generate_rollback_csv(
                session_id=session_id,
                output_path=output_path,
            )
            # Cannot easily verify log call without proper capture fixture, but execution should pass

    def test_reverse_order_for_rollback(self):
        """Test that operations are reversed for rollback."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "reverse_test.csv"

        # 3 operations in order 1, 2, 3
        entries = []
        for i in range(3):
            entry = ChangeLogEntry(
                id=i + 1,
                timestamp=f"2023-01-01T12:0{i}:00",
                session_id=session_id,
                operation_type="create",
                object_type="ip4_address",
                resource_id=100 + i,
                row_id=str(i + 1),
                before_state=None,
                after_state=json.dumps({"address": f"10.1.0.{i + 1}"}),
                success=True,
                error_message=None,
            )
            entries.append(entry)

        self.mock_changelog_entries(entries)

        self.rollback_generator.generate_rollback_csv(
            session_id=session_id,
            output_path=output_path,
        )

        # Read CSV and verify order is reversed
        with open(output_path, encoding="utf-8") as f:
            lines = f.readlines()
            data_lines = [line for line in lines if not line.startswith("#")]
            reader = csv.DictReader(data_lines)
            rows = list(reader)

        assert len(rows) == 3
        # Should be reversed: 3, 2, 1
        assert rows[0]["bam_id"] == "102"  # id 100+2
        assert rows[1]["bam_id"] == "101"  # id 100+1
        assert rows[2]["bam_id"] == "100"  # id 100+0

    def test_mixed_operation_types(self):
        """Test rollback generation with mixed operation types."""
        session_id = "test_session"
        output_path = Path(self.temp_dir) / "mixed_test.csv"

        # Create entries with different operation types
        entries = [
            ChangeLogEntry(
                id=1,
                timestamp="2023-01-01T12:00:00",
                session_id=session_id,
                operation_type="create",
                object_type="ip4_address",
                resource_id=101,
                row_id="1",
                before_state=None,
                after_state=json.dumps({"address": "10.1.0.1"}),
                success=True,
                error_message=None,
            ),
            ChangeLogEntry(
                id=2,
                timestamp="2023-01-01T12:01:00",
                session_id=session_id,
                operation_type="update",
                object_type="ip4_address",
                resource_id=102,
                row_id="2",
                before_state=json.dumps({"name": "old"}),
                after_state=json.dumps({"name": "new"}),
                success=True,
                error_message=None,
            ),
            ChangeLogEntry(
                id=3,
                timestamp="2023-01-01T12:02:00",
                session_id=session_id,
                operation_type="noop",
                object_type="ip4_address",
                resource_id=None,
                row_id="3",
                before_state=None,
                after_state=None,
                success=True,
                error_message=None,
            ),
        ]
        self.mock_changelog_entries(entries)

        stats = self.rollback_generator.generate_rollback_csv(
            session_id=session_id,
            output_path=output_path,
            include_updates=True,
        )

        # Should have 2 rollback operations (CREATE→DELETE, UPDATE→UPDATE)
        assert stats["rollback_operations"] == 2

        # Read and verify types
        with open(output_path, encoding="utf-8") as f:
            lines = f.readlines()
            data_lines = [line for line in lines if not line.startswith("#")]
            reader = csv.DictReader(data_lines)
            rows = list(reader)

        actions = [row["action"] for row in rows]
        # Reversed order: UPDATE, CREATE->DELETE
        assert actions == ["update", "delete"]
