"""Unit tests for Rollback CLI command."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from src.importer.cli import app


class TestRollbackCLI:
    """Test Rollback CLI command."""

    def setup_method(self):
        self.runner = CliRunner()
        self.csv_file = Path("rollback.csv")

    @patch("src.importer.execution.runner.ImportRunner")
    @patch("src.importer.cli.ImporterConfig")
    def test_rollback_command_execution(self, mock_config, mock_runner_class):
        """Test rollback command executes ImportRunner correctly."""
        # Setup mocks
        mock_runner_instance = mock_runner_class.return_value
        mock_runner_instance.run_session = AsyncMock(return_value=0)

        with self.runner.isolated_filesystem():
            # Create a dummy rollback file
            with open("rollback.csv", "w") as f:
                f.write("test")

            # Invoke command
            result = self.runner.invoke(app, ["rollback", "rollback.csv", "--yes"])

            assert result.exit_code == 0

            # Verify ImportRunner call
            mock_runner_instance.run_session.assert_awaited_once()
            call_kwargs = mock_runner_instance.run_session.await_args.kwargs

            assert call_kwargs["csv_file"] == Path("rollback.csv")
            assert call_kwargs["allow_dangerous_operations"] is True  # Should be forced True
            assert call_kwargs["generate_rollback"] is False  # Should be False for rollback

    @patch("src.importer.execution.runner.ImportRunner")
    @patch("src.importer.cli.ImporterConfig")
    def test_rollback_command_dry_run(self, mock_config, mock_runner_class):
        """Test rollback command in dry-run mode."""
        mock_runner_instance = mock_runner_class.return_value
        mock_runner_instance.run_session = AsyncMock(return_value=0)

        with self.runner.isolated_filesystem():
            with open("rollback.csv", "w") as f:
                f.write("test")

            result = self.runner.invoke(
                app, ["rollback", "rollback.csv", "--dry-run"]
            )  # No --yes needed for dry-run?

            # Note: The CLI implementation checks 'yes' OR 'dry_run' before prompting.
            # "if not yes and not dry_run: prompt"
            # So dry-run should skip prompt.

            assert result.exit_code == 0
            call_kwargs = mock_runner_instance.run_session.await_args.kwargs
            assert call_kwargs["dry_run"] is True

    @patch("src.importer.execution.runner.ImportRunner")
    def test_rollback_aborted(self, mock_runner_class):
        """Test rollback aborted by user."""
        with self.runner.isolated_filesystem():
            with open("rollback.csv", "w") as f:
                f.write("test")

            result = self.runner.invoke(app, ["rollback", "rollback.csv"], input="n\n")

            assert result.exit_code != 0
            assert isinstance(result.exception, SystemExit) or result.exit_code == 1
            mock_runner_class.return_value.run_session.assert_not_called()
