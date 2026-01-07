"""Tests for type-safe Pydantic API payload models.

These tests verify that payload models properly validate inputs
and generate correct API payloads (Fix 4.1).
"""

import pytest
from importer.models.payloads import (
    AddressObject,
    AliasRecordPayload,
    DHCPDeploymentRolePayload,
    DHCPv4ClientOptionPayload,
    DHCPv4ServiceOptionPayload,
    DNSDeploymentRolePayload,
    ExternalHostRecordPayload,
    HostRecordPayload,
    InterfaceRef,
    IPv4AddressPayload,
    IPv4BlockPayload,
    IPv4NetworkPayload,
    LinkedRecordRef,
    MACAddressPayload,
    MXRecordPayload,
    SRVRecordPayload,
    TXTRecordPayload,
    ViewRef,
    ZonePayload,
)
from pydantic import ValidationError


class TestIPv4BlockPayload:
    """Tests for IPv4BlockPayload."""

    def test_valid_payload(self) -> None:
        """Test creating a valid block payload."""
        payload = IPv4BlockPayload(name="Test Block", range="10.0.0.0/8")

        assert payload.type == "IPv4Block"
        assert payload.name == "Test Block"
        assert payload.range == "10.0.0.0/8"

    def test_model_dump(self) -> None:
        """Test payload serialization."""
        payload = IPv4BlockPayload(
            name="Test Block",
            range="10.0.0.0/8",
            properties={"key": "value"},
        )

        data = payload.model_dump(exclude_none=True)
        assert data["type"] == "IPv4Block"
        assert data["name"] == "Test Block"
        assert data["range"] == "10.0.0.0/8"
        assert data["properties"] == {"key": "value"}

    def test_invalid_cidr_format(self) -> None:
        """Test that invalid CIDR raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            IPv4BlockPayload(name="Test", range="invalid-cidr")

        assert "Invalid CIDR notation" in str(exc_info.value)

    def test_empty_name_rejected(self) -> None:
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError):
            IPv4BlockPayload(name="", range="10.0.0.0/8")


class TestIPv4NetworkPayload:
    """Tests for IPv4NetworkPayload."""

    def test_valid_payload(self) -> None:
        """Test creating a valid network payload."""
        payload = IPv4NetworkPayload(name="Test Network", range="10.1.0.0/24")

        assert payload.type == "IPv4Network"
        assert payload.name == "Test Network"
        assert payload.range == "10.1.0.0/24"

    def test_invalid_cidr_rejected(self) -> None:
        """Test that invalid CIDR is rejected."""
        with pytest.raises(ValidationError):
            IPv4NetworkPayload(name="Test", range="not-a-cidr")


class TestIPv4AddressPayload:
    """Tests for IPv4AddressPayload."""

    def test_valid_static_address(self) -> None:
        """Test creating a valid static address."""
        payload = IPv4AddressPayload(
            address="10.1.0.10",
            state="STATIC",
            name="Server 1",
        )

        assert payload.type == "IPv4Address"
        assert payload.address == "10.1.0.10"
        assert payload.state == "STATIC"

    def test_valid_dhcp_reserved(self) -> None:
        """Test DHCP_RESERVED state."""
        mac = MACAddressPayload(address="00:11:22:33:44:55")
        payload = IPv4AddressPayload(
            address="10.1.0.20",
            state="DHCP_RESERVED",
            macAddress=mac,
        )

        assert payload.state == "DHCP_RESERVED"
        assert payload.macAddress is not None

    def test_invalid_address_rejected(self) -> None:
        """Test that invalid IP address is rejected."""
        with pytest.raises(ValidationError):
            IPv4AddressPayload(address="not-an-ip", state="STATIC")

    def test_invalid_state_rejected(self) -> None:
        """Test that invalid state is rejected."""
        with pytest.raises(ValidationError):
            IPv4AddressPayload(address="10.1.0.10", state="INVALID_STATE")


class TestMACAddressPayload:
    """Tests for MACAddressPayload."""

    def test_valid_mac_colon_format(self) -> None:
        """Test MAC address with colon separators."""
        mac = MACAddressPayload(address="00:11:22:33:44:55")
        assert mac.address == "00-11-22-33-44-55"  # Normalized to BAM format

    def test_valid_mac_dash_format(self) -> None:
        """Test MAC address with dash separators."""
        mac = MACAddressPayload(address="00-11-22-33-44-55")
        assert mac.address == "00-11-22-33-44-55"

    def test_valid_mac_no_separator(self) -> None:
        """Test MAC address without separators."""
        mac = MACAddressPayload(address="001122334455")
        assert mac.address == "00-11-22-33-44-55"

    def test_invalid_mac_rejected(self) -> None:
        """Test that invalid MAC is rejected."""
        with pytest.raises(ValidationError):
            MACAddressPayload(address="invalid-mac")


class TestZonePayload:
    """Tests for ZonePayload."""

    def test_valid_zone(self) -> None:
        """Test creating a valid zone payload."""
        payload = ZonePayload(absoluteName="example.com")

        assert payload.type == "Zone"
        assert payload.absoluteName == "example.com"

    def test_empty_name_rejected(self) -> None:
        """Test that empty name is rejected."""
        with pytest.raises(ValidationError):
            ZonePayload(absoluteName="")


class TestHostRecordPayload:
    """Tests for HostRecordPayload."""

    def test_valid_host_record(self) -> None:
        """Test creating a valid host record."""
        addresses = [AddressObject(type="IPv4Address", address="10.1.0.10")]
        payload = HostRecordPayload(
            name="www",
            addresses=addresses,
            ttl=3600,
        )

        assert payload.type == "HostRecord"
        assert payload.name == "www"
        assert len(payload.addresses) == 1

    def test_multiple_addresses(self) -> None:
        """Test host record with multiple addresses."""
        addresses = [
            AddressObject(type="IPv4Address", address="10.1.0.10"),
            AddressObject(type="IPv4Address", address="10.1.0.11"),
        ]
        payload = HostRecordPayload(name="multi", addresses=addresses)

        assert len(payload.addresses) == 2

    def test_empty_addresses_rejected(self) -> None:
        """Test that empty address list is rejected."""
        with pytest.raises(ValidationError):
            HostRecordPayload(name="test", addresses=[])


class TestAliasRecordPayload:
    """Tests for AliasRecordPayload (CNAME)."""

    def test_valid_alias(self) -> None:
        """Test creating a valid alias record."""
        linked = LinkedRecordRef(absoluteName="www.example.com")
        payload = AliasRecordPayload(
            name="alias",
            linkedRecord=linked,
        )

        assert payload.type == "AliasRecord"
        assert payload.linkedRecord.absoluteName == "www.example.com"


class TestMXRecordPayload:
    """Tests for MXRecordPayload."""

    def test_valid_mx_record(self) -> None:
        """Test creating a valid MX record."""
        linked = LinkedRecordRef(absoluteName="mail.example.com")
        payload = MXRecordPayload(
            name="@",
            linkedRecord=linked,
            priority=10,
        )

        assert payload.type == "MXRecord"
        assert payload.priority == 10

    def test_negative_priority_rejected(self) -> None:
        """Test that negative priority is rejected."""
        linked = LinkedRecordRef(absoluteName="mail.example.com")
        with pytest.raises(ValidationError):
            MXRecordPayload(name="@", linkedRecord=linked, priority=-1)


class TestTXTRecordPayload:
    """Tests for TXTRecordPayload."""

    def test_valid_txt_record(self) -> None:
        """Test creating a valid TXT record."""
        payload = TXTRecordPayload(
            name="@",
            text="v=spf1 include:_spf.example.com ~all",
        )

        assert payload.type == "TXTRecord"
        assert "spf1" in payload.text


class TestSRVRecordPayload:
    """Tests for SRVRecordPayload."""

    def test_valid_srv_record(self) -> None:
        """Test creating a valid SRV record."""
        linked = LinkedRecordRef(absoluteName="sip.example.com")
        payload = SRVRecordPayload(
            name="_sip._tcp",
            linkedRecord=linked,
            priority=10,
            weight=5,
            port=5060,
        )

        assert payload.type == "SRVRecord"
        assert payload.port == 5060

    def test_invalid_port_rejected(self) -> None:
        """Test that port > 65535 is rejected."""
        linked = LinkedRecordRef(absoluteName="sip.example.com")
        with pytest.raises(ValidationError):
            SRVRecordPayload(
                name="_sip._tcp",
                linkedRecord=linked,
                priority=10,
                weight=5,
                port=99999,
            )


class TestExternalHostRecordPayload:
    """Tests for ExternalHostRecordPayload."""

    def test_valid_external_host(self) -> None:
        """Test creating a valid external host record."""
        view = ViewRef(id=123)
        payload = ExternalHostRecordPayload(
            name="external.example.com",
            view=view,
        )

        assert payload.type == "ExternalHostRecord"
        assert payload.view.id == 123


class TestGenericRecordPayload:
    """Tests for GenericRecordPayload."""

    def test_valid_sshfp_record(self) -> None:
        """Test creating a valid SSHFP generic record."""
        from importer.models.payloads import GenericRecordPayload

        payload = GenericRecordPayload(
            name="server1",
            recordType="SSHFP",
            rdata="2 1 123456789abcdef67890123456789abcdef67890",
        )

        assert payload.type == "GenericRecord"
        assert payload.recordType == "SSHFP"
        assert payload.rdata == "2 1 123456789abcdef67890123456789abcdef67890"

    def test_valid_caa_record(self) -> None:
        """Test creating a valid CAA generic record."""
        from importer.models.payloads import GenericRecordPayload

        payload = GenericRecordPayload(
            name="@",
            recordType="CAA",
            rdata="0 issue letsencrypt.org",
            ttl=3600,
        )

        assert payload.type == "GenericRecord"
        assert payload.recordType == "CAA"
        assert payload.ttl == 3600

    def test_valid_tlsa_record(self) -> None:
        """Test creating a valid TLSA generic record."""
        from importer.models.payloads import GenericRecordPayload

        payload = GenericRecordPayload(
            name="_443._tcp.www",
            recordType="TLSA",
            rdata="3 1 1 abcdef123456789",
        )

        assert payload.type == "GenericRecord"
        assert payload.recordType == "TLSA"

    def test_record_type_uppercase(self) -> None:
        """Test that record type is converted to uppercase."""
        from importer.models.payloads import GenericRecordPayload

        payload = GenericRecordPayload(
            name="test",
            recordType="sshfp",
            rdata="2 1 abc123",
        )

        assert payload.recordType == "SSHFP"

    def test_invalid_record_type(self) -> None:
        """Test that invalid record type raises ValidationError."""
        from importer.models.payloads import GenericRecordPayload

        with pytest.raises(ValidationError) as exc_info:
            GenericRecordPayload(
                name="test",
                recordType="INVALID",
                rdata="some data",
            )

        assert "Invalid record type" in str(exc_info.value)

    def test_empty_rdata_rejected(self) -> None:
        """Test that empty rdata is rejected."""
        from importer.models.payloads import GenericRecordPayload

        with pytest.raises(ValidationError):
            GenericRecordPayload(
                name="test",
                recordType="SSHFP",
                rdata="",
            )

    def test_model_dump(self) -> None:
        """Test payload serialization."""
        from importer.models.payloads import GenericRecordPayload

        payload = GenericRecordPayload(
            name="server1",
            recordType="SSHFP",
            rdata="2 1 abc123",
            ttl=3600,
            comment="SSH fingerprint",
        )

        data = payload.model_dump(exclude_none=True)
        assert data["type"] == "GenericRecord"
        assert data["name"] == "server1"
        assert data["recordType"] == "SSHFP"
        assert data["rdata"] == "2 1 abc123"
        assert data["ttl"] == 3600
        assert data["comment"] == "SSH fingerprint"


class TestDeploymentRolePayloads:
    """Tests for deployment role payloads."""

    def test_dhcp_deployment_role(self) -> None:
        """Test DHCP deployment role payload."""
        interfaces = [InterfaceRef(id=100)]
        payload = DHCPDeploymentRolePayload(
            roleType="MASTER",
            interfaces=interfaces,
        )

        assert payload.type == "DHCPDeploymentRole"
        assert payload.roleType == "MASTER"

    def test_dns_deployment_role(self) -> None:
        """Test DNS deployment role payload."""
        interfaces = [InterfaceRef(id=200)]
        payload = DNSDeploymentRolePayload(
            roleType="PRIMARY",
            interfaces=interfaces,
        )

        assert payload.type == "DNSDeploymentRole"


class TestDeploymentOptionPayloads:
    """Tests for deployment option payloads."""

    def test_dhcpv4_client_option(self) -> None:
        """Test DHCPv4 client option payload."""
        payload = DHCPv4ClientOptionPayload(
            name="domain-name-servers",
            code=6,
            value="8.8.8.8,8.8.4.4",
        )

        assert payload.type == "DHCPv4ClientOption"
        assert payload.code == 6

    def test_invalid_option_code_rejected(self) -> None:
        """Test that option code > 254 is rejected."""
        with pytest.raises(ValidationError):
            DHCPv4ClientOptionPayload(
                name="test",
                code=300,
                value="test",
            )

    def test_dhcpv4_client_option_json_types(self) -> None:
        """Test that DHCP options accept valid JSON types (list, int, bool)."""
        # Test List
        payload_list = DHCPv4ClientOptionPayload(
            name="dns-servers",
            code=6,
            value=["8.8.8.8", "8.8.4.4"],
        )
        assert isinstance(payload_list.value, list)
        assert payload_list.value == ["8.8.8.8", "8.8.4.4"]

        # Test Integer
        payload_int = DHCPv4ClientOptionPayload(
            name="time-offset",
            code=2,
            value=0,
        )
        assert isinstance(payload_int.value, int)
        assert payload_int.value == 0

        # Test Boolean
        payload_bool = DHCPv4ClientOptionPayload(
            name="ip-forwarding",
            code=19,
            value=False,
        )
        assert isinstance(payload_bool.value, bool)
        assert payload_bool.value is False

    def test_invalid_server_scope_rejected(self) -> None:
        """Test that invalid server scope is rejected."""
        with pytest.raises(ValidationError):
            DHCPv4ClientOptionPayload(
                name="test",
                code=6,
                value="test",
                serverScope="INVALID_SCOPE",
            )

    def test_dhcpv4_service_option(self) -> None:
        """Test DHCPv4 service option payload."""
        payload = DHCPv4ServiceOptionPayload(
            name="lease-time",
            code=51,
            value="86400",
            serverScope="DHCP_SERVER",
        )

        assert payload.type == "DHCPv4ServiceOption"


class TestPayloadModelDump:
    """Tests for proper model serialization."""

    def test_exclude_none_values(self) -> None:
        """Test that None values can be excluded from dump."""
        payload = IPv4AddressPayload(address="10.1.0.10", state="STATIC")

        # With exclude_none, optional None fields should not appear
        data = payload.model_dump(exclude_none=True)
        assert "name" not in data or data.get("name") is None

    def test_nested_model_serialization(self) -> None:
        """Test that nested models serialize correctly."""
        addresses = [AddressObject(type="IPv4Address", address="10.1.0.10")]
        payload = HostRecordPayload(name="www", addresses=addresses)

        data = payload.model_dump()
        assert isinstance(data["addresses"], list)
        assert data["addresses"][0]["type"] == "IPv4Address"
        assert data["addresses"][0]["address"] == "10.1.0.10"
