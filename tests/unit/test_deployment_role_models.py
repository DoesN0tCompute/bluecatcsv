"""Tests for DHCP and DNS deployment role CSV row models."""

import pytest
from pydantic import ValidationError

from src.importer.models.csv_row import (
    DHCPDeploymentRoleRow,
    DHCPv4ClientDeploymentOptionRow,
    DHCPv4ServiceDeploymentOptionRow,
    DNSDeploymentRoleRow,
)


class TestDHCPDeploymentRoleRow:
    """Test DHCP deployment role CSV row model."""

    def test_valid_dhcp_deployment_role_minimal(self):
        """Test DHCP deployment role with minimal required fields."""
        row = DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            name="Test DHCP Role",
        )

        assert row.row_id == 1
        assert row.object_type == "dhcp_deployment_role"
        assert row.name == "Test DHCP Role"
        assert row.config is None
        assert row.network_path is None
        assert row.role_type is None
        assert row.server_group is None

    def test_valid_dhcp_deployment_role_full(self):
        """Test DHCP deployment role with all fields."""
        row = DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            name="Primary DHCP Role",
            config="Default",
            network_path="192.168.1.0/24",
            role_type="PRIMARY",
            server_group="DHCP-Servers",
            server_group_id=123,
        )

        assert row.name == "Primary DHCP Role"
        assert row.config == "Default"
        assert row.network_path == "192.168.1.0/24"
        assert row.role_type == "PRIMARY"
        assert row.server_group == "DHCP-Servers"
        assert row.server_group_id == 123

    def test_role_type_validation_valid_values(self):
        """Test role type validation with valid values."""
        valid_types = ["PRIMARY", "SECONDARY", "ACTIVE", "PASSIVE", "NONE"]

        for role_type in valid_types:
            row = DHCPDeploymentRoleRow(
                row_id=1,
                object_type="dhcp_deployment_role",
                action="create",
                name="Test Role",
                role_type=role_type,
            )
            assert row.role_type == role_type

    def test_role_type_validation_invalid_values(self):
        """Test role type validation rejects invalid values."""
        invalid_types = ["INVALID", "MASTER", "BACKUP"]

        for role_type in invalid_types:
            with pytest.raises(ValidationError) as exc_info:
                DHCPDeploymentRoleRow(
                    row_id=1,
                    object_type="dhcp_deployment_role",
                    action="create",
                    name="Test Role",
                    role_type=role_type,
                )
            assert "Invalid role type" in str(exc_info.value)

    def test_role_type_case_insensitive(self):
        """Test role type validation is case insensitive and converts to uppercase."""
        row = DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            name="Test Role",
            role_type="primary",  # lowercase input
        )
        assert row.role_type == "PRIMARY"  # converted to uppercase

    def test_whitespace_stripping(self):
        """Test whitespace stripping from string fields."""
        row = DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            name="  Test Role  ",
            config="  Default  ",
            network_path=" 192.168.1.0/24  ",
            role_type="  PRIMARY  ",
            server_group="  DHCP-Servers  ",
        )

        assert row.name == "Test Role"
        assert row.config == "Default"
        assert row.network_path == "192.168.1.0/24"
        assert row.role_type == "PRIMARY"
        assert row.server_group == "DHCP-Servers"

    def test_udf_fields_support(self):
        """Test user-defined fields are supported."""
        row = DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            name="Test Role",
            udf_environment="production",
            udf_owner="infrastructure-team",
            udf_cost_center="IT-001",
        )

        udf_fields = row.get_udf_fields()
        assert len(udf_fields) == 3
        assert udf_fields["udf_environment"] == "production"
        assert udf_fields["udf_owner"] == "infrastructure-team"
        assert udf_fields["udf_cost_center"] == "IT-001"


class TestDNSDeploymentRoleRow:
    """Test DNS deployment role CSV row model."""

    def test_valid_dns_deployment_role_minimal(self):
        """Test DNS deployment role with minimal required fields."""
        row = DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            name="Test DNS Role",
            zone_path="Internal/test.com",  # DNS roles require a parent path
        )

        assert row.row_id == 1
        assert row.object_type == "dns_deployment_role"
        assert row.name == "Test DNS Role"
        assert row.config is None
        assert row.zone_path == "Internal/test.com"
        assert row.network_path is None
        assert row.block_path is None
        assert row.role_type is None
        assert row.interfaces is None
        assert row.ns_record_ttl is None

    def test_zone_level_dns_deployment_role(self):
        """Test zone-level DNS deployment role."""
        row = DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            name="Zone DNS Role",
            config="Default",
            zone_path="Internal/example.com",
            role_type="PRIMARY",
            interfaces="server1:interface1|server2:interface2",
            ns_record_ttl=3600,
        )

        assert row.zone_path == "Internal/example.com"
        assert row.network_path is None
        assert row.block_path is None
        assert row.role_type == "PRIMARY"
        assert row.interfaces == "server1:interface1|server2:interface2"
        assert row.ns_record_ttl == 3600

    def test_network_level_dns_deployment_role(self):
        """Test network-level DNS deployment role."""
        row = DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            name="Network DNS Role",
            config="Default",
            network_path="192.168.40.0/24",
            role_type="SECONDARY",
            interfaces="server3:interface5",
            ns_record_ttl=1800,
        )

        assert row.zone_path is None
        assert row.network_path == "192.168.40.0/24"
        assert row.block_path is None
        assert row.role_type == "SECONDARY"
        assert row.interfaces == "server3:interface5"
        assert row.ns_record_ttl == 1800

    def test_block_level_dns_deployment_role(self):
        """Test block-level DNS deployment role."""
        row = DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            name="Block DNS Role",
            config="Default",
            block_path="/IPv4/10.0.0.0/8",
            role_type="STUB",
            interfaces="server4:interface10|server5:interface15",
        )

        assert row.zone_path is None
        assert row.network_path is None
        assert row.block_path == "/IPv4/10.0.0.0/8"
        assert row.role_type == "STUB"
        assert row.interfaces == "server4:interface10|server5:interface15"

    def test_dns_role_type_validation_valid_values(self):
        """Test DNS role type validation with valid values."""
        valid_types = [
            "PRIMARY",
            "MULTI_PRIMARY",
            "HIDDEN_PRIMARY",
            "HIDDEN_MULTI_PRIMARY",
            "SECONDARY",
            "STEALTH_SECONDARY",
            "FORWARDING",
            "STUB",
            "RECURSIVE",
            "NONE",
        ]

        for role_type in valid_types:
            row = DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="create",
                name="Test Role",
                zone_path="Internal/test.com",  # Required parent path
                role_type=role_type,
            )
            assert row.role_type == role_type

    def test_dns_role_type_validation_invalid_values(self):
        """Test DNS role type validation rejects invalid values."""
        invalid_types = ["INVALID", "MASTER", "SLAVE"]

        for role_type in invalid_types:
            with pytest.raises(ValidationError) as exc_info:
                DNSDeploymentRoleRow(
                    row_id=1,
                    object_type="dns_deployment_role",
                    action="create",
                    name="Test Role",
                    zone_path="Internal/test.com",  # Required parent path
                    role_type=role_type,
                )
            assert "Invalid DNS deployment role type" in str(exc_info.value)

    def test_interfaces_validation_server_interface_format(self):
        """Test interfaces validation with server:interface format."""
        # Valid interfaces
        valid_interfaces = [
            "server1:interface1",
            "server1:interface1|server2:interface2",
            "ns1.example.com:eth0|ns2.example.com:eth1",
        ]

        for interfaces in valid_interfaces:
            row = DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="create",
                name="Test Role",
                zone_path="Internal/test.com",  # Required parent path
                interfaces=interfaces,
            )
            assert row.interfaces == interfaces

    def test_interfaces_validation_server_names_only(self):
        """Test interfaces validation with server names only."""
        row = DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            name="Test Role",
            zone_path="Internal/test.com",  # Required parent path
            interfaces="server1|server2|server3",
        )
        assert row.interfaces == "server1|server2|server3"

    def test_interfaces_validation_interface_ids_only(self):
        """Test interfaces validation with interface IDs only."""
        row = DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            name="Test Role",
            zone_path="Internal/test.com",  # Required parent path
            interfaces="4402278|4402274|4402280",
        )
        assert row.interfaces == "4402278|4402274|4402280"

    def test_interfaces_validation_filters_invalid_format(self):
        """Test interfaces validation filters out invalid formats."""
        # Test that empty or invalid interfaces get filtered out
        row = DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            name="Test Role",
            zone_path="Internal/test.com",  # Required parent path
            interfaces="server1:interface1||server2:interface2",  # Double pipe creates empty interface
        )
        # Empty interface should be filtered out
        assert row.interfaces == "server1:interface1|server2:interface2"


class TestDHCPv4ClientDeploymentOptionRow:
    """Test DHCPv4 client deployment option CSV row model."""

    def test_valid_dhcp_client_option_minimal(self):
        """Test DHCP client option with minimal required fields."""
        row = DHCPv4ClientDeploymentOptionRow(
            row_id=1,
            object_type="dhcpv4_client_deployment_option",
            action="create",
            name="DNS Servers",
            code=6,
            value="8.8.8.8,8.8.4.4",
        )

        assert row.row_id == 1
        assert row.object_type == "dhcpv4_client_deployment_option"
        assert row.name == "DNS Servers"
        assert row.code == 6
        assert row.value == "8.8.8.8,8.8.4.4"
        assert row.config is None
        assert row.network_path is None
        assert row.server_scope is None

    def test_valid_dhcp_client_option_full(self):
        """Test DHCP client option with all fields."""
        row = DHCPv4ClientDeploymentOptionRow(
            row_id=1,
            object_type="dhcpv4_client_deployment_option",
            action="create",
            name="Domain Name",
            config="Default",
            network_path="192.168.1.0/24",
            code=15,
            value="example.com",
            server_scope="DHCP_SERVER",
        )

        assert row.config == "Default"
        assert row.network_path == "192.168.1.0/24"
        assert row.code == 15
        assert row.value == "example.com"
        assert row.server_scope == "DHCP_SERVER"

    def test_dhcp_option_code_validation_valid_range(self):
        """Test DHCP option code validation with valid range."""
        for code in [1, 6, 15, 51, 254]:  # min, common, max values
            row = DHCPv4ClientDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_client_deployment_option",
                action="create",
                name="Test Option",
                code=code,
                value="test",
            )
            assert row.code == code

    def test_dhcp_option_code_validation_invalid_range(self):
        """Test DHCP option code validation rejects invalid codes."""
        invalid_codes = [0, -1, 255, 300, 1000]

        for code in invalid_codes:
            with pytest.raises(ValidationError) as exc_info:
                DHCPv4ClientDeploymentOptionRow(
                    row_id=1,
                    object_type="dhcpv4_client_deployment_option",
                    action="create",
                    name="Invalid Option",
                    code=code,
                    value="test",
                )
            assert "DHCP option code must be between 1 and 254" in str(exc_info.value)


class TestDHCPv4ServiceDeploymentOptionRow:
    """Test DHCPv4 service deployment option CSV row model."""

    def test_valid_dhcp_service_option_minimal(self):
        """Test DHCP service option with minimal required fields."""
        row = DHCPv4ServiceDeploymentOptionRow(
            row_id=1,
            object_type="dhcpv4_service_deployment_option",
            action="create",
            name="Default Lease Time",
            code=51,
            value="86400",
        )

        assert row.row_id == 1
        assert row.object_type == "dhcpv4_service_deployment_option"
        assert row.name == "Default Lease Time"
        assert row.code == 51
        assert row.value == "86400"

    def test_server_scope_validation_valid_values(self):
        """Test server scope validation with valid values."""
        valid_scopes = ["DHCP_SERVER", "ALL_SERVERS"]

        for scope in valid_scopes:
            row = DHCPv4ServiceDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_service_deployment_option",
                action="create",
                name="Test Option",
                code=6,
                value="test",
                server_scope=scope,
            )
            assert row.server_scope == scope

    def test_server_scope_validation_case_insensitive(self):
        """Test server scope validation is case insensitive and converts to uppercase."""
        row = DHCPv4ServiceDeploymentOptionRow(
            row_id=1,
            object_type="dhcpv4_service_deployment_option",
            action="create",
            name="Test Option",
            code=6,
            value="test",
            server_scope="dhcp_server",  # lowercase input
        )
        assert row.server_scope == "DHCP_SERVER"  # converted to uppercase

    def test_both_deployment_options_inherit_csv_base(self):
        """Test both deployment option types inherit CSV base functionality."""
        # Test client option
        client_row = DHCPv4ClientDeploymentOptionRow(
            row_id=1,
            object_type="dhcpv4_client_deployment_option",
            action="update",
            bam_id=123,
            name="Test",
            code=6,
            value="test",
        )

        # Test service option
        service_row = DHCPv4ServiceDeploymentOptionRow(
            row_id=2,
            object_type="dhcpv4_service_deployment_option",
            action="delete",
            bam_id=456,
            name="Test",
            code=51,
            value="test",
        )

        # Both should have base CSV row fields
        assert client_row.row_id == 1
        assert client_row.action == "update"
        assert client_row.bam_id == 123

        assert service_row.row_id == 2
        assert service_row.action == "delete"
        assert service_row.bam_id == 456

        # Both should support UDFs
        client_row.udf_test_field = "test_value"
        service_row.udf_another_field = "another_value"

        assert client_row.get_udf_fields()["udf_test_field"] == "test_value"
        assert service_row.get_udf_fields()["udf_another_field"] == "another_value"
