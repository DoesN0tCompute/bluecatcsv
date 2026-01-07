"""Tests for Unicode handling in CSV parser and row models (EDGE-008)."""

import pytest

from src.importer.models.csv_row import (
    strip_whitespace_and_validate_encoding,
    validate_name_encoding,
)


class TestUnicodeValidation:
    """Test suite for Unicode character handling in resource names."""

    def test_valid_unicode_names(self):
        """Test that valid Unicode names are accepted."""
        # German
        assert validate_name_encoding("Büro Netzwerk") == "Büro Netzwerk"
        # Japanese
        assert validate_name_encoding("サーバー") == "サーバー"
        # Chinese
        assert validate_name_encoding("网络服务器") == "网络服务器"
        # Mixed
        assert validate_name_encoding("Production-サーバー-01") == "Production-サーバー-01"
        # Accents
        assert validate_name_encoding("café") == "café"
        assert validate_name_encoding("naïve") == "naïve"

    def test_emoji_in_names(self):
        """Test that special Unicode characters are accepted."""
        # Special Unicode characters are valid
        assert validate_name_encoding("Production ★") == "Production ★"
        assert validate_name_encoding("Test † Server") == "Test † Server"

    def test_null_bytes_rejected(self):
        """Test that null bytes are rejected."""
        with pytest.raises(ValueError) as exc:
            validate_name_encoding("Server\x00Name")
        assert "null bytes" in str(exc.value)

    def test_control_characters_rejected(self):
        """Test that control characters (ASCII < 32, except tab/newline/cr) are rejected."""
        # Bell character (ASCII 7)
        with pytest.raises(ValueError) as exc:
            validate_name_encoding("Server\x07Name")
        assert "control character" in str(exc.value).lower()

        # Backspace (ASCII 8)
        with pytest.raises(ValueError) as exc:
            validate_name_encoding("Server\x08Name")
        assert "control character" in str(exc.value).lower()

        # Form feed (ASCII 12)
        with pytest.raises(ValueError) as exc:
            validate_name_encoding("Server\x0cName")
        assert "control character" in str(exc.value).lower()

    def test_allowed_whitespace_characters(self):
        """Test that tab, newline, and carriage return are allowed."""
        # Tab is common in descriptions
        assert validate_name_encoding("Server\tConfig") == "Server\tConfig"
        # While unusual in names, newlines might appear in description fields
        assert validate_name_encoding("Line1\nLine2") == "Line1\nLine2"
        # Carriage return
        assert validate_name_encoding("Line1\rLine2") == "Line1\rLine2"

    def test_empty_and_none_values(self):
        """Test that empty and None values pass through."""
        assert validate_name_encoding("") == ""
        assert validate_name_encoding(None) is None

    def test_combined_validator(self):
        """Test the combined strip_whitespace_and_validate_encoding function."""
        # Strips whitespace and validates
        assert (
            strip_whitespace_and_validate_encoding("  Server Name  ") is None
            or strip_whitespace_and_validate_encoding("  Server Name  ") == "Server Name"
        )

        # Rejects control characters after stripping
        with pytest.raises(ValueError):
            strip_whitespace_and_validate_encoding("  Server\x00Name  ")

    def test_standard_ascii_names(self):
        """Test that standard ASCII names work correctly."""
        assert validate_name_encoding("Production-Server-01") == "Production-Server-01"
        assert validate_name_encoding("test_network_192.168.1.0") == "test_network_192.168.1.0"
        assert validate_name_encoding("Block A (Main DC)") == "Block A (Main DC)"

    def test_special_characters_in_names(self):
        """Test that special printable characters are allowed."""
        # These are all printable and should be allowed
        assert validate_name_encoding("Server@DC1") == "Server@DC1"
        assert validate_name_encoding("Network#42") == "Network#42"
        assert validate_name_encoding("Block (Primary)") == "Block (Primary)"
        assert validate_name_encoding("Test/Dev/Prod") == "Test/Dev/Prod"
