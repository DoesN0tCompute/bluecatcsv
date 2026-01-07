"""Unit tests for Reporter."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.importer.models.operations import OperationType
from src.importer.models.results import OperationResult
from src.importer.observability.reporter import ImportReport, ReportGenerator


class TestReporter:
    """Test Reporter class."""

    @pytest.fixture
    def reporter(self):
        """Create a reporter instance."""
        return ReportGenerator()

    @pytest.fixture
    def sample_results(self):
        """Create sample operation results."""
        op1 = OperationResult(
            row_id="1",
            operation=OperationType.CREATE,
            success=True,
            resource_id=101,
            duration_ms=100.0,
        )
        op2 = OperationResult(
            row_id="2",
            operation=OperationType.UPDATE,
            success=False,
            error_message="Update failed",
            duration_ms=50.0,
        )
        return [op1, op2]

    def test_init(self):
        """Test initialization."""
        reporter = ReportGenerator()
        assert reporter.changelog is None

    def test_generate_report(self, reporter, sample_results):
        """Test generating report object."""
        start_time = datetime(2023, 1, 1, 12, 0, 0)
        end_time = datetime(2023, 1, 1, 12, 0, 5)

        report = reporter.generate_report(
            session_id="test_session",
            results=sample_results,
            start_time=start_time,
            end_time=end_time,
            csv_file=Path("test.csv"),
            dry_run=False,
            metrics={"initial_concurrency": 5},
        )

        assert isinstance(report, ImportReport)
        assert report.session_id == "test_session"
        assert report.total_operations == 2
        assert report.successful_operations == 1
        assert report.failed_operations == 1
        assert report.creates == 1
        assert report.updates == 1
        assert report.avg_operation_duration_ms == 75.0
        # If any failed, status is partial (if some succeeded)
        assert report.status == "partial"
        assert len(report.errors) == 1
        assert report.errors[0]["row_id"] == "2"

    def test_write_json_report(self, reporter, tmp_path):
        """Test writing JSON report."""
        report = ImportReport(
            session_id="test",
            start_time="2023-01-01T12:00:00",
            end_time="2023-01-01T12:00:05",
            duration_seconds=5.0,
            status="completed",
            total_operations=10,
            successful_operations=10,
            failed_operations=0,
            skipped_operations=0,
            creates=5,
            updates=5,
            deletes=0,
            noops=0,
            avg_operation_duration_ms=100.0,
            max_operation_duration_ms=200.0,
            operations_per_second=2.0,
            initial_concurrency=1,
            final_concurrency=1,
            rate_limit_hits=0,
            errors=[],
            csv_file="test.csv",
            dry_run=False,
            rollback_csv_generated=False,
            rollback_csv_path=None,
        )

        output_path = tmp_path / "report.json"
        reporter.write_json_report(report, output_path)

        assert output_path.exists()
        import json

        with open(output_path) as f:
            data = json.load(f)
        assert data["session_id"] == "test"
        assert data["status"] == "completed"

    def test_write_html_report(self, reporter, tmp_path):
        """Test writing HTML report."""
        report = ImportReport(
            session_id="test_html",
            start_time="2023-01-01T12:00:00",
            end_time="2023-01-01T12:00:05",
            duration_seconds=5.0,
            status="failed",
            total_operations=2,
            successful_operations=1,
            failed_operations=1,
            skipped_operations=0,
            creates=1,
            updates=1,
            deletes=0,
            noops=0,
            avg_operation_duration_ms=100.0,
            max_operation_duration_ms=100.0,
            operations_per_second=0.4,
            initial_concurrency=1,
            final_concurrency=1,
            rate_limit_hits=0,
            errors=[{"row_id": "2", "operation_type": "update", "error": "Failed"}],
            csv_file="test.csv",
            dry_run=False,
            rollback_csv_generated=True,
            rollback_csv_path="/tmp/rollback.csv",
        )

        output_path = tmp_path / "report.html"
        reporter.write_html_report(report, output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "BlueCat Import Report" in content
        assert "test_html" in content
        assert "FAILED" in content
        assert "rollback.csv" in content

    def test_get_session_summary_no_changelog(self):
        """Test getting summary without changelog."""
        reporter = ReportGenerator()
        assert reporter.get_session_summary("session") is None

    def test_get_session_summary_with_changelog(self):
        """Test getting summary with changelog."""
        mock_changelog = MagicMock()
        entry1 = MagicMock(success=True, timestamp="2023-01-01T12:00:00")
        entry2 = MagicMock(success=False, timestamp="2023-01-01T12:00:05")
        mock_changelog.get_session_entries.return_value = [entry1, entry2]

        reporter = ReportGenerator(changelog=mock_changelog)
        summary = reporter.get_session_summary("session1")

        assert summary is not None
        assert summary["session_id"] == "session1"
        assert summary["total_operations"] == 2
        assert summary["successful"] == 1
        assert summary["failed"] == 1
        assert summary["start_time"] == "2023-01-01T12:00:00"
        assert summary["end_time"] == "2023-01-01T12:00:05"
