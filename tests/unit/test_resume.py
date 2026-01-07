"""Unit tests for Batch Resume feature."""

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from src.importer.execution.executor import OperationExecutor
from src.importer.execution.planner import ExecutionBatch, ExecutionPlan
from src.importer.execution.runner import ImportRunner
from src.importer.persistence.checkpoint import Checkpoint


class TestResume:
    """Test Batch Resume functionality."""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.bam.url = "https://bam.example.com"
        config.bam.username = "user"
        config.bam.password = "pass"
        config.bam.verify_ssl = True
        return config

    @pytest.fixture
    def mock_console(self):
        return MagicMock(spec=Console)

    @pytest.fixture
    def runner(self, mock_config, mock_console):
        return ImportRunner(mock_config, mock_console)

    def test_calculate_file_hash(self, runner, tmp_path):
        """Test file hash calculation."""
        f = tmp_path / "test.csv"
        f.write_text("content")

        expected_hash = hashlib.sha256(b"content").hexdigest()
        assert runner._calculate_file_hash(f) == expected_hash

    @patch("src.importer.execution.runner.OperationFactory")
    @patch("src.importer.execution.runner.PendingResources")
    @patch("src.importer.execution.runner.CheckpointManager")
    @patch("src.importer.execution.runner.ImportRunner._calculate_file_hash")
    @patch("src.importer.execution.runner.Confirm")
    @patch("src.importer.execution.runner.BAMClient")
    @patch("src.importer.execution.runner.Resolver")
    @patch("src.importer.execution.runner.DependencyGraph")
    @patch("src.importer.execution.runner.DependencyPlanner")
    @patch("src.importer.execution.runner.ExecutionPlanner")
    @patch("src.importer.execution.runner.OperationExecutor")
    @patch("src.importer.execution.runner.CSVParser")
    @patch("src.importer.execution.runner.ChangeLog")
    @patch("src.importer.execution.runner.Progress")
    @pytest.mark.asyncio
    async def test_resume_prompt_yes(
        self,
        mock_progress,
        mock_changelog,
        mock_parser,
        mock_executor_cls,
        mock_exec_planner,
        mock_dep_planner,
        mock_graph,
        mock_resolver,
        mock_client_cls,
        mock_confirm,
        mock_hash,
        mock_ckpt_mgr_cls,
        mock_pending,
        mock_factory_cls,
        runner,
    ):
        """Test resume prompt accepted by user."""
        # Setup
        mock_hash.return_value = "hash123"
        mock_ckpt_mgr = mock_ckpt_mgr_cls.return_value

        # Found resumable session
        checkpoint = MagicMock(spec=Checkpoint)
        checkpoint.session_id = "sess_123"
        checkpoint.batch_id = 5
        checkpoint.completed_operations = 50
        mock_ckpt_mgr.find_resumable_session.return_value = checkpoint

        # Mock Client (ensure async methods)
        mock_client_instance = mock_client_cls.return_value
        mock_client_instance.login = AsyncMock()
        mock_client_instance.logout = AsyncMock()
        mock_client_instance.close = AsyncMock()
        mock_client_instance.authenticate = AsyncMock()

        # Mock Executor
        mock_executor_instance = mock_executor_cls.return_value
        mock_executor_instance.execute_plan = AsyncMock(return_value=[])

        # Mock Factory
        mock_factory_instance = mock_factory_cls.return_value
        mock_factory_instance.create_from_row = AsyncMock(return_value=MagicMock())

        # User says YES
        mock_confirm.ask.return_value = True

        # Run
        await runner.run_session(Path("test.csv"), dry_run=False, resume=None)

        # Verify
        mock_confirm.ask.assert_called_once()
        mock_executor_cls.assert_called_once()
        _, kwargs = mock_executor_cls.call_args
        assert kwargs["session_id"] == "sess_123"

        # Verify start_batch_id passed to execute_plan
        mock_executor = mock_executor_cls.return_value
        mock_executor.execute_plan.assert_awaited_once()
        _, call_kwargs = mock_executor.execute_plan.await_args
        assert call_kwargs["start_batch_id"] == 5

    @patch("src.importer.execution.executor.AdaptiveThrottle")
    @pytest.mark.asyncio
    async def test_executor_skips_batches(self, mock_throttle, mock_config):
        """Test executor skips batches based on start_batch_id."""
        # Setup
        executor = OperationExecutor(
            bam_client=MagicMock(), policy=mock_config.policy, allow_dangerous_operations=False
        )

        # Plan with 2 batches
        op1 = MagicMock()
        op2 = MagicMock()
        batch1 = ExecutionBatch(batch_id=1, operations=[op1], depth=0)
        batch2 = ExecutionBatch(batch_id=2, operations=[op2], depth=1)
        plan = ExecutionPlan(batches=[batch1, batch2], total_operations=2)

        # Mock execution
        executor._execute_batch = AsyncMock(return_value=[])

        # Execute resuming from batch 2
        await executor.execute_plan(plan, start_batch_id=2)

        # execute_batch should only be called for batch 2
        assert executor._execute_batch.call_count == 1
        args, _ = executor._execute_batch.call_args
        assert args[0].batch_id == 2
