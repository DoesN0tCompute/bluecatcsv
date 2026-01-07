"""Unit tests for ImportRunner."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from src.importer.execution.runner import ImportRunner
from src.importer.models.operations import OperationType


class TestImportRunner:
    """Test ImportRunner class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = MagicMock()
        self.config.bam.url = "https://bam.example.com"
        self.config.bam.username = "user"
        self.config.bam.password = "pass"
        self.config.bam.verify_ssl = True

        self.console = MagicMock(spec=Console)
        self.runner = ImportRunner(self.config, self.console)

    @patch("src.importer.execution.runner.Progress")
    @patch("src.importer.execution.runner.BAMClient")
    @patch("src.importer.execution.runner.Resolver")
    @patch("src.importer.execution.runner.DependencyGraph")
    @patch("src.importer.execution.runner.DependencyPlanner")
    @patch("src.importer.execution.runner.ExecutionPlanner")
    @patch("src.importer.execution.runner.OperationExecutor")
    @patch("src.importer.execution.runner.CSVParser")
    @patch("src.importer.execution.runner.ChangeLog")
    @patch("src.importer.execution.runner.CheckpointManager")
    @patch("src.importer.execution.runner.RollbackGenerator")
    @patch("src.importer.execution.runner.ImportRunner._calculate_file_hash")
    @patch("src.importer.execution.runner.Confirm")
    @pytest.mark.asyncio
    async def test_run_session_success(
        self,
        mock_confirm,
        mock_hash,
        mock_rollback_gen,
        mock_ckpt_mgr,
        mock_changelog,
        mock_parser,
        mock_executor,
        mock_exec_planner,
        mock_dep_planner,
        mock_graph,
        mock_resolver,
        mock_client,
        mock_progress,
    ):
        """Test successful session execution."""
        # Setup mocks
        mock_hash.return_value = "dummyhash"
        mock_ckpt_mgr.return_value.find_resumable_session.return_value = None
        mock_parser_instance = mock_parser.return_value
        mock_parser_instance.parse.return_value = [
            MagicMock(row_id=1, object_type="network", action="create")
        ]

        mock_client_instance = mock_client.return_value
        mock_client_instance.login = AsyncMock()
        mock_client_instance.logout = AsyncMock()
        mock_client_instance.close = AsyncMock()
        mock_client_instance.authenticate = AsyncMock()
        mock_client_instance.get_configuration_by_name = AsyncMock(return_value={"id": 1})

        mock_executor_instance = mock_executor.return_value
        result = MagicMock()
        result.success = True
        result.metadata = {}
        mock_executor_instance.execute_plan.return_value = [result]
        mock_executor_instance.execute_plan = AsyncMock(return_value=[result])

        mock_plan = MagicMock()
        mock_plan.total_operations = 1
        mock_exec_planner.return_value.create_plan.return_value = mock_plan

        # Run session
        failed = await self.runner.run_session(
            csv_file=Path("test.csv"),
            dry_run=False,
            allow_dangerous_operations=False,
            generate_rollback=True,
        )

        # Verify
        assert failed == 0
        mock_client_instance.authenticate.assert_awaited_once()
        mock_changelog.assert_called_once()
        mock_executor.return_value.execute_plan.assert_called_once()

        # Verify rollback generation
        mock_rollback_gen.return_value.generate_rollback_csv.assert_called_once()

    @patch("src.importer.execution.runner.OperationFactory")
    @patch("src.importer.execution.runner.Progress")
    @patch("src.importer.execution.runner.BAMClient")
    @patch("src.importer.execution.runner.Resolver")
    @patch("src.importer.execution.runner.DependencyGraph")
    @patch("src.importer.execution.runner.DependencyPlanner")
    @patch("src.importer.execution.runner.ExecutionPlanner")
    @patch("src.importer.execution.runner.OperationExecutor")
    @patch("src.importer.execution.runner.CSVParser")
    @patch("src.importer.execution.runner.ChangeLog")
    @patch("src.importer.execution.runner.CheckpointManager")
    @patch("src.importer.execution.runner.RollbackGenerator")
    @patch("src.importer.execution.runner.ImportRunner._calculate_file_hash")
    @patch("src.importer.execution.runner.Confirm")
    @pytest.mark.asyncio
    async def test_run_session_cache_invalidation(
        self,
        mock_confirm,
        mock_hash,
        mock_rollback_gen,
        mock_ckpt_mgr,
        mock_changelog,
        mock_parser,
        mock_executor,
        mock_exec_planner,
        mock_dep_planner,
        mock_graph,
        mock_resolver_cls,
        mock_client,
        mock_progress,
        mock_factory_cls,
    ):
        """Test that successful DELETE operations invalidate the cache."""
        # Setup hash
        mock_hash.return_value = "hash123"
        mock_ckpt_mgr.return_value.find_resumable_session.return_value = None

        # Setup CSV
        row = MagicMock()
        row.row_id = 99
        row.action = "delete"
        row.object_type = "ip4_block"
        mock_parser.return_value.parse.return_value = [row]

        # Setup Factory operation
        op = MagicMock()
        op.row_id = 99
        op.operation_type = OperationType.DELETE
        op.object_type = "ip4_block"
        op.payload = {"resource_path": "Default/10.0.0.0/8"}
        mock_factory_cls.return_value.create_from_row = AsyncMock(return_value=op)

        # Setup Client logout
        mock_client.return_value.logout = AsyncMock()
        mock_client.return_value.login = AsyncMock()
        mock_client.return_value.close = AsyncMock()
        mock_client.return_value.authenticate = AsyncMock()

        # Setup Resolver invalidate (now async)
        mock_resolver_cls.return_value.invalidate = AsyncMock()

        # Setup Executor result
        result = MagicMock()
        result.row_id = 99
        result.success = True
        result.operation = OperationType.DELETE
        mock_executor.return_value.execute_plan = AsyncMock(return_value=[result])

        # Run
        await self.runner.run_session(Path("dummy.csv"))

        # Verify invalidate called (use assert_any_call since there are 2 calls: path and parent)
        mock_resolver_instance = mock_resolver_cls.return_value
        mock_resolver_instance.invalidate.assert_any_call("Default/10.0.0.0/8", "ip4_block")

        # Verify rollback generation
        mock_rollback_gen.return_value.generate_rollback_csv.assert_called_once()

    @patch("src.importer.execution.runner.Progress")
    @patch("src.importer.execution.runner.BAMClient")
    @patch("src.importer.execution.runner.Resolver")
    @patch("src.importer.execution.runner.DependencyGraph")
    @patch("src.importer.execution.runner.DependencyPlanner")
    @patch("src.importer.execution.runner.ExecutionPlanner")
    @patch("src.importer.execution.runner.OperationExecutor")
    @patch("src.importer.execution.runner.CSVParser")
    @patch("src.importer.execution.runner.ChangeLog")
    @patch("src.importer.execution.runner.CheckpointManager")
    @patch("src.importer.execution.runner.ImportRunner._calculate_file_hash")
    @patch("src.importer.execution.runner.Confirm")
    @pytest.mark.asyncio
    async def test_run_session_failure(
        self,
        mock_confirm,
        mock_hash,
        mock_ckpt_mgr,
        mock_changelog,
        mock_parser,
        mock_executor,
        mock_exec_planner,
        mock_dep_planner,
        mock_graph,
        mock_resolver,
        mock_client,
        mock_progress,
    ):
        """Test session with failures."""
        # Setup mocks
        mock_hash.return_value = "dummyhash"
        mock_ckpt_mgr.return_value.find_resumable_session.return_value = None
        mock_parser_instance = mock_parser.return_value
        mock_parser_instance.parse.return_value = [
            MagicMock(row_id=1, object_type="network", action="create")
        ]

        mock_client_instance = mock_client.return_value
        mock_client_instance.login = AsyncMock()
        mock_client_instance.logout = AsyncMock()
        mock_client_instance.close = AsyncMock()
        mock_client_instance.authenticate = AsyncMock()
        mock_client_instance.get_configuration_by_name = AsyncMock(return_value={"id": 1})

        mock_executor_instance = mock_executor.return_value
        result = MagicMock()
        result.success = False
        result.error_message = "Failed"
        result.metadata = {}
        mock_executor_instance.execute_plan = AsyncMock(return_value=[result])

        mock_plan = MagicMock()
        mock_plan.total_operations = 1

        mock_exec_planner.return_value.create_plan.return_value = mock_plan

        # Run session
        failed = await self.runner.run_session(csv_file=Path("test.csv"), dry_run=False)

        assert failed == 1

    @patch("src.importer.execution.runner.Progress")
    @patch("src.importer.execution.runner.BAMClient")
    @patch("src.importer.execution.runner.CSVParser")
    @patch("src.importer.execution.runner.ImportRunner._calculate_file_hash")
    @pytest.mark.asyncio
    async def test_run_session_empty_csv(
        self,
        mock_hash,
        mock_parser,
        mock_client,
        mock_progress,
    ):
        """Test session with empty CSV file."""
        # Setup mocks
        mock_hash.return_value = "dummyhash"
        mock_parser_instance = mock_parser.return_value
        mock_parser_instance.parse.return_value = []  # Empty CSV

        mock_client_instance = mock_client.return_value
        mock_client_instance.authenticate = AsyncMock()
        mock_client_instance.close = AsyncMock()

        # Create mock progress context manager
        mock_progress_instance = MagicMock()
        mock_progress_ctx = MagicMock()
        mock_progress_ctx.__enter__ = MagicMock(return_value=mock_progress_instance)
        mock_progress_ctx.__exit__ = MagicMock(return_value=False)
        mock_progress.return_value = mock_progress_ctx

        # Run session with empty CSV
        result = await self.runner.run_session(csv_file=Path("empty.csv"), dry_run=False)

        # Should return success with 0 operations
        assert result["success"] is True
        assert result["total_operations"] == 0
        assert result["successful_operations"] == 0
        assert result["failed_operations"] == 0
        assert "empty" in result["message"].lower()
