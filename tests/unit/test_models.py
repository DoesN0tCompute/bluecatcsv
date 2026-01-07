"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from src.importer.models.csv_row import (
    DHCPv4ClientDeploymentOptionRow,
    DHCPv4ServiceDeploymentOptionRow,
    DNSDeploymentRoleRow,
    HostRecordRow,
    IP4AddressRow,
    IP4NetworkRow,
)


def test_ip4_address_row_validation() -> None:
    """Test IP4AddressRow validation."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.5",
        name="server1",
        mac="00:11:22:33:44:55",
    )

    assert row.row_id == 1
    assert row.object_type == "ip4_address"
    assert row.address == "10.1.0.5"
    assert row.name == "server1"
    assert row.mac == "00:11:22:33:44:55"


def test_ip4_address_invalid_ip() -> None:
    """Test that invalid IP addresses are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="999.999.999.999",
        )

    assert "Invalid IPv4 address" in str(exc_info.value)


def test_ip4_address_invalid_mac() -> None:
    """Test that invalid MAC addresses are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            mac="invalid-mac",
        )

    assert "Invalid MAC address" in str(exc_info.value)


def test_ip4_network_row_validation() -> None:
    """Test IP4NetworkRow validation."""
    row = IP4NetworkRow(
        row_id=1,
        object_type="ip4_network",
        action="create",
        config="Default",
        parent="/IPv4/10.0.0.0/8",
        cidr="10.1.0.0/16",
        name="Corp-Network",
    )

    assert row.cidr == "10.1.0.0/16"
    assert row.name == "Corp-Network"


def test_ip4_network_invalid_cidr() -> None:
    """Test that invalid CIDR is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        IP4NetworkRow(
            row_id=1,
            object_type="ip4_network",
            action="create",
            config="Default",
            parent="/IPv4",
            cidr="10.0.0.0/99",
            name="BadNet",
        )

    assert "Invalid CIDR" in str(exc_info.value)


def test_host_record_row_validation() -> None:
    """Test HostRecordRow validation."""
    row = HostRecordRow(
        row_id=1,
        object_type="host_record",
        action="create",
        config="Default",
        view_path="Internal",
        name="www.example.com",
        addresses="10.1.0.5|10.1.0.6",
        ttl=3600,
    )

    assert row.name == "www.example.com"
    assert row.addresses == "10.1.0.5|10.1.0.6"
    assert row.get_address_list() == ["10.1.0.5", "10.1.0.6"]
    assert row.ttl == 3600


def test_host_record_invalid_addresses() -> None:
    """Test that invalid addresses in host record are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        HostRecordRow(
            row_id=1,
            object_type="host_record",
            action="create",
            config="Default",
            view_path="Internal",
            name="www.example.com",
            addresses="10.1.0.5|invalid.ip",
        )

    assert "Invalid IP address" in str(exc_info.value)


def test_row_id_can_be_string() -> None:
    """Test that row_id can be either int or string."""
    # Integer row_id
    row1 = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.5",
    )
    assert row1.row_id == 1

    # String row_id
    row2 = IP4AddressRow(
        row_id="row_001",
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.6",
    )
    assert row2.row_id == "row_001"


def test_udf_fields_are_preserved() -> None:
    """Test that user-defined fields are preserved."""
    # Create row with extra UDF fields
    row = IP4AddressRow.model_validate(
        {
            "row_id": 1,
            "object_type": "ip4_address",
            "action": "create",
            "config": "Default",
            "address": "10.1.0.5",
            "udf_owner": "IT",
            "udf_environment": "production",
            "udf_cost_center": "12345",
        }
    )

    # Check UDF fields are accessible
    udf_fields = row.get_udf_fields()
    assert udf_fields["udf_owner"] == "IT"
    assert udf_fields["udf_environment"] == "production"
    assert udf_fields["udf_cost_center"] == "12345"


def test_whitespace_stripping() -> None:
    """Test that whitespace is stripped from string fields."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config=" Default ",
        address=" 10.1.0.5 ",
        name=" server1 ",
    )

    assert row.config == "Default"
    assert row.address == "10.1.0.5"
    assert row.name == "server1"


def test_ip4_address_dhcp_reserved_state() -> None:
    """Test IP4AddressRow with DHCP_RESERVED state."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.100",
        name="dhcp-reserved-server",
        state="DHCP_RESERVED",
    )

    assert row.state == "DHCP_RESERVED"
    assert row.name == "dhcp-reserved-server"


def test_ip4_address_static_state() -> None:
    """Test IP4AddressRow with STATIC state."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.10",
        name="static-server",
        state="STATIC",
    )

    assert row.state == "STATIC"


def test_ip4_address_gateway_state() -> None:
    """Test IP4AddressRow with GATEWAY state."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.1",
        name="gateway",
        state="GATEWAY",
    )

    assert row.state == "GATEWAY"


def test_ip4_address_reserved_state() -> None:
    """Test IP4AddressRow with RESERVED state."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.50",
        name="reserved-server",
        state="RESERVED",
    )

    assert row.state == "RESERVED"


def test_ip4_address_state_case_insensitive() -> None:
    """Test that state validation is case insensitive."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.200",
        state="dhcp_reserved",  # lowercase input
    )

    assert row.state == "DHCP_RESERVED"  # should be normalized to uppercase


def test_ip4_address_invalid_state() -> None:
    """Test that invalid state values are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            state="INVALID_STATE",
        )

    assert "Invalid state" in str(exc_info.value)
    assert "STATIC, RESERVED, DHCP_RESERVED, GATEWAY" in str(exc_info.value)


def test_ip4_address_state_optional() -> None:
    """Test that state is optional and defaults to None."""
    row = IP4AddressRow(
        row_id=1,
        object_type="ip4_address",
        action="create",
        config="Default",
        address="10.1.0.5",
        name="server",
        # state not provided
    )

    assert row.state is None


def test_dns_deployment_role_row_validation() -> None:
    """Test DNSDeploymentRoleRow validation."""
    row = DNSDeploymentRoleRow(
        row_id=1,
        object_type="dns_deployment_role",
        action="create",
        config="Default",
        zone_path="Internal/example.com",
        name="Primary DNS",
        role_type="PRIMARY",
        interfaces="12345:67890|12346:67891",
        ns_record_ttl=3600,
    )

    assert row.row_id == 1
    assert row.object_type == "dns_deployment_role"
    assert row.config == "Default"
    assert row.zone_path == "Internal/example.com"
    assert row.name == "Primary DNS"
    assert row.role_type == "PRIMARY"
    assert row.interfaces == "12345:67890|12346:67891"
    assert row.ns_record_ttl == 3600


def test_dns_deployment_role_interface_parsing() -> None:
    """Test interface parsing functionality."""
    row = DNSDeploymentRoleRow(
        row_id=1,
        object_type="dns_deployment_role",
        action="create",
        config="Default",
        zone_path="Internal/example.com",
        name="Primary DNS",
        role_type="PRIMARY",
        interfaces="12345:67890|12346:67891|12347:67892",
    )

    interfaces = row.get_interface_list()
    assert len(interfaces) == 3
    assert "12345:67890" in interfaces
    assert "12346:67891" in interfaces
    assert "12347:67892" in interfaces


def test_dns_deployment_role_invalid_role_type() -> None:
    """Test that invalid role types are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            config="Default",
            zone_path="Internal/example.com",
            name="Primary DNS",
            role_type="INVALID_ROLE",
            interfaces="12345:67890",
        )

    assert "Invalid DNS deployment role type" in str(exc_info.value)


def test_dns_deployment_role_invalid_interface_format() -> None:
    """Test that invalid interface formats are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            config="Default",
            zone_path="Internal/example.com",
            name="Primary DNS",
            role_type="PRIMARY",
            interfaces="server$1",  # Invalid character
        )

    assert "Invalid interface format" in str(exc_info.value)


def test_dns_deployment_role_server_name_interface() -> None:
    """Test that server names are accepted for interfaces."""
    row = DNSDeploymentRoleRow(
        row_id=1,
        object_type="dns_deployment_role",
        action="create",
        config="Default",
        zone_path="Internal/example.com",
        name="Primary DNS",
        role_type="PRIMARY",
        interfaces="server1|server2|dns-server-01",
    )

    assert row.interfaces == "server1|server2|dns-server-01"
    interfaces = row.get_interface_list()
    assert len(interfaces) == 3
    assert "server1" in interfaces
    assert "server2" in interfaces
    assert "dns-server-01" in interfaces


def test_dns_deployment_role_mixed_interface_formats() -> None:
    """Test that mixed interface formats are accepted."""
    row = DNSDeploymentRoleRow(
        row_id=1,
        object_type="dns_deployment_role",
        action="create",
        config="Default",
        zone_path="Internal/example.com",
        name="Primary DNS",
        role_type="PRIMARY",
        interfaces="12345|server1:eth0|server2",
    )

    assert row.interfaces == "12345|server1:eth0|server2"
    interfaces = row.get_interface_list()
    assert len(interfaces) == 3
    assert "12345" in interfaces
    assert "server1:eth0" in interfaces
    assert "server2" in interfaces


def test_dns_deployment_role_invalid_ttl() -> None:
    """Test that invalid TTL values are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        DNSDeploymentRoleRow(
            row_id=1,
            object_type="dns_deployment_role",
            action="create",
            config="Default",
            zone_path="Internal/example.com",
            name="Primary DNS",
            role_type="PRIMARY",
            interfaces="12345:67890",
            ns_record_ttl=2147483648,  # Exceeds max value
        )

    assert "NS record TTL" in str(exc_info.value)
    assert "exceeds maximum value" in str(exc_info.value)


def test_dns_deployment_role_optional_fields() -> None:
    """Test that optional fields can be omitted."""
    row = DNSDeploymentRoleRow(
        row_id=1,
        object_type="dns_deployment_role",
        action="create",
        config="Default",
        zone_path="Internal/example.com",
        name="Primary DNS",
        role_type="SECONDARY",
        interfaces="12345:67890",
        # ns_record_ttl omitted
    )

    assert row.ns_record_ttl is None
    assert row.get_interface_list() == ["12345:67890"]


def test_dns_deployment_role_whitespace_stripping() -> None:
    """Test that whitespace is properly stripped from fields."""
    row = DNSDeploymentRoleRow(
        row_id=1,
        object_type="dns_deployment_role",
        action="create",
        config="  Default  ",
        zone_path="  Internal/example.com  ",
        name="  Primary DNS  ",
        role_type="  PRIMARY  ",
        interfaces="  12345:67890  |  12346:67891  ",
        ns_record_ttl=3600,
    )

    assert row.config == "Default"
    assert row.zone_path == "Internal/example.com"
    assert row.name == "Primary DNS"
    assert row.role_type == "PRIMARY"
    assert row.interfaces == "12345:67890|12346:67891"


def test_dns_deployment_role_role_type_case_insensitive() -> None:
    """Test that role types are converted to uppercase."""
    row = DNSDeploymentRoleRow(
        row_id=1,
        object_type="dns_deployment_role",
        action="create",
        config="Default",
        zone_path="Internal/example.com",
        name="Primary DNS",
        role_type="primary",  # lowercase
        interfaces="12345:67890",
    )

    assert row.role_type == "PRIMARY"  # Should be converted to uppercase


def test_dhcpv4_client_deployment_option_validation() -> None:
    """Test DHCPv4ClientDeploymentOptionRow validation."""
    row = DHCPv4ClientDeploymentOptionRow(
        row_id=1,
        object_type="dhcpv4_client_deployment_option",
        action="create",
        config="Default",
        network_path="/IPv4/10.0.0.0/8/10.1.0.0/24",
        name="DNS Servers",
        code=6,
        value="8.8.8.8,8.8.4.4",
        server_scope="DHCP_SERVER",
    )

    assert row.row_id == 1
    assert row.object_type == "dhcpv4_client_deployment_option"
    assert row.config == "Default"
    assert row.network_path == "/IPv4/10.0.0.0/8/10.1.0.0/24"
    assert row.name == "DNS Servers"
    assert row.code == 6
    assert row.value == "8.8.8.8,8.8.4.4"
    assert row.server_scope == "DHCP_SERVER"


def test_dhcpv4_client_deployment_option_invalid_code() -> None:
    """Test that invalid DHCP option codes are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        DHCPv4ClientDeploymentOptionRow(
            row_id=1,
            object_type="dhcpv4_client_deployment_option",
            action="create",
            config="Default",
            network_path="/IPv4/10.0.0.0/8/10.1.0.0/24",
            name="Invalid Option",
            code=300,  # Invalid code (> 254)
            value="test",
        )

    assert "DHCP option code must be between 1 and 254" in str(exc_info.value)


def test_dhcpv4_client_deployment_option_invalid_server_scope() -> None:
    """Test that invalid server scopes are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        DHCPv4ClientDeploymentOptionRow(
            row_id=1,
            object_type="dhcpv4_client_deployment_option",
            action="create",
            config="Default",
            network_path="/IPv4/10.0.0.0/8/10.1.0.0/24",
            name="Invalid Scope",
            code=6,
            value="8.8.8.8",
            server_scope="INVALID_SCOPE",  # Invalid scope
        )

    assert "Invalid server scope: INVALID_SCOPE" in str(exc_info.value)


def test_dhcpv4_service_deployment_option_validation() -> None:
    """Test DHCPv4ServiceDeploymentOptionRow validation."""
    row = DHCPv4ServiceDeploymentOptionRow(
        row_id=1,
        object_type="dhcpv4_service_deployment_option",
        action="create",
        config="Default",
        network_path="/IPv4/10.0.0.0/8/10.1.0.0/24",
        name="Default Lease Time",
        code=51,
        value="86400",
        server_scope="DHCP_SERVER",
    )

    assert row.row_id == 1
    assert row.object_type == "dhcpv4_service_deployment_option"
    assert row.config == "Default"
    assert row.network_path == "/IPv4/10.0.0.0/8/10.1.0.0/24"
    assert row.name == "Default Lease Time"
    assert row.code == 51
    assert row.value == "86400"
    assert row.server_scope == "DHCP_SERVER"


def test_dhcpv4_service_deployment_option_minimal_fields() -> None:
    """Test DHCPv4ServiceDeploymentOptionRow with minimal required fields."""
    row = DHCPv4ServiceDeploymentOptionRow(
        row_id=2,
        object_type="dhcpv4_service_deployment_option",
        action="create",
        name="Domain Name",
        code=15,
        value="example.com",
        config="Default",
    )

    assert row.row_id == 2
    assert row.object_type == "dhcpv4_service_deployment_option"
    assert row.name == "Domain Name"
    assert row.code == 15
    assert row.value == "example.com"
    assert row.config == "Default"
    assert row.network_path is None
    assert row.server_scope is None


def test_dhcpv4_client_deployment_option_whitespace_stripping() -> None:
    """Test that whitespace is stripped from string fields."""
    row = DHCPv4ClientDeploymentOptionRow(
        row_id=1,
        object_type="dhcpv4_client_deployment_option",
        action="create",
        config="  Default  ",
        network_path="  /IPv4/10.0.0.0/8/10.1.0.0/24  ",
        name="  DNS Servers  ",
        code=6,
        value="  8.8.8.8,8.8.4.4  ",
        server_scope="  dhcp_server  ",
    )

    assert row.config == "Default"
    assert row.network_path == "/IPv4/10.0.0.0/8/10.1.0.0/24"
    assert row.name == "DNS Servers"
    assert row.value == "8.8.8.8,8.8.4.4"
    assert row.server_scope == "DHCP_SERVER"  # Should be uppercase


def test_dhcpv4_service_deployment_option_boundary_codes() -> None:
    """Test DHCP option codes at boundaries."""
    # Test minimum valid code
    row_min = DHCPv4ServiceDeploymentOptionRow(
        row_id=1,
        object_type="dhcpv4_service_deployment_option",
        action="create",
        name="Min Code",
        code=1,  # Minimum valid code
        value="test",
        config="Default",
    )
    assert row_min.code == 1

    # Test maximum valid code
    row_max = DHCPv4ServiceDeploymentOptionRow(
        row_id=2,
        object_type="dhcpv4_service_deployment_option",
        action="create",
        name="Max Code",
        code=254,  # Maximum valid code
        value="test",
        config="Default",
    )
    assert row_max.code == 254

    # Test invalid code below minimum
    with pytest.raises(ValidationError) as exc_info:
        DHCPv4ServiceDeploymentOptionRow(
            row_id=3,
            object_type="dhcpv4_service_deployment_option",
            action="create",
            name="Invalid Min Code",
            code=0,  # Invalid code (< 1)
            value="test",
            config="Default",
        )
    assert "DHCP option code must be between 1 and 254" in str(exc_info.value)
