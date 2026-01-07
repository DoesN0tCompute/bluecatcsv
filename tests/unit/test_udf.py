"""Unit tests for User-Defined Fields (UDF) functionality.

Tests cover:
- UDF definition CSV row models
- UDF payload models
- UDF handlers
- UDF value extraction from rows
"""

import pytest
from importer.models.csv_row import UDFDefinitionRow, UDLDefinitionRow
from importer.models.payloads import UDFDefinitionPayload, UDLDefinitionPayload
from pydantic import ValidationError


class TestUDFDefinitionRow:
    """Tests for UDFDefinitionRow model."""

    def test_valid_udf_definition(self):
        """Test valid UDF definition parsing."""
        row = UDFDefinitionRow(
            row_id=1,
            object_type="udf_definition",
            action="create",
            name="CostCenter",
            display_name="Cost Center",
            field_type="TEXT",
            required=False,
            resource_types="IPv4Network|IPv4Block",
        )
        assert row.name == "CostCenter"
        assert row.display_name == "Cost Center"
        assert row.field_type == "TEXT"
        assert row.required is False
        assert row.resource_types == "IPv4Network|IPv4Block"

    def test_field_type_validation(self):
        """Test that field type is validated."""
        row = UDFDefinitionRow(
            row_id=1,
            object_type="udf_definition",
            action="create",
            name="TestField",
            field_type="text",  # lowercase should be converted
        )
        assert row.field_type == "TEXT"

    def test_invalid_field_type(self):
        """Test that invalid field type raises error."""
        with pytest.raises(ValidationError) as exc:
            UDFDefinitionRow(
                row_id=1,
                object_type="udf_definition",
                action="create",
                name="TestField",
                field_type="INVALID_TYPE",
            )
        assert "Invalid UDF field type" in str(exc.value)

    def test_name_with_spaces_rejected(self):
        """Test that UDF name with spaces is rejected."""
        with pytest.raises(ValidationError) as exc:
            UDFDefinitionRow(
                row_id=1,
                object_type="udf_definition",
                action="create",
                name="Cost Center",  # Space not allowed
                field_type="TEXT",
            )
        assert "cannot contain spaces" in str(exc.value)

    def test_name_starting_with_number_rejected(self):
        """Test that UDF name starting with number is rejected."""
        with pytest.raises(ValidationError) as exc:
            UDFDefinitionRow(
                row_id=1,
                object_type="udf_definition",
                action="create",
                name="1CostCenter",
                field_type="TEXT",
            )
        assert "must start with a letter" in str(exc.value)

    def test_get_resource_types_list(self):
        """Test parsing pipe-separated resource types."""
        row = UDFDefinitionRow(
            row_id=1,
            object_type="udf_definition",
            action="create",
            name="TestField",
            field_type="TEXT",
            resource_types="IPv4Network|IPv4Block|IPv4Address",
        )
        types = row.get_resource_types_list()
        assert types == ["IPv4Network", "IPv4Block", "IPv4Address"]

    def test_get_resource_types_list_wildcard(self):
        """Test resource types wildcard."""
        row = UDFDefinitionRow(
            row_id=1,
            object_type="udf_definition",
            action="create",
            name="TestField",
            field_type="TEXT",
            resource_types="*",
        )
        types = row.get_resource_types_list()
        assert types == ["*"]

    def test_get_predefined_values_list(self):
        """Test parsing pipe-separated predefined values."""
        row = UDFDefinitionRow(
            row_id=1,
            object_type="udf_definition",
            action="create",
            name="Environment",
            field_type="TEXT",
            predefined_values="Dev|Staging|Production",
        )
        values = row.get_predefined_values_list()
        assert values == ["Dev", "Staging", "Production"]

    def test_all_valid_field_types(self):
        """Test all valid UDF field types."""
        valid_types = ["TEXT", "MULTILINE_TEXT", "URL", "EMAIL", "PHONE"]
        for field_type in valid_types:
            row = UDFDefinitionRow(
                row_id=1,
                object_type="udf_definition",
                action="create",
                name="TestField",
                field_type=field_type,
            )
            assert row.field_type == field_type


class TestUDLDefinitionRow:
    """Tests for UDLDefinitionRow model."""

    def test_valid_udl_definition(self):
        """Test valid UDL definition parsing."""
        row = UDLDefinitionRow(
            row_id=1,
            object_type="udl_definition",
            action="create",
            name="AssociatedDevice",
            display_name="Associated Device",
            source_types="IPv4Address",
            destination_types="Device",
        )
        assert row.name == "AssociatedDevice"
        assert row.display_name == "Associated Device"
        assert row.source_types == "IPv4Address"
        assert row.destination_types == "Device"

    def test_name_with_spaces_rejected(self):
        """Test that UDL name with spaces is rejected."""
        with pytest.raises(ValidationError) as exc:
            UDLDefinitionRow(
                row_id=1,
                object_type="udl_definition",
                action="create",
                name="Associated Device",  # Space not allowed
                source_types="IPv4Address",
                destination_types="Device",
            )
        assert "cannot contain spaces" in str(exc.value)

    def test_get_source_types_list(self):
        """Test parsing pipe-separated source types."""
        row = UDLDefinitionRow(
            row_id=1,
            object_type="udl_definition",
            action="create",
            name="TestLink",
            source_types="IPv4Address|IPv4Network",
            destination_types="Device",
        )
        types = row.get_source_types_list()
        assert types == ["IPv4Address", "IPv4Network"]

    def test_get_destination_types_list(self):
        """Test parsing pipe-separated destination types."""
        row = UDLDefinitionRow(
            row_id=1,
            object_type="udl_definition",
            action="create",
            name="TestLink",
            source_types="IPv4Address",
            destination_types="Device|Server",
        )
        types = row.get_destination_types_list()
        assert types == ["Device", "Server"]


class TestUDFPayloads:
    """Tests for UDF payload models."""

    def test_udf_definition_payload(self):
        """Test valid UDF definition payload."""
        payload = UDFDefinitionPayload(
            name="CostCenter",
            type="TEXT",
            displayName="Cost Center",
            required=False,
            resourceTypes=["IPv4Network", "IPv4Block"],
        )
        assert payload.name == "CostCenter"
        assert payload.type == "TEXT"
        assert payload.resourceTypes == ["IPv4Network", "IPv4Block"]

    def test_udf_definition_payload_name_validation(self):
        """Test UDF payload name validation."""
        with pytest.raises(ValidationError) as exc:
            UDFDefinitionPayload(
                name="Cost Center",  # Space not allowed
                type="TEXT",
            )
        assert "cannot contain spaces" in str(exc.value)

    def test_udl_definition_payload(self):
        """Test valid UDL definition payload."""
        payload = UDLDefinitionPayload(
            name="AssociatedDevice",
            sourceTypes=["IPv4Address"],
            destinationTypes=["Device"],
            displayName="Associated Device",
        )
        assert payload.name == "AssociatedDevice"
        assert payload.sourceTypes == ["IPv4Address"]
        assert payload.destinationTypes == ["Device"]


class TestUDFValueExtraction:
    """Tests for extracting UDF values from CSV rows."""

    def test_get_udf_fields_from_row(self):
        """Test extracting UDF fields from a row."""
        from importer.models.csv_row import IP4NetworkRow

        # Create a row with UDF fields
        row = IP4NetworkRow(
            row_id=1,
            object_type="ip4_network",
            action="create",
            config="Default",
            cidr="10.1.0.0/24",
            name="Test-Network",
        )

        # Access model dump to simulate extra fields
        row.model_dump()

        # Test get_udf_fields method with no UDF fields
        udf_fields = row.get_udf_fields()
        assert udf_fields == {}

    def test_udf_fields_with_extra(self):
        """Test that extra fields starting with udf_ are captured."""
        from importer.models.csv_row import IP4NetworkRow

        # Create row with extra fields (simulating CSV with UDF columns)
        row_data = {
            "row_id": 1,
            "object_type": "ip4_network",
            "action": "create",
            "config": "Default",
            "cidr": "10.1.0.0/24",
            "name": "Test-Network",
            "udf_CostCenter": "CC-12345",
            "udf_Owner": "admin@example.com",
        }
        row = IP4NetworkRow.model_validate(row_data)

        # Get UDF fields
        udf_fields = row.get_udf_fields()
        assert "udf_CostCenter" in udf_fields
        assert "udf_Owner" in udf_fields
        assert udf_fields["udf_CostCenter"] == "CC-12345"
        assert udf_fields["udf_Owner"] == "admin@example.com"
