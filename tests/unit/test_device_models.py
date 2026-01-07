"""Unit tests for device-related CSV row models."""

import pytest
from pydantic import ValidationError

from src.importer.models.csv_row import (
    DeviceAddressRow,
    DeviceRow,
    DeviceSubtypeRow,
    DeviceTypeRow,
)


class TestDeviceTypeRow:
    """Test DeviceTypeRow validation."""

    def test_valid_device_type(self):
        """Test creating a valid device type row."""
        row = DeviceTypeRow(
            row_id=1,
            object_type="device_type",
            action="create",
            name="Cisco",
        )
        assert row.name == "Cisco"
        assert row.object_type == "device_type"
        assert row.action == "create"

    def test_device_type_whitespace_stripped(self):
        """Test that whitespace is stripped from name."""
        row = DeviceTypeRow(
            row_id=1,
            object_type="device_type",
            action="create",
            name="  Fortinet  ",
        )
        assert row.name == "Fortinet"

    def test_device_type_missing_name(self):
        """Test that missing name raises validation error."""
        with pytest.raises(ValidationError):
            DeviceTypeRow(
                row_id=1,
                object_type="device_type",
                action="create",
                name=None,
            )

    def test_device_type_update_action(self):
        """Test device type with update action."""
        row = DeviceTypeRow(
            row_id=2,
            object_type="device_type",
            action="update",
            name="Palo Alto",
        )
        assert row.action == "update"

    def test_device_type_delete_action(self):
        """Test device type with delete action."""
        row = DeviceTypeRow(
            row_id=3,
            object_type="device_type",
            action="delete",
            name="Old-Type",
        )
        assert row.action == "delete"


class TestDeviceSubtypeRow:
    """Test DeviceSubtypeRow validation."""

    def test_valid_device_subtype(self):
        """Test creating a valid device subtype row."""
        row = DeviceSubtypeRow(
            row_id=1,
            object_type="device_subtype",
            action="create",
            device_type="Cisco",
            name="Catalyst-3750",
        )
        assert row.device_type == "Cisco"
        assert row.name == "Catalyst-3750"

    def test_device_subtype_whitespace_stripped(self):
        """Test that whitespace is stripped from fields."""
        row = DeviceSubtypeRow(
            row_id=1,
            object_type="device_subtype",
            action="create",
            device_type="  Fortinet  ",
            name="  FortiGate-600E  ",
        )
        assert row.device_type == "Fortinet"
        assert row.name == "FortiGate-600E"

    def test_device_subtype_missing_device_type(self):
        """Test that missing device_type raises validation error."""
        with pytest.raises(ValidationError):
            DeviceSubtypeRow(
                row_id=1,
                object_type="device_subtype",
                action="create",
                device_type=None,
                name="ASA-5505",
            )

    def test_device_subtype_missing_name(self):
        """Test that missing name raises validation error."""
        with pytest.raises(ValidationError):
            DeviceSubtypeRow(
                row_id=1,
                object_type="device_subtype",
                action="create",
                device_type="Cisco",
                name=None,
            )


class TestDeviceRow:
    """Test DeviceRow validation."""

    def test_valid_device_minimal(self):
        """Test creating a device with minimal required fields."""
        row = DeviceRow(
            row_id=1,
            object_type="device",
            action="create",
            config="Default",
            name="firewall-01",
        )
        assert row.config == "Default"
        assert row.name == "firewall-01"
        assert row.device_type is None
        assert row.device_subtype is None
        assert row.addresses is None
        assert row.mac_address is None

    def test_valid_device_full(self):
        """Test creating a device with all fields."""
        row = DeviceRow(
            row_id=1,
            object_type="device",
            action="create",
            config="Default",
            name="firewall-01",
            device_type="Fortinet",
            device_subtype="FortiGate-600E",
            addresses="10.0.1.1|10.0.2.1",
            mac_address="00:11:22:33:44:55",
        )
        assert row.device_type == "Fortinet"
        assert row.device_subtype == "FortiGate-600E"
        assert row.addresses == "10.0.1.1|10.0.2.1"
        assert row.mac_address == "00:11:22:33:44:55"

    def test_device_missing_config(self):
        """Test that missing config raises validation error."""
        with pytest.raises(ValidationError):
            DeviceRow(
                row_id=1,
                object_type="device",
                action="create",
                config=None,
                name="firewall-01",
            )

    def test_device_missing_name(self):
        """Test that missing name raises validation error."""
        with pytest.raises(ValidationError):
            DeviceRow(
                row_id=1,
                object_type="device",
                action="create",
                config="Default",
                name=None,
            )

    def test_device_valid_mac_colon_format(self):
        """Test valid MAC address with colon separator."""
        row = DeviceRow(
            row_id=1,
            object_type="device",
            action="create",
            config="Default",
            name="test-device",
            mac_address="00:11:22:33:44:55",
        )
        assert row.mac_address == "00:11:22:33:44:55"

    def test_device_valid_mac_dash_format(self):
        """Test valid MAC address with dash separator."""
        row = DeviceRow(
            row_id=1,
            object_type="device",
            action="create",
            config="Default",
            name="test-device",
            mac_address="00-11-22-33-44-55",
        )
        assert row.mac_address == "00-11-22-33-44-55"

    def test_device_invalid_mac(self):
        """Test that invalid MAC address raises validation error."""
        with pytest.raises(ValidationError, match="Invalid MAC address format"):
            DeviceRow(
                row_id=1,
                object_type="device",
                action="create",
                config="Default",
                name="test-device",
                mac_address="invalid-mac",
            )

    def test_device_empty_mac_allowed(self):
        """Test that empty MAC address is allowed."""
        row = DeviceRow(
            row_id=1,
            object_type="device",
            action="create",
            config="Default",
            name="test-device",
            mac_address="",
        )
        # Empty string should be converted to None
        assert row.mac_address is None or row.mac_address == ""

    def test_device_addresses_pipe_separated(self):
        """Test pipe-separated addresses field."""
        row = DeviceRow(
            row_id=1,
            object_type="device",
            action="create",
            config="Default",
            name="firewall-01",
            addresses="10.0.1.1|10.0.2.1|192.168.1.1",
        )
        # The field stores raw string; parsing is done in operation factory
        assert row.addresses == "10.0.1.1|10.0.2.1|192.168.1.1"


class TestDeviceAddressRow:
    """Test DeviceAddressRow validation."""

    def test_valid_device_address(self):
        """Test creating a valid device address row."""
        row = DeviceAddressRow(
            row_id=1,
            object_type="device_address",
            action="create",
            config="Default",
            device_name="firewall-01",
            address="10.0.1.1",
        )
        assert row.config == "Default"
        assert row.device_name == "firewall-01"
        assert row.address == "10.0.1.1"

    def test_device_address_ipv6(self):
        """Test device address with IPv6."""
        row = DeviceAddressRow(
            row_id=1,
            object_type="device_address",
            action="create",
            config="Default",
            device_name="router-01",
            address="2001:db8::1",
        )
        assert row.address == "2001:db8::1"

    def test_device_address_missing_config(self):
        """Test that missing config raises validation error."""
        with pytest.raises(ValidationError):
            DeviceAddressRow(
                row_id=1,
                object_type="device_address",
                action="create",
                config=None,
                device_name="firewall-01",
                address="10.0.1.1",
            )

    def test_device_address_missing_device_name(self):
        """Test that missing device_name raises validation error."""
        with pytest.raises(ValidationError):
            DeviceAddressRow(
                row_id=1,
                object_type="device_address",
                action="create",
                config="Default",
                device_name=None,
                address="10.0.1.1",
            )

    def test_device_address_missing_address(self):
        """Test that missing address raises validation error."""
        with pytest.raises(ValidationError):
            DeviceAddressRow(
                row_id=1,
                object_type="device_address",
                action="create",
                config="Default",
                device_name="firewall-01",
                address=None,
            )

    def test_device_address_invalid_ip(self):
        """Test that invalid IP address raises validation error."""
        with pytest.raises(ValidationError, match="Invalid IP address"):
            DeviceAddressRow(
                row_id=1,
                object_type="device_address",
                action="create",
                config="Default",
                device_name="firewall-01",
                address="invalid-ip",
            )

    def test_device_address_delete_action(self):
        """Test device address with delete action."""
        row = DeviceAddressRow(
            row_id=1,
            object_type="device_address",
            action="delete",
            config="Default",
            device_name="firewall-01",
            address="10.0.1.1",
        )
        assert row.action == "delete"

    def test_device_address_whitespace_stripped(self):
        """Test that whitespace is stripped from fields."""
        row = DeviceAddressRow(
            row_id=1,
            object_type="device_address",
            action="create",
            config="  Default  ",
            device_name="  firewall-01  ",
            address="  10.0.1.1  ",
        )
        assert row.config == "Default"
        assert row.device_name == "firewall-01"
        assert row.address == "10.0.1.1"
