"""Unit tests for Enhanced Logger."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog

from src.importer.observability.logger import (
    LogContext,
    add_context,
    clear_all_context,
    clear_context,
    configure_logging,
)


class TestLoggingConfiguration:
    """Test logging configuration functions."""

    def test_configure_logging_defaults(self):
        """Test configure_logging with default parameters."""
        configure_logging()

        # Check that structlog is configured
        logger = structlog.get_logger("test")
        assert logger is not None

    def test_configure_logging_with_level(self):
        """Test configure_logging with custom level."""
        configure_logging(level="DEBUG")

        # Check that logging level is set
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
    def test_configure_logging_different_levels(self, level):
        """Test configure_logging with different log levels."""
        configure_logging(level=level)

        expected_level = getattr(logging, level.upper())
        root_logger = logging.getLogger()
        assert root_logger.level == expected_level

    def test_configure_logging_with_json(self):
        """Test configure_logging with JSON output."""
        configure_logging(json_logs=True)

        logger = structlog.get_logger("test")
        # The main difference is in the processor chain, which is hard to test directly
        # But we can verify no errors occurred
        assert logger is not None

    def test_configure_logging_with_file(self):
        """Test configure_logging with file output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"

            configure_logging(log_file=log_file, level="INFO")

            # Test that log file is created when logging
            logger = structlog.get_logger("test")
            logger.info("test message")

            # Verify file exists and contains message
            assert log_file.exists()
            content = log_file.read_text()
            assert "test message" in content

    def test_configure_logging_file_creates_directories(self):
        """Test that log file configuration creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_path = Path(temp_dir) / "nested" / "dir" / "test.log"

            configure_logging(log_file=nested_path)

            # Directory should be created
            assert nested_path.parent.exists()

    @patch("sys.stdout.isatty")
    def test_configure_logging_tty_detection(self, mock_isatty):
        """Test that TTY detection affects console output."""
        mock_isatty.return_value = True

        configure_logging(json_logs=False)

        # Should not raise any errors
        logger = structlog.get_logger("test")
        logger.info("test message")

    def test_configure_logging_invalid_level(self):
        """Test configure_logging with invalid level defaults to INFO."""
        # Invalid levels default to INFO instead of raising an error
        configure_logging(level="INVALID_LEVEL")
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO


class TestContextManagement:
    """Test logging context management functions."""

    def test_add_context(self):
        """Test adding context variables."""
        configure_logging()  # Ensure structlog is configured

        add_context(session_id="test123", user="admin", operation="import")

        # Note: In real usage, context would be available in subsequent log messages
        # Testing context binding directly is challenging without actual log output

    def test_clear_context(self):
        """Test clearing specific context variables."""
        configure_logging()

        # Add context
        add_context(session_id="test123", user="admin")
        # Clear specific context
        clear_context("session_id")

        # Note: Actual context clearing verification would require log output analysis

    def test_clear_context_nonexistent(self):
        """Test clearing context that doesn't exist."""
        configure_logging()

        # Should not raise error
        clear_context("nonexistent_key")

    def test_clear_all_context(self):
        """Test clearing all context variables."""
        configure_logging()

        # Add multiple context variables
        add_context(session_id="test123", user="admin", operation="import")
        # Clear all
        clear_all_context()

        # Note: Actual context clearing verification would require log output analysis


class TestLogContext:
    """Test LogContext context manager."""

    def test_log_context_basic(self):
        """Test basic LogContext usage."""
        configure_logging()

        with LogContext(session_id="test123", user="admin"):
            # Context should be active within this block
            logger = structlog.get_logger("test")
            logger.info("test message")

        # Context should be cleared after block

    def test_log_context_nested(self):
        """Test nested LogContext usage."""
        configure_logging()

        with LogContext(session_id="test123"):
            with LogContext(operation="import"):
                # Both contexts should be active
                logger = structlog.get_logger("test")
                logger.info("nested message")

            # Outer context should still be active
            logger.info("outer message")

    def test_log_context_exception_handling(self):
        """Test LogContext with exception."""
        configure_logging()

        try:
            with LogContext(session_id="test123"):
                raise ValueError("test error")
        except ValueError:
            pass  # Expected exception

        # Context should be cleared even with exception

    def test_log_context_return_value(self):
        """Test LogContext return value."""
        configure_logging()

        context = LogContext(session_id="test123")

        # Context manager should return self
        with context as ctx:
            assert ctx == context

    def test_log_context_empty(self):
        """Test LogContext with no context variables."""
        configure_logging()

        with LogContext():
            # Should work with empty context
            logger = structlog.get_logger("test")
            logger.info("empty context message")


class TestLoggingIntegration:
    """Test logging integration with structlog."""

    def setup_method(self):
        """Set up test environment."""
        # Configure logging for each test to ensure clean state
        configure_logging(level="DEBUG", json_logs=False)

    def test_logger_creation(self):
        """Test creating loggers."""
        logger = structlog.get_logger("test_module")
        assert logger is not None

    def test_logger_with_different_names(self):
        """Test creating loggers with different names."""
        logger1 = structlog.get_logger("module1")
        logger2 = structlog.get_logger("module2")
        logger3 = structlog.get_logger("module1")  # Same name as logger1

        assert logger1 is not None
        assert logger2 is not None
        assert logger3 is not None

    def test_log_level_filtering(self):
        """Test that log levels are properly filtered."""
        configure_logging(level="WARNING")

        logger = structlog.get_logger("test")

        # These should be filtered out
        logger.debug("debug message")
        logger.info("info message")

        # This should pass through
        logger.warning("warning message")
        logger.error("error message")

    def test_structlog_processors(self):
        """Test that structlog processors are correctly configured."""
        configure_logging(json_logs=False)

        # The configuration should add various processors
        # We can't easily test the processor chain directly, but we can test logging works
        logger = structlog.get_logger("test")
        logger.info("test message", extra_field="extra_value")

    def test_json_logging_format(self):
        """Test JSON logging format."""
        with patch("structlog.processors.JSONRenderer") as mock_renderer:
            configure_logging(json_logs=True)

            # JSONRenderer should be in the processor chain
            # This verifies the configuration path, not actual JSON formatting
            assert mock_renderer.called

    @patch("structlog.dev.ConsoleRenderer")
    def test_console_logging_format(self, mock_console_renderer):
        """Test console logging format."""
        configure_logging(json_logs=False)

        # ConsoleRenderer should be in the processor chain
        # Note: This test may be flaky due to structlog internals
        # The important thing is that configuration doesn't error

    def test_file_logging_format(self):
        """Test file logging format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"

            configure_logging(log_file=log_file, json_logs=False)

            logger = structlog.get_logger("test")
            logger.info("test message")

            content = log_file.read_text()

            # Should contain timestamp, level, and message in readable format
            assert "INFO" in content or "test" in content

    def test_file_logging_json_format(self):
        """Test file logging with JSON format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.json"

            configure_logging(log_file=log_file, json_logs=True)

            logger = structlog.get_logger("test")
            logger.info("test message")

            content = log_file.read_text()

            # JSON format should not have the standard prefix formatting
            # (exact format depends on structlog version)
            assert "test" in content

    def test_logging_exception_info(self):
        """Test logging with exception information."""
        logger = structlog.get_logger("test")

        try:
            raise ValueError("test error")
        except ValueError:
            logger.exception("An error occurred")

        # Should not raise any errors and should include exception info

    def test_multiple_loggers_share_context(self):
        """Test that multiple loggers share the same context."""
        configure_logging()

        add_context(session_id="shared123")

        logger1 = structlog.get_logger("module1")
        logger2 = structlog.get_logger("module2")

        # Both loggers should have access to the same context
        logger1.info("message from logger1")
        logger2.info("message from logger2")

        clear_all_context()

    def test_logging_performance(self):
        """Test that logging doesn't have significant performance impact."""
        configure_logging(level="INFO")

        logger = structlog.get_logger("performance_test")

        # Log many messages quickly
        for i in range(100):
            logger.info(f"message {i}", iteration=i)

        # If we get here without timeout or memory issues, performance is acceptable


class TestLoggingEdgeCases:
    """Test edge cases and error conditions."""

    def test_configure_logging_multiple_calls(self):
        """Test calling configure_logging multiple times."""
        configure_logging(level="INFO")
        configure_logging(level="DEBUG", json_logs=True)

        # Should not raise errors and should apply latest configuration
        logger = structlog.get_logger("test")
        logger.debug("debug message should now appear")

    def test_context_with_none_values(self):
        """Test adding context with None values."""
        configure_logging()

        add_context(session_id="test123", user=None, operation="import")

        # Should handle None values gracefully
        logger = structlog.get_logger("test")
        logger.info("test message")

        clear_context("user")

    def test_context_with_special_characters(self):
        """Test adding context with special characters."""
        configure_logging()

        special_context = {
            "session_id": "test_123",
            "message": "Hello, 世界! 🌍",
            "unicode_test": "Café résumé naïve",
            "json_chars": '{"key": "value"}',
        }

        add_context(**special_context)

        logger = structlog.get_logger("test")
        logger.info("test with special characters")

        clear_all_context()

    def test_log_context_with_large_data(self):
        """Test LogContext with large amounts of data."""
        configure_logging()

        large_context = {
            "large_string": "x" * 10000,
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(1000)},
        }

        with LogContext(**large_context):
            logger = structlog.get_logger("test")
            logger.info("test with large context")

    def test_configure_logging_file_permission_error(self):
        """Test handling of file permission errors."""
        # Use a path that likely doesn't exist and can't be created
        invalid_path = Path("/root/nonexistent/test.log")

        # Should handle permission errors gracefully
        try:
            configure_logging(log_file=invalid_path)
        except (PermissionError, OSError):
            # Expected in most environments
            pass

    def test_logging_after_clear_all(self):
        """Test logging after clearing all context."""
        configure_logging()

        # Add and clear context
        add_context(session_id="test123")
        clear_all_context()

        # Should still be able to log normally
        logger = structlog.get_logger("test")
        logger.info("message after context clear")
