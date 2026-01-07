import pytest

from src.importer.core.parser import CSVParser
from src.importer.models.csv_row import IP4NetworkRow


class TestParserEmptyString:
    """Test handling of empty strings in CSV parser."""

    def test_preserve_empty_description(self, tmp_path):
        """Test that description="" is preserved as "" (empty string) not None."""
        csv_path = tmp_path / "test_empty_desc.csv"
        csv_path.write_text(
            "row_id,object_type,action,config,cidr,name,description\n"
            '1,ip4_network,update,Default,10.0.0.0/8,TestNet,""\n'
        )

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, IP4NetworkRow)
        # Verify description is empty string, NOT None
        assert row.description == ""

    def test_preserve_empty_parent_code(self, tmp_path):
        """Test that parent_code="" is passed to validator."""
        # Note: LocationRow.validate_parent_code converts "" to None,
        # so final result is None. But we want to ensure parser doesn't
        # preemptively convert it if we mark it as preserve_empty.

        csv_path = tmp_path / "test_empty_parent.csv"
        # Location code must have 2 parts to be valid
        csv_path.write_text(
            "row_id,object_type,action,code,name,parent_code\n"
            '1,location,create,US NYC,New York,""\n'
        )

        from src.importer.utils.exceptions import CSVValidationError

        parser = CSVParser(csv_path)
        with pytest.raises(CSVValidationError) as excinfo:
            parser.parse()

        assert "Input should be a valid string" in str(excinfo.value)

    def test_preserve_empty_description_block(self, tmp_path):
        """Test description clearing on Block."""
        csv_path = tmp_path / "test_block_desc.csv"
        csv_path.write_text(
            "row_id,object_type,action,config,cidr,name,description\n"
            '1,ip4_block,update,Default,10.0.0.0/8,Block1,""\n'
        )

        parser = CSVParser(csv_path)
        rows = parser.parse()
        assert len(rows) == 1
        assert rows[0].description == ""

    def test_standard_fields_convert_to_none(self, tmp_path):
        """Test that standard fields (like name) still convert empty to None (and fail validation if required)."""
        csv_path = tmp_path / "test_standard_field.csv"

        csv_path.write_text(
            "row_id,object_type,action,config,cidr,name,location_code\n"
            '1,ip4_network,update,Default,10.0.0.0/8,TestNet,""\n'
        )

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        row = rows[0]
        # location_code should be None
        assert row.location_code is None

    def test_int_fields_convert_to_none(self, tmp_path):
        """Test that int fields convert empty string to None."""
        csv_path = tmp_path / "test_int_field.csv"
        # bam_id is int | None

        csv_path.write_text(
            "row_id,object_type,action,config,cidr,name,bam_id\n"
            '1,ip4_network,update,Default,10.0.0.0/8,TestNet,""\n'
        )

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        row = rows[0]
        # bam_id should be None
        assert row.bam_id is None
