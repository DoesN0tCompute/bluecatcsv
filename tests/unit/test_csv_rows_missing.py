"""Tests for CSV row models that were missing dedicated test coverage."""

import pytest
from pydantic import ValidationError

from src.importer.models.csv_row import (
    AliasRecordRow,
    DNSZoneRow,
    ExternalHostRecordRow,
    GenericRecordRow,
    IP4BlockRow,
    MXRecordRow,
    SRVRecordRow,
    TXTRecordRow,
)


class TestIP4BlockRow:
    """Test IP4BlockRow model."""

    def test_ip4_block_row_valid(self):
        """Test creating a valid IPv4 block row."""
        row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="Corporate Block",
        )

        assert row.row_id == 1
        assert row.object_type == "ip4_block"
        assert row.action == "create"
        assert row.config == "Default"
        assert row.cidr == "10.0.0.0/8"
        assert row.name == "Corporate Block"

    def test_ip4_block_row_invalid_cidr(self):
        """Test that invalid CIDR notation is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IP4BlockRow(
                row_id=1,
                object_type="ip4_block",
                action="create",
                config="Default",
                cidr="invalid-cidr",
                name="Test Block",
            )

        assert "Invalid CIDR notation" in str(exc_info.value)

    def test_ip4_block_row_empty_name(self):
        """Test that empty name is handled correctly."""
        # Name is a required field and cannot be empty
        with pytest.raises(ValidationError) as exc_info:
            IP4BlockRow(
                row_id=1,
                object_type="ip4_block",
                action="create",
                config="Default",
                cidr="10.0.0.0/8",
                name="  ",
            )

        assert "name" in str(exc_info.value)

    def test_ip4_block_row_with_udf(self):
        """Test UDF fields are preserved."""
        row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="Test Block",
            udf_owner="IT Department",
            udf_environment="Production",
        )

        udf_fields = row.get_udf_fields()
        assert udf_fields["udf_owner"] == "IT Department"
        assert udf_fields["udf_environment"] == "Production"


class TestAliasRecordRow:
    """Test AliasRecordRow model."""

    def test_alias_record_row_valid(self):
        """Test creating a valid alias record row."""
        row = AliasRecordRow(
            row_id=1,
            object_type="alias_record",
            action="create",
            config="Default",
            view_path="Internal",
            name="www",
            cname="web.example.com",
            ttl=3600,
        )

        assert row.row_id == 1
        assert row.object_type == "alias_record"
        assert row.action == "create"
        assert row.config == "Default"
        assert row.view_path == "Internal"
        assert row.name == "www"
        assert row.linked_record_name == "web.example.com"
        assert row.ttl == 3600

    def test_alias_record_row_missing_cname(self):
        """Test validation when cname is missing for create."""
        with pytest.raises(ValidationError) as exc_info:
            AliasRecordRow(
                row_id=1,
                object_type="alias_record",
                action="create",
                config="Default",
                view_path="Internal",
                name="www",
            )

        assert "cname" in str(exc_info.value).lower()


class TestMXRecordRow:
    """Test MXRecordRow model."""

    def test_mx_record_row_valid(self):
        """Test creating a valid MX record row."""
        row = MXRecordRow(
            row_id=1,
            object_type="mx_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="@",
            exchange="mail.example.com",
            preference=10,
            ttl=3600,
        )

        assert row.row_id == 1
        assert row.object_type == "mx_record"
        assert row.exchange == "mail.example.com"
        assert row.preference == 10
        assert row.ttl == 3600

    def test_mx_record_row_missing_exchange(self):
        """Test validation when exchange is missing."""
        with pytest.raises(ValidationError) as exc_info:
            MXRecordRow(
                row_id=1,
                object_type="mx_record",
                action="create",
                config="Default",
                view_path="Internal",
                name="@",
                preference=10,
            )

        assert "exchange" in str(exc_info.value).lower()

    def test_mx_record_row_invalid_preference(self):
        """Test validation for invalid preference values."""
        # The MXRecordRow model doesn't validate preference range, so this should pass
        row = MXRecordRow(
            row_id=1,
            object_type="mx_record",
            action="create",
            config="Default",
            view_path="Internal",
            name="@",
            exchange="mail.example.com",
            preference=70000,  # Above 65535 but still valid in the model
        )

        assert row.preference == 70000


class TestTXTRecordRow:
    """Test TXTRecordRow model."""

    def test_txt_record_row_valid(self):
        """Test creating a valid TXT record row."""
        row = TXTRecordRow(
            row_id=1,
            object_type="txt_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="_dmarc",
            text="v=DMARC1; p=none",
            ttl=3600,
        )

        assert row.row_id == 1
        assert row.object_type == "txt_record"
        assert row.name == "_dmarc"
        assert row.text == "v=DMARC1; p=none"
        assert row.ttl == 3600

    def test_txt_record_row_missing_text(self):
        """Test validation when text is missing."""
        with pytest.raises(ValidationError) as exc_info:
            TXTRecordRow(
                row_id=1,
                object_type="txt_record",
                action="create",
                config="Default",
                view_path="Internal",
                zone_name="example.com",
                name="_dmarc",
            )

        assert "text" in str(exc_info.value).lower()

    def test_txt_record_row_with_quoted_text(self):
        """Test TXT record with quoted text."""
        row = TXTRecordRow(
            row_id=1,
            object_type="txt_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="test",
            text='"v=spf1 include:_spf.example.com ~all"',
        )

        # Text should preserve quotes for SPF records
        assert row.text == '"v=spf1 include:_spf.example.com ~all"'


class TestSRVRecordRow:
    """Test SRVRecordRow model."""

    def test_srv_record_row_valid(self):
        """Test creating a valid SRV record row."""
        row = SRVRecordRow(
            row_id=1,
            object_type="srv_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="_sip._tcp",
            target="sip.example.com",
            port=5060,
            priority=10,
            weight=50,
            ttl=3600,
        )

        assert row.row_id == 1
        assert row.object_type == "srv_record"
        assert row.name == "_sip._tcp"
        assert row.target == "sip.example.com"
        assert row.port == 5060
        assert row.priority == 10
        assert row.weight == 50
        assert row.ttl == 3600

    def test_srv_record_row_missing_target(self):
        """Test validation when target is missing."""
        with pytest.raises(ValidationError) as exc_info:
            SRVRecordRow(
                row_id=1,
                object_type="srv_record",
                action="create",
                config="Default",
                view_path="Internal",
                zone_name="example.com",
                name="_sip._tcp",
                port=5060,
            )

        assert "target" in str(exc_info.value).lower()

    def test_srv_record_row_invalid_port(self):
        """Test validation for invalid port values."""
        with pytest.raises(ValidationError) as exc_info:
            SRVRecordRow(
                row_id=1,
                object_type="srv_record",
                action="create",
                config="Default",
                view_path="Internal",
                zone_name="example.com",
                name="_sip._tcp",
                target="sip.example.com",
                port=70000,  # Above 65535
            )

        assert "port" in str(exc_info.value).lower()


class TestDNSZoneRow:
    """Test DNSZoneRow model."""

    def test_dns_zone_row_valid(self):
        """Test creating a valid DNS zone row."""
        row = DNSZoneRow(
            row_id=1,
            object_type="dns_zone",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
        )

        assert row.row_id == 1
        assert row.object_type == "dns_zone"
        assert row.action == "create"
        assert row.config == "Default"
        assert row.view_path == "Internal"
        assert row.zone_name == "example.com"

    def test_dns_zone_row_with_spaces_in_zone_name(self):
        """Test that zone names with spaces are handled."""
        row = DNSZoneRow(
            row_id=1,
            object_type="dns_zone",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="  example.com  ",
        )

        # Whitespace should be stripped
        assert row.zone_name == "example.com"


class TestExternalHostRecordRow:
    """Test ExternalHostRecordRow model."""

    def test_external_host_record_row_valid(self):
        """Test creating a valid external host record row."""
        row = ExternalHostRecordRow(
            row_id=1,
            object_type="external_host_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="host.external.com",
            ttl=3600,
            description="External web server",
        )

        assert row.row_id == 1
        assert row.object_type == "external_host_record"
        assert row.action == "create"
        assert row.config == "Default"
        assert row.view_path == "Internal"
        assert row.zone_name == "example.com"
        assert row.name == "host.external.com"
        assert row.ttl == 3600
        assert row.description == "External web server"

    def test_external_host_record_row_minimal(self):
        """Test external host record with minimal required fields."""
        row = ExternalHostRecordRow(
            row_id=1,
            object_type="external_host_record",
            action="create",
            config="Default",
            view_path="Internal",
            name="external.example.com",
        )

        assert row.name == "external.example.com"
        assert row.zone_name is None
        assert row.ttl is None
        assert row.description is None

    def test_external_host_record_row_invalid_name(self):
        """Test validation for invalid host names."""
        with pytest.raises(ValidationError) as exc_info:
            ExternalHostRecordRow(
                row_id=1,
                object_type="external_host_record",
                action="create",
                config="Default",
                view_path="Internal",
                name="invalid..name",
            )

        assert "Invalid external host name" in str(exc_info.value)

    def test_external_host_record_row_empty_name(self):
        """Test validation for empty host name."""
        with pytest.raises(ValidationError) as exc_info:
            ExternalHostRecordRow(
                row_id=1,
                object_type="external_host_record",
                action="create",
                config="Default",
                view_path="Internal",
                name="",
            )

        assert "Input should be a valid string" in str(exc_info.value)

    def test_external_host_record_row_trailing_dot(self):
        """Test handling of trailing dot in FQDN."""
        row = ExternalHostRecordRow(
            row_id=1,
            object_type="external_host_record",
            action="create",
            config="Default",
            view_path="Internal",
            name="host.example.com.",
        )

        # Trailing dot should be removed
        assert row.name == "host.example.com"

    def test_external_host_record_row_with_udf(self):
        """Test UDF fields are preserved."""
        row = ExternalHostRecordRow(
            row_id=1,
            object_type="external_host_record",
            action="create",
            config="Default",
            view_path="Internal",
            name="host.external.com",
            udf_owner="External Team",
            udf_environment="Production",
        )

        udf_fields = row.get_udf_fields()
        assert udf_fields["udf_owner"] == "External Team"
        assert udf_fields["udf_environment"] == "Production"

    def test_external_host_record_row_negative_ttl(self):
        """Test that negative TTL is allowed (validation done at API level)."""
        # ExternalHostRecordRow doesn't validate TTL range, this is done by the API
        row = ExternalHostRecordRow(
            row_id=1,
            object_type="external_host_record",
            action="create",
            config="Default",
            view_path="Internal",
            name="host.external.com",
            ttl=-1,
        )

        assert row.ttl == -1


class TestCSVRowBaseFeatures:
    """Test base features that apply to all CSV row models."""

    def test_whitespace_stripping(self):
        """Test that whitespace is stripped from string fields."""
        row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",  # object_type is literal, doesn't strip
            action="create",  # action is literal, doesn't strip
            config="  Default  ",
            cidr="  10.0.0.0/8  ",
            name="  Test Block  ",
        )

        assert row.object_type == "ip4_block"
        assert row.action == "create"
        assert row.config == "Default"
        assert row.cidr == "10.0.0.0/8"
        assert row.name == "Test Block"

    def test_version_field_default(self):
        """Test that version field defaults to 3.0."""
        row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="Test Block",
        )

        assert row.version == "3.0"

    def test_extra_fields_for_udfs(self):
        """Test that extra fields are allowed for UDFs."""
        row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="Test Block",
            custom_field="should be allowed",
            uf_custom="another custom field",
        )

        assert row.custom_field == "should be allowed"
        assert row.uf_custom == "another custom field"

    def test_get_udf_fields(self):
        """Test extraction of UDF fields."""
        row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="Test Block",
            udf_owner="IT",
            udf_location="Datacenter 1",
            regular_field="not a UDF",
        )

        udf_fields = row.get_udf_fields()
        assert udf_fields == {
            "udf_owner": "IT",
            "udf_location": "Datacenter 1",
        }
        assert "regular_field" not in udf_fields


class TestGenericRecordRow:
    """Test GenericRecordRow model."""

    def test_generic_record_row_valid_sshfp(self):
        """Test creating a valid SSHFP generic record row."""
        row = GenericRecordRow(
            row_id=1,
            object_type="generic_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="server1",
            record_type="SSHFP",
            rdata="2 1 123456789abcdef67890123456789abcdef67890",
            ttl=3600,
            description="SSH fingerprint for server1",
        )

        assert row.row_id == 1
        assert row.object_type == "generic_record"
        assert row.action == "create"
        assert row.config == "Default"
        assert row.view_path == "Internal"
        assert row.zone_name == "example.com"
        assert row.name == "server1"
        assert row.record_type == "SSHFP"
        assert row.rdata == "2 1 123456789abcdef67890123456789abcdef67890"
        assert row.ttl == 3600
        assert row.description == "SSH fingerprint for server1"

    def test_generic_record_row_valid_caa(self):
        """Test creating a valid CAA generic record row."""
        row = GenericRecordRow(
            row_id=1,
            object_type="generic_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="@",
            record_type="CAA",
            rdata="0 issue letsencrypt.org",
        )

        assert row.record_type == "CAA"
        assert row.rdata == "0 issue letsencrypt.org"
        assert row.ttl is None  # Optional field

    def test_generic_record_row_valid_tlsa(self):
        """Test creating a valid TLSA generic record row."""
        row = GenericRecordRow(
            row_id=1,
            object_type="generic_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="_443._tcp.www",
            record_type="TLSA",
            rdata="3 1 1 abc123def456",
        )

        assert row.record_type == "TLSA"
        assert row.name == "_443._tcp.www"

    def test_generic_record_row_record_type_uppercase(self):
        """Test that record type is converted to uppercase."""
        row = GenericRecordRow(
            row_id=1,
            object_type="generic_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="test",
            record_type="sshfp",  # lowercase
            rdata="2 1 abc123",
        )

        assert row.record_type == "SSHFP"

    def test_generic_record_row_invalid_record_type(self):
        """Test that invalid record type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GenericRecordRow(
                row_id=1,
                object_type="generic_record",
                action="create",
                config="Default",
                view_path="Internal",
                zone_name="example.com",
                name="test",
                record_type="INVALID",
                rdata="some data",
            )

        assert "Invalid record type" in str(exc_info.value)

    def test_generic_record_row_missing_rdata(self):
        """Test that missing rdata is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GenericRecordRow(
                row_id=1,
                object_type="generic_record",
                action="create",
                config="Default",
                view_path="Internal",
                zone_name="example.com",
                name="test",
                record_type="SSHFP",
            )

        assert "rdata" in str(exc_info.value).lower()

    def test_generic_record_row_whitespace_stripping(self):
        """Test that whitespace is stripped from string fields."""
        row = GenericRecordRow(
            row_id=1,
            object_type="generic_record",
            action="create",
            config="  Default  ",
            view_path="  Internal  ",
            zone_name="  example.com  ",
            name="  server1  ",
            record_type="  SSHFP  ",
            rdata="2 1 abc123",  # rdata should NOT be stripped (may have intentional spaces)
        )

        assert row.config == "Default"
        assert row.view_path == "Internal"
        assert row.zone_name == "example.com"
        assert row.name == "server1"
        assert row.record_type == "SSHFP"

    def test_generic_record_row_all_supported_types(self):
        """Test that all documented record types are accepted."""
        supported_types = [
            "A",
            "A6",
            "AAAA",
            "AFSDB",
            "APL",
            "CAA",
            "CERT",
            "DHCID",
            "DNAME",
            "DS",
            "IPSECKEY",
            "ISDN",
            "KEY",
            "KX",
            "LOC",
            "MB",
            "MG",
            "MINFO",
            "MR",
            "NS",
            "NSAP",
            "PTR",
            "PX",
            "RP",
            "RT",
            "SINK",
            "SPF",
            "SSHFP",
            "TLSA",
            "TXT",
            "WKS",
            "X25",
        ]

        for record_type in supported_types:
            row = GenericRecordRow(
                row_id=1,
                object_type="generic_record",
                action="create",
                config="Default",
                view_path="Internal",
                zone_name="example.com",
                name="test",
                record_type=record_type,
                rdata="test data",
            )
            assert row.record_type == record_type

    def test_generic_record_row_with_udf(self):
        """Test UDF fields are preserved."""
        row = GenericRecordRow(
            row_id=1,
            object_type="generic_record",
            action="create",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
            name="server1",
            record_type="SSHFP",
            rdata="2 1 abc123",
            udf_owner="DNS Team",
            udf_environment="Production",
        )

        udf_fields = row.get_udf_fields()
        assert udf_fields["udf_owner"] == "DNS Team"
        assert udf_fields["udf_environment"] == "Production"
