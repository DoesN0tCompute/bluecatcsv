"""Tests for DHCP CSV row models."""

import pytest
from pydantic import ValidationError

from src.importer.models.csv_row import (
    DHCPDeploymentRoleRow,
    IPv4DHCPRangeRow,
)


class TestIPv4DHCPRangeRow:
    """Test IPv4DHCPRangeRow model."""

    def test_ipv4_dhcp_range_row_create_valid(self):
        """Test creating a valid IPv4 DHCP range row."""
        row = IPv4DHCPRangeRow(
            row_id=1,
            object_type="ipv4_dhcp_range",
            action="create",
            name="Corporate Network DHCP",
            config="Default",
            range="10.1.1.100-10.1.1.200",
            network_id=123,
            split_around_static_addresses=True,
            low_water_mark=20,
            high_water_mark=80,
        )

        assert row.row_id == 1
        assert row.object_type == "ipv4_dhcp_range"
        assert row.action == "create"
        assert row.name == "Corporate Network DHCP"
        assert row.range == "10.1.1.100-10.1.1.200"
        assert row.network_id == 123
        assert row.split_around_static_addresses is True
        assert row.low_water_mark == 20
        assert row.high_water_mark == 80

    def test_ipv4_dhcp_range_row_update_valid(self):
        """Test updating an IPv4 DHCP range row."""
        row = IPv4DHCPRangeRow(
            row_id=1,
            object_type="ipv4_dhcp_range",
            action="update",
            resource_id=456,
            name="Updated DHCP Range",
            low_water_mark=30,
        )

        assert row.action == "update"
        assert row.resource_id == 456
        assert row.name == "Updated DHCP Range"

    def test_ipv4_dhcp_range_row_delete_valid(self):
        """Test deleting an IPv4 DHCP range row."""
        row = IPv4DHCPRangeRow(
            row_id=1,
            object_type="ipv4_dhcp_range",
            action="delete",
            resource_id=789,
        )

        assert row.action == "delete"
        assert row.resource_id == 789

    def test_ipv4_dhcp_range_invalid_range_format(self):
        """Test invalid DHCP range format raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            IPv4DHCPRangeRow(
                row_id=1,
                object_type="ipv4_dhcp_range",
                action="create",
                range="invalid-range",
            )

        assert "Invalid DHCP range format" in str(exc_info.value)

    def test_ipv4_dhcp_range_invalid_watermark(self):
        """Test invalid watermark values raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            IPv4DHCPRangeRow(
                row_id=1,
                object_type="ipv4_dhcp_range",
                action="create",
                low_water_mark=150,  # Invalid: > 100
            )

        assert "Watermark must be between 0-100" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            IPv4DHCPRangeRow(
                row_id=1,
                object_type="ipv4_dhcp_range",
                action="create",
                high_water_mark=-10,  # Invalid: < 0
            )

        assert "Watermark must be between 0-100" in str(exc_info.value)


class TestDHCPDeploymentRoleRow:
    """Test DHCPDeploymentRoleRow model."""

    def test_dhcp_deployment_role_row_create_valid(self):
        """Test creating a valid DHCP deployment role row."""
        row = DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            name="Primary DHCP Server",
            config="Default",
            role_type="PRIMARY",
            server_group="DHCP-Servers",
        )

        assert row.row_id == 1
        assert row.object_type == "dhcp_deployment_role"
        assert row.name == "Primary DHCP Server"
        assert row.role_type == "PRIMARY"
        assert row.server_group == "DHCP-Servers"

    def test_deployment_role_case_insensitive(self):
        """Test role type is case insensitive and normalized."""
        row = DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            role_type="secondary",  # Lower case input
        )

        assert row.role_type == "SECONDARY"

    def test_dhcp_deployment_role_invalid_type(self):
        """Test invalid deployment role type raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            DHCPDeploymentRoleRow(
                row_id=1,
                object_type="dhcp_deployment_role",
                action="create",
                role_type="INVALID",
            )

        assert "Invalid role type" in str(exc_info.value)
        assert "PRIMARY, SECONDARY, ACTIVE, PASSIVE, NONE" in str(exc_info.value)
