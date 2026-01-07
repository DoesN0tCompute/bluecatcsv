"""Advanced tests for report generation system.

This module tests the report generation comprehensively:
- ImportReport dataclass
- ReportGenerator functionality
- Report generation from execution data
- Summary statistics calculation
- Error collection and formatting
"""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from importer.observability.reporter import ImportReport, ReportGenerator


class TestImportReport:
    """Test ImportReport dataclass."""

    def test_import_report_initialization(self):
        """Test ImportReport can be initialized with required fields."""
        report = ImportReport(
            session_id="test-123",
            status="completed",
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T00:01:00",
            duration_seconds=60.0,
            csv_file="/path/to/file.csv",
            dry_run=False,
            total_operations=10,
            successful_operations=9,
            failed_operations=1,
            skipped_operations=0,
            operations_per_second=0.167,
            avg_operation_duration_ms=100.0,
            max_operation_duration_ms=200.0,
            initial_concurrency=5,
            final_concurrency=5,
            rate_limit_hits=0,
            rollback_csv_generated=True,
        )

        assert report.session_id == "test-123"
        assert report.status == "completed"
        assert report.total_operations == 10
        assert report.successful_operations == 9
        assert report.failed_operations == 1

    def test_import_report_default_values(self):
        """Test ImportReport default values for optional fields."""
        report = ImportReport(
            session_id="test-123",
            status="completed",
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T00:01:00",
            duration_seconds=60.0,
            csv_file="/path/to/file.csv",
            dry_run=False,
            total_operations=10,
            successful_operations=10,
            failed_operations=0,
            skipped_operations=0,
            operations_per_second=0.167,
            avg_operation_duration_ms=100.0,
            max_operation_duration_ms=200.0,
            initial_concurrency=5,
            final_concurrency=5,
            rate_limit_hits=0,
            rollback_csv_generated=False,
        )

        assert report.rollback_csv_path is None
        assert report.errors == []
        assert report.creates == 0
        assert report.updates == 0
        assert report.deletes == 0
        assert report.noops == 0

    def test_import_report_with_errors(self):
        """Test ImportReport with error details."""
        errors = [
            {"row_id": 1, "operation_type": "create", "error": "Network already exists"},
            {"row_id": 5, "operation_type": "update", "error": "Resource not found"},
        ]

        report = ImportReport(
            session_id="test-123",
            status="failed",
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T00:01:00",
            duration_seconds=60.0,
            csv_file="/path/to/file.csv",
            dry_run=False,
            total_operations=10,
            successful_operations=8,
            failed_operations=2,
            skipped_operations=0,
            operations_per_second=0.167,
            avg_operation_duration_ms=100.0,
            max_operation_duration_ms=200.0,
            initial_concurrency=5,
            final_concurrency=5,
            rate_limit_hits=0,
            rollback_csv_generated=False,
            errors=errors,
        )

        assert len(report.errors) == 2
        assert report.errors[0]["row_id"] == 1
        assert report.errors[1]["row_id"] == 5

    def test_import_report_with_operation_breakdown(self):
        """Test ImportReport with operation type breakdown."""
        report = ImportReport(
            session_id="test-123",
            status="completed",
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T00:01:00",
            duration_seconds=60.0,
            csv_file="/path/to/file.csv",
            dry_run=False,
            total_operations=10,
            successful_operations=10,
            failed_operations=0,
            skipped_operations=0,
            operations_per_second=0.167,
            avg_operation_duration_ms=100.0,
            max_operation_duration_ms=200.0,
            initial_concurrency=5,
            final_concurrency=5,
            rate_limit_hits=0,
            rollback_csv_generated=False,
            creates=5,
            updates=3,
            deletes=1,
            noops=1,
        )

        assert report.creates == 5
        assert report.updates == 3
        assert report.deletes == 1
        assert report.noops == 1

    def test_import_report_to_dict(self):
        """Test ImportReport can be converted to dictionary."""
        report = ImportReport(
            session_id="test-123",
            status="completed",
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T00:01:00",
            duration_seconds=60.0,
            csv_file="/path/to/file.csv",
            dry_run=False,
            total_operations=10,
            successful_operations=10,
            failed_operations=0,
            skipped_operations=0,
            operations_per_second=0.167,
            avg_operation_duration_ms=100.0,
            max_operation_duration_ms=200.0,
            initial_concurrency=5,
            final_concurrency=5,
            rate_limit_hits=0,
            rollback_csv_generated=True,
            rollback_csv_path="/path/to/rollback.csv",
        )

        report_dict = asdict(report)
        assert isinstance(report_dict, dict)
        assert report_dict["session_id"] == "test-123"
        assert report_dict["status"] == "completed"
        assert report_dict["rollback_csv_path"] == "/path/to/rollback.csv"


class TestReportGenerator:
    """Test ReportGenerator class."""

    def test_report_generator_initialization(self):
        """Test ReportGenerator can be initialized."""
        generator = ReportGenerator()
        assert generator.changelog is None

    def test_report_generator_with_changelog(self):
        """Test ReportGenerator with changelog."""
        mock_changelog = Mock()
        generator = ReportGenerator(changelog=mock_changelog)
        assert generator.changelog is mock_changelog

    def test_generate_report_basic(self):
        """Test basic report generation."""
        generator = ReportGenerator()

        # Mock operation results
        results = [
            Mock(
                success=True,
                operation="create",
                row_id=1,
                duration_ms=100.0,
                error_message=None,
            ),
            Mock(
                success=True,
                operation="update",
                row_id=2,
                duration_ms=150.0,
                error_message=None,
            ),
        ]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        assert report.session_id == "test-123"
        assert report.total_operations == 2
        assert report.successful_operations == 2
        assert report.failed_operations == 0
        assert report.creates == 1
        assert report.updates == 1
        assert report.deletes == 0

    def test_generate_report_calculates_duration(self):
        """Test report generation calculates duration correctly."""
        generator = ReportGenerator()

        results = [Mock(success=True, operation="create", row_id=1, duration_ms=100.0)]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 2, 30),  # 150 seconds
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        assert report.duration_seconds == 150.0

    def test_generate_report_calculates_operations_per_second(self):
        """Test report generation calculates ops/sec correctly."""
        generator = ReportGenerator()

        results = [
            Mock(success=True, operation="create", row_id=i, duration_ms=100.0)
            for i in range(10)
        ]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 0, 10),  # 10 seconds
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        assert report.operations_per_second == 1.0  # 10 ops / 10 seconds

    def test_generate_report_handles_zero_duration(self):
        """Test report generation handles zero duration (instant operations)."""
        generator = ReportGenerator()

        results = [Mock(success=True, operation="create", row_id=1, duration_ms=100.0)]

        # Same start and end time
        same_time = datetime(2024, 1, 1, 0, 0, 0)
        report = generator.generate_report(
            session_id="test-123",
            start_time=same_time,
            end_time=same_time,
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        # Should not divide by zero
        assert report.operations_per_second == 0

    def test_generate_report_calculates_latency_stats(self):
        """Test report generation calculates latency statistics."""
        generator = ReportGenerator()

        results = [
            Mock(success=True, operation="create", row_id=1, duration_ms=100.0),
            Mock(success=True, operation="create", row_id=2, duration_ms=200.0),
            Mock(success=True, operation="create", row_id=3, duration_ms=150.0),
        ]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        assert report.avg_operation_duration_ms == 150.0  # (100 + 200 + 150) / 3
        assert report.max_operation_duration_ms == 200.0

    def test_generate_report_handles_missing_duration(self):
        """Test report generation handles results without duration_ms."""
        generator = ReportGenerator()

        results = [
            Mock(success=True, operation="create", row_id=1, duration_ms=None),
            Mock(success=True, operation="create", row_id=2, duration_ms=100.0),
        ]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        # Should only use results with duration_ms
        assert report.avg_operation_duration_ms == 100.0
        assert report.max_operation_duration_ms == 100.0

    def test_generate_report_with_failures(self):
        """Test report generation with failed operations."""
        generator = ReportGenerator()

        results = [
            Mock(
                success=True,
                operation="create",
                row_id=1,
                duration_ms=100.0,
                error_message=None,
            ),
            Mock(
                success=False,
                operation="update",
                row_id=2,
                duration_ms=50.0,
                error_message="Resource not found",
            ),
            Mock(
                success=False,
                operation="delete",
                row_id=3,
                duration_ms=75.0,
                error_message="Permission denied",
            ),
        ]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        assert report.successful_operations == 1
        assert report.failed_operations == 2
        assert len(report.errors) == 2
        assert report.errors[0]["row_id"] == 2
        assert report.errors[1]["row_id"] == 3

    def test_generate_report_operation_breakdown(self):
        """Test report generation with operation type breakdown."""
        generator = ReportGenerator()

        results = [
            Mock(success=True, operation="create", row_id=1, duration_ms=100.0),
            Mock(success=True, operation="create", row_id=2, duration_ms=100.0),
            Mock(success=True, operation="update", row_id=3, duration_ms=100.0),
            Mock(success=True, operation="delete", row_id=4, duration_ms=100.0),
            Mock(success=True, operation="noop", row_id=5, duration_ms=10.0),
        ]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        assert report.creates == 2
        assert report.updates == 1
        assert report.deletes == 1
        assert report.noops == 1

    def test_generate_report_with_rollback(self):
        """Test report generation with rollback CSV."""
        generator = ReportGenerator()

        results = [Mock(success=True, operation="create", row_id=1, duration_ms=100.0)]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=Path("/path/to/rollback.csv"),
        )

        assert report.rollback_csv_generated is True
        assert report.rollback_csv_path == "/path/to/rollback.csv"

    def test_generate_report_dry_run(self):
        """Test report generation for dry run."""
        generator = ReportGenerator()

        results = [Mock(success=True, operation="create", row_id=1, duration_ms=100.0)]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=True,
            results=results,
            metrics={},
            rollback_path=None,
        )

        assert report.dry_run is True
        assert report.rollback_csv_generated is False

    def test_generate_report_empty_results(self):
        """Test report generation with empty results list."""
        generator = ReportGenerator()

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 1, 0),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=[],
            metrics={},
            rollback_path=None,
        )

        assert report.total_operations == 0
        assert report.successful_operations == 0
        assert report.failed_operations == 0
        assert report.avg_operation_duration_ms == 0
        assert report.max_operation_duration_ms == 0

    def test_generate_report_formats_timestamps(self):
        """Test report generation formats timestamps as ISO strings."""
        generator = ReportGenerator()

        results = [Mock(success=True, operation="create", row_id=1, duration_ms=100.0)]

        report = generator.generate_report(
            session_id="test-123",
            start_time=datetime(2024, 1, 1, 12, 30, 45),
            end_time=datetime(2024, 1, 1, 12, 31, 45),
            csv_file=Path("/path/to/file.csv"),
            dry_run=False,
            results=results,
            metrics={},
            rollback_path=None,
        )

        # Timestamps should be ISO format strings
        assert isinstance(report.start_time, str)
        assert isinstance(report.end_time, str)
        assert "2024-01-01" in report.start_time
        assert "12:30:45" in report.start_time


class TestReportGeneratorIntegration:
    """Integration tests for report generation."""

    def test_full_report_generation_workflow(self):
        """Test complete report generation workflow."""
        generator = ReportGenerator()

        # Simulate realistic execution results
        results = [
            Mock(
                success=True,
                operation="create",
                row_id=1,
                duration_ms=120.0,
                error_message=None,
            ),
            Mock(
                success=True,
                operation="create",
                row_id=2,
                duration_ms=150.0,
                error_message=None,
            ),
            Mock(
                success=True,
                operation="update",
                row_id=3,
                duration_ms=80.0,
                error_message=None,
            ),
            Mock(
                success=False,
                operation="delete",
                row_id=4,
                duration_ms=50.0,
                error_message="Resource is in use",
            ),
            Mock(success=True, operation="noop", row_id=5, duration_ms=5.0, error_message=None),
        ]

        report = generator.generate_report(
            session_id="integration-test-456",
            start_time=datetime(2024, 6, 15, 10, 0, 0),
            end_time=datetime(2024, 6, 15, 10, 5, 0),  # 5 minutes
            csv_file=Path("/data/imports/production.csv"),
            dry_run=False,
            results=results,
            metrics={"concurrency": 5, "throttle": "adaptive"},
            rollback_path=Path("/data/rollbacks/rollback_456.csv"),
        )

        # Verify all report fields
        assert report.session_id == "integration-test-456"
        assert report.total_operations == 5
        assert report.successful_operations == 4
        assert report.failed_operations == 1
        assert report.creates == 2
        assert report.updates == 1
        # Note: The operation breakdown counts all operations by type, regardless of success
        assert report.deletes == 1  # Counts all delete operations (including failed)
        assert report.noops == 1
        assert report.duration_seconds == 300.0  # 5 minutes
        assert report.operations_per_second == pytest.approx(0.0167, rel=1e-2)
        assert report.avg_operation_duration_ms == 81.0  # (120+150+80+50+5)/5
        assert report.max_operation_duration_ms == 150.0
        assert len(report.errors) == 1
        assert report.errors[0]["row_id"] == 4
        assert report.rollback_csv_generated is True
