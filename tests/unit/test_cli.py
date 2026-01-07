"""Unit tests for CLI interface."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner

from src.importer.cli import app


class TestCLI:
    """Test CLI interface."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.csv_file = Path(self.temp_dir) / "test.csv"
        self.csv_file.write_text(
            "row_id,object_type,action,config,address\n1,ip4_address,create,Default,10.1.0.1\n"
        )
        self.runner = CliRunner()

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def test_cli_app_structure(self):
        """Test CLI app structure."""
        # Verify app is a Typer instance
        assert app is not None
        assert isinstance(app, typer.Typer)
        assert callable(app)

    @patch("src.importer.cli.CSVParser")
    def test_validate_command_success(self, mock_parser_class):
        """Test successful validation command."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = [MagicMock(object_type="ip4_address")]
        mock_parser.errors = []
        mock_parser.get_error_summary.return_value = "No errors"

        result = self.runner.invoke(app, ["validate", str(self.csv_file)])

        assert result.exit_code == 0
        assert "Validation successful!" in result.stdout

    @patch("src.importer.cli.CSVParser")
    def test_validate_command_with_errors(self, mock_parser_class):
        """Test validation command with errors."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = []
        mock_parser.errors = ["Invalid CIDR"]
        mock_parser.get_error_summary.return_value = "Invalid CIDR on line 2"

        result = self.runner.invoke(app, ["validate", str(self.csv_file)])

        assert result.exit_code == 0  # Should not fail in non-strict mode
        assert "Found 1 validation errors" in result.stdout

    @patch("src.importer.cli.CSVParser")
    def test_validate_command_strict_mode(self, mock_parser_class):
        """Test validation command in strict mode."""
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = []
        mock_parser.errors = ["Invalid CIDR"]
        mock_parser.get_error_summary.return_value = "Invalid CIDR on line 2"

        result = self.runner.invoke(app, ["validate", str(self.csv_file), "--strict"])

        assert result.exit_code == 1  # Should fail in strict mode
        assert "Validation failed (strict mode)" in result.stdout

    def test_validate_command_file_not_found(self):
        """Test validation with non-existent file."""
        result = self.runner.invoke(app, ["validate", "nonexistent.csv"])

        assert result.exit_code == 2  # Typer validation error

    @patch("src.importer.cli.CSVParser")
    def test_validate_command_exception(self, mock_parser_class):
        """Test validation with parser exception."""
        mock_parser_class.side_effect = Exception("Parser error")

        result = self.runner.invoke(app, ["validate", str(self.csv_file)])

        assert result.exit_code == 1
        assert "Validation failed:" in result.stdout

    def test_apply_command_exists(self):
        """Test that apply command exists."""
        # Get help for apply command
        result = self.runner.invoke(app, ["apply", "--help"])

        assert result.exit_code == 0
        # Check that the help output contains command usage information
        assert "Usage:" in result.stdout or "apply" in result.stdout.lower()

    def test_export_command_exists(self):
        """Test that export command exists."""
        # Get help for export command
        result = self.runner.invoke(app, ["export", "--help"])

        assert result.exit_code == 0
        # Check that the help output contains command usage information
        assert "Usage:" in result.stdout or "export" in result.stdout.lower()

    def test_rollback_command_exists(self):
        """Test that rollback command exists."""
        # Get help for rollback command
        result = self.runner.invoke(app, ["rollback", "--help"])

        assert result.exit_code == 0
        # Check that the help output contains command usage information
        assert "Usage:" in result.stdout or "rollback" in result.stdout.lower()

    def test_status_command_exists(self):
        """Test that status command exists."""
        # Get help for status command
        result = self.runner.invoke(app, ["status", "--help"])

        assert result.exit_code == 0
        # Check that the help output contains command usage information
        assert "Usage:" in result.stdout or "status" in result.stdout.lower()

    def test_history_command_exists(self):
        """Test that history command exists."""
        # Get help for history command
        result = self.runner.invoke(app, ["history", "--help"])

        assert result.exit_code == 0
        # Check that the help output contains command usage information
        assert "Usage:" in result.stdout or "history" in result.stdout.lower()

    def test_version_command_exists(self):
        """Test that version command exists."""
        # Get help for version command
        result = self.runner.invoke(app, ["version", "--help"])

        assert result.exit_code == 0

    def test_self_test_command_exists(self):
        """Test that self-test command exists."""
        # Get help for self-test command
        result = self.runner.invoke(app, ["self-test", "--help"])

        assert result.exit_code == 0
        # Check that the help output contains command usage information
        assert "Usage:" in result.stdout or "self-test" in result.stdout.lower()
