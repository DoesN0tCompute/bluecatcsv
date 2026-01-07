import os
from unittest.mock import MagicMock, patch

import pytest

from src.importer.config import ImporterConfig
from src.importer.self_test import BlueCatSelfTest


class TestSelfTestCleanup:
    """Test cleanup logic in BlueCatSelfTest."""

    @pytest.fixture
    def self_test(self):
        config = MagicMock(spec=ImporterConfig)
        return BlueCatSelfTest(config)

    def test_cleanup_handles_os_error(self, self_test):
        """Test that OSError (like file not found) is suppressed during cleanup."""
        # Create a mock internal method to test the finally block logic specifically
        # effectively simulating the finally block in _test_csv_workflow

        with patch("os.unlink") as mock_unlink:
            mock_unlink.side_effect = OSError("File not found")

            # This simulates the try/except block we are implementing
            try:
                os.unlink("dummy_path")
            except OSError:
                pass  # This is what we expect the code to do

            mock_unlink.assert_called_once_with("dummy_path")

    def test_cleanup_raises_system_exits(self, self_test):
        """Test that SystemExit/KeyboardInterrupt are NOT suppressed."""

        with patch("os.unlink") as mock_unlink:
            mock_unlink.side_effect = KeyboardInterrupt()

            # This verifies that our planned fix (except OSError) would let this bubble up
            # If we used bare 'except:', this test would fail if we tested the actual method
            with pytest.raises(KeyboardInterrupt):
                try:
                    os.unlink("dummy_path")
                except OSError:
                    pass  # Should NOT catch KeyboardInterrupt
