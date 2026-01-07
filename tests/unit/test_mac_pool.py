"""Unit tests for MAC Pool Management functionality.

Tests cover:
- MAC Pool CSV row models
- MAC Address CSV row models
- MAC address format validation
- Handler registration
"""

import pytest
from pydantic import ValidationError

from src.importer.execution.handlers import get_handler
from src.importer.models.csv_row import MACAddressRow, MACPoolRow


class TestMACPoolRow:
    """Tests for MACPoolRow model."""

    def test_valid_mac_pool(self):
        """Test valid MAC pool parsing."""
        row = MACPoolRow(
            row_id=1,
            object_type="mac_pool",
            action="create",
            config="Default",
            name="VoIP-Phones",
            pool_type="MACPool",
        )
        assert row.name == "VoIP-Phones"
        assert row.config == "Default"
        assert row.pool_type == "MACPool"

    def test_mac_pool_default_type(self):
        """Test MAC pool default type is MACPool."""
        row = MACPoolRow(
            row_id=1,
            object_type="mac_pool",
            action="create",
            config="Default",
            name="TestPool",
        )
        assert row.pool_type == "MACPool"

    def test_deny_mac_pool(self):
        """Test DenyMACPool type."""
        row = MACPoolRow(
            row_id=1,
            object_type="mac_pool",
            action="create",
            config="Default",
            name="Blocked-Devices",
            pool_type="DenyMACPool",
        )
        assert row.pool_type == "DenyMACPool"

    def test_invalid_pool_type(self):
        """Test that invalid pool type raises error."""
        with pytest.raises(ValidationError):
            MACPoolRow(
                row_id=1,
                object_type="mac_pool",
                action="create",
                config="Default",
                name="TestPool",
                pool_type="InvalidType",
            )

    def test_whitespace_stripped_from_name(self):
        """Test that whitespace is stripped from name."""
        row = MACPoolRow(
            row_id=1,
            object_type="mac_pool",
            action="create",
            config="Default",
            name="  VoIP-Phones  ",
        )
        assert row.name == "VoIP-Phones"


class TestMACAddressRow:
    """Tests for MACAddressRow model."""

    def test_valid_mac_address_colon_format(self):
        """Test valid MAC address with colon separators."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="00:11:22:33:44:55",
            name="test-device",
        )
        assert row.mac_address == "00:11:22:33:44:55"
        assert row.name == "test-device"

    def test_valid_mac_address_hyphen_format(self):
        """Test valid MAC address with hyphen separators."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="00-11-22-33-44-55",
        )
        # Should be normalized to colon format
        assert row.mac_address == "00:11:22:33:44:55"

    def test_valid_mac_address_lowercase(self):
        """Test valid MAC address with lowercase letters."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="aa:bb:cc:dd:ee:ff",
        )
        # Should be normalized to uppercase
        assert row.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_valid_mac_address_no_separators(self):
        """Test valid MAC address without separators."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="001122334455",
        )
        # Should be normalized with colons
        assert row.mac_address == "00:11:22:33:44:55"

    def test_valid_mac_address_dot_format(self):
        """Test valid MAC address with dot separators (Cisco format)."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="0011.2233.4455",
        )
        # Should be normalized with colons
        assert row.mac_address == "00:11:22:33:44:55"

    def test_invalid_mac_address_too_short(self):
        """Test that too short MAC address raises error."""
        with pytest.raises(ValidationError) as exc:
            MACAddressRow(
                row_id=1,
                object_type="mac_address",
                action="create",
                config="Default",
                mac_address="00:11:22:33:44",
            )
        assert "Invalid MAC address length" in str(exc.value)

    def test_invalid_mac_address_too_long(self):
        """Test that too long MAC address raises error."""
        with pytest.raises(ValidationError) as exc:
            MACAddressRow(
                row_id=1,
                object_type="mac_address",
                action="create",
                config="Default",
                mac_address="00:11:22:33:44:55:66",
            )
        assert "Invalid MAC address length" in str(exc.value)

    def test_invalid_mac_address_invalid_chars(self):
        """Test that MAC address with invalid characters raises error."""
        with pytest.raises(ValidationError) as exc:
            MACAddressRow(
                row_id=1,
                object_type="mac_address",
                action="create",
                config="Default",
                mac_address="00:11:22:33:44:GG",
            )
        assert "Invalid MAC address format" in str(exc.value)

    def test_empty_mac_address(self):
        """Test that empty MAC address raises error."""
        with pytest.raises(ValidationError):
            MACAddressRow(
                row_id=1,
                object_type="mac_address",
                action="create",
                config="Default",
                mac_address="",
            )

    def test_mac_address_with_pool(self):
        """Test MAC address with pool association."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="00:11:22:33:44:55",
            name="voip-phone",
            pool_name="VoIP-Phones",
        )
        assert row.pool_name == "VoIP-Phones"

    def test_mac_address_without_pool(self):
        """Test MAC address without pool association."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="00:11:22:33:44:55",
        )
        assert row.pool_name is None

    def test_mac_address_optional_name(self):
        """Test MAC address with optional name."""
        row = MACAddressRow(
            row_id=1,
            object_type="mac_address",
            action="create",
            config="Default",
            mac_address="00:11:22:33:44:55",
        )
        assert row.name is None


class TestMACPoolHandlerRegistration:
    """Tests for MAC Pool handler registration."""

    def test_mac_pool_handler_registered(self):
        """Test that mac_pool handler is registered."""
        handler = get_handler("mac_pool")
        assert handler is not None

    def test_mac_address_handler_registered(self):
        """Test that mac_address handler is registered."""
        handler = get_handler("mac_address")
        assert handler is not None
