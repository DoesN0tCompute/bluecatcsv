"""Unit tests for User-Defined Links functionality.

Tests cover:
- UserDefinedLinkRow CSV model
- Handler registration
- Collection type mapping
"""

import pytest

from src.importer.execution.handlers import UserDefinedLinkHandler, get_handler
from src.importer.models.csv_row import UserDefinedLinkRow


class TestUserDefinedLinkRow:
    """Tests for UserDefinedLinkRow model."""

    def test_valid_user_defined_link(self):
        """Test valid user-defined link parsing."""
        row = UserDefinedLinkRow(
            row_id=1,
            object_type="user_defined_link",
            action="create",
            config="Default",
            udl_name="AssociatedDevice",
            source_type="ip4_address",
            source_path="10.0.1.10",
            destination_type="device",
            destination_path="firewall-01",
            description="Primary firewall address",
        )
        assert row.udl_name == "AssociatedDevice"
        assert row.source_type == "ip4_address"
        assert row.source_path == "10.0.1.10"
        assert row.destination_type == "device"
        assert row.destination_path == "firewall-01"
        assert row.description == "Primary firewall address"

    def test_user_defined_link_without_description(self):
        """Test user-defined link without optional description."""
        row = UserDefinedLinkRow(
            row_id=1,
            object_type="user_defined_link",
            action="create",
            config="Default",
            udl_name="AssociatedDevice",
            source_type="ip4_address",
            source_path="10.0.1.10",
            destination_type="device",
            destination_path="firewall-01",
        )
        assert row.description is None

    def test_whitespace_stripped(self):
        """Test that whitespace is stripped from fields."""
        row = UserDefinedLinkRow(
            row_id=1,
            object_type="user_defined_link",
            action="create",
            config="Default",
            udl_name="  AssociatedDevice  ",
            source_type="  ip4_address  ",
            source_path="  10.0.1.10  ",
            destination_type="  device  ",
            destination_path="  firewall-01  ",
        )
        assert row.udl_name == "AssociatedDevice"
        assert row.source_type == "ip4_address"
        assert row.source_path == "10.0.1.10"
        assert row.destination_type == "device"
        assert row.destination_path == "firewall-01"

    def test_various_resource_types(self):
        """Test user-defined links with various resource types."""
        test_cases = [
            ("ip4_address", "device"),
            ("ip4_network", "device"),
            ("ip6_address", "server"),
            ("host_record", "host_record"),
            ("dns_zone", "server"),
        ]
        for source_type, dest_type in test_cases:
            row = UserDefinedLinkRow(
                row_id=1,
                object_type="user_defined_link",
                action="create",
                config="Default",
                udl_name="TestLink",
                source_type=source_type,
                source_path="test-source",
                destination_type=dest_type,
                destination_path="test-dest",
            )
            assert row.source_type == source_type
            assert row.destination_type == dest_type


class TestUserDefinedLinkHandler:
    """Tests for UserDefinedLinkHandler."""

    def test_handler_registered(self):
        """Test that user_defined_link handler is registered."""
        handler = get_handler("user_defined_link")
        assert handler is not None
        assert isinstance(handler, UserDefinedLinkHandler)

    def test_resource_type_to_collection_mapping(self):
        """Test resource type to collection mapping."""
        handler = UserDefinedLinkHandler()

        # Test various mappings
        assert handler._get_collection_for_type("ip4_address") == "addresses"
        assert handler._get_collection_for_type("ip6_address") == "addresses"
        assert handler._get_collection_for_type("ip4_block") == "blocks"
        assert handler._get_collection_for_type("ip6_block") == "blocks"
        assert handler._get_collection_for_type("ip4_network") == "networks"
        assert handler._get_collection_for_type("ip6_network") == "networks"
        assert handler._get_collection_for_type("device") == "devices"
        assert handler._get_collection_for_type("mac_address") == "macAddresses"
        assert handler._get_collection_for_type("mac_pool") == "macPools"
        assert handler._get_collection_for_type("dns_zone") == "zones"
        assert handler._get_collection_for_type("view") == "views"
        assert handler._get_collection_for_type("server") == "servers"

    def test_unsupported_resource_type_raises_error(self):
        """Test that unsupported resource type raises ValueError."""
        handler = UserDefinedLinkHandler()

        with pytest.raises(ValueError) as exc:
            handler._get_collection_for_type("unsupported_type")
        assert "Unsupported resource type for UDL" in str(exc.value)


class TestUserDefinedLinkActions:
    """Tests for user-defined link actions."""

    def test_create_action(self):
        """Test create action is valid."""
        row = UserDefinedLinkRow(
            row_id=1,
            object_type="user_defined_link",
            action="create",
            config="Default",
            udl_name="TestLink",
            source_type="ip4_address",
            source_path="10.0.1.10",
            destination_type="device",
            destination_path="test-device",
        )
        assert row.action == "create"

    def test_delete_action(self):
        """Test delete action is valid."""
        row = UserDefinedLinkRow(
            row_id=1,
            object_type="user_defined_link",
            action="delete",
            config="Default",
            udl_name="TestLink",
            source_type="ip4_address",
            source_path="10.0.1.10",
            destination_type="device",
            destination_path="test-device",
        )
        assert row.action == "delete"

    def test_update_action_is_valid_but_not_supported(self):
        """Test that update action parses but handler rejects it."""
        # The row model accepts update action
        row = UserDefinedLinkRow(
            row_id=1,
            object_type="user_defined_link",
            action="update",
            config="Default",
            udl_name="TestLink",
            source_type="ip4_address",
            source_path="10.0.1.10",
            destination_type="device",
            destination_path="test-device",
        )
        assert row.action == "update"
        # But the handler should reject it at runtime (tested in handler tests)
