import os
from unittest.mock import MagicMock

from src.importer.execution.runner import ImportRunner
from src.importer.models.operations import Operation, OperationType


def test_generate_dry_run_report(tmp_path):
    # Setup
    config = MagicMock()
    console = MagicMock()
    runner = ImportRunner(config, console)

    # Mock results
    op = MagicMock(spec=Operation)
    op.operation_type = OperationType.CREATE
    op.object_type = "network"
    op.row_id = "1"
    op.csv_row = MagicMock()
    op.csv_row.name = "TestNet"
    op.csv_row.cidr = "10.0.0.0/24"
    # Ensure attributes exist to avoid AttributeError in _format_operation_details checks
    op.csv_row.ip_address = None
    op.csv_row.zone_name = None
    op.csv_row.config = "Default"

    result = MagicMock()
    result.success = True
    result.operation = OperationType.CREATE
    result.row_id = "1"
    result.metadata = {}

    results = [result]
    session_id = "test_session"
    duration = 1.5

    # Change CWD to tmp_path to capture file
    orig_cwd = os.getcwd()
    os.chdir(tmp_path)
    ops_map = {"1": op}
    try:
        runner._generate_dry_run_report(results, session_id, duration, ops_map)

        report_file = tmp_path / f"dry_run_report_{session_id}.md"
        assert report_file.exists()
        content = report_file.read_text()

        print(content)

        assert "# Dry Run Report: test_session" in content
        assert "Proposed Changes:** 1" in content
        assert (
            "| 1 | CREATE | network | Name: TestNet, CIDR: 10.0.0.0/24, (Config: Default) |"
            in content
        )
    finally:
        os.chdir(orig_cwd)
