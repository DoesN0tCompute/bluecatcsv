"""Tests for the CSVParser class."""

from pathlib import Path

import pytest

from src.importer.core.parser import CSVParser
from src.importer.utils.exceptions import CSVValidationError


class TestCSVParser:
    """Test suite for CSVParser."""

    @pytest.fixture
    def csv_file(self, tmp_path):
        """Create a temporary CSV file."""
        path = tmp_path / "test.csv"
        return path

    def test_parse_valid_csv(self, csv_file):
        """Test parsing a valid CSV file."""
        content = """row_id,object_type,action,name,cidr,config,_version
1,ip4_block,create,test-block,10.0.0.0/8,Default,3.0
2,ip4_network,create,test-network,10.0.0.0/24,Default,3.0
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)
        rows = parser.parse()

        assert len(rows) == 2
        assert rows[0].row_id == "1"
        assert rows[0].object_type == "ip4_block"
        assert rows[0].action == "create"
        assert rows[1].row_id == "2"
        assert rows[1].object_type == "ip4_network"
        assert rows[1].action == "create"

    def test_parse_empty_csv(self, csv_file):
        """Test parsing an empty CSV file returns empty list (BUG-004 fix)."""
        csv_file.write_text("", encoding="utf-8")

        parser = CSVParser(csv_file)

        # BUG-004: Empty CSVs should return empty list, not raise error
        rows = parser.parse()
        assert rows == []

    def test_parse_missing_file(self):
        """Test parsing a non-existent file."""
        parser = CSVParser(Path("non_existent.csv"))
        with pytest.raises(FileNotFoundError):
            parser.parse()

    def test_parse_invalid_row(self, csv_file):
        """Test parsing a CSV with an invalid row (validation error)."""
        # Missing required field 'cidr' for ip4_block
        content = """row_id,object_type,action,name,config
1,ip4_block,create,test-block,Default
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)

        with pytest.raises(CSVValidationError) as exc:
            parser.parse(strict=True)

        assert "Line 2" in str(exc.value)

    def test_parse_invalid_row_non_strict(self, csv_file):
        """Test non-strict parsing collects errors."""
        # Missing required field 'cidr' for ip4_block
        content = """row_id,object_type,action,name,config
1,ip4_block,create,test-block,Default
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)
        rows = parser.parse(strict=False)

        assert len(rows) == 0
        assert len(parser.errors) == 1
        assert "Line 2" in str(parser.errors[0])

    def test_duplicate_row_id(self, csv_file):
        """Test detection of duplicate row IDs."""
        content = """row_id,object_type,action,name,cidr,config
1,ip4_block,create,test-block,10.0.0.0/8,Default
1,ip4_block,create,test-block-2,11.0.0.0/8,Default
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)

        # Note: The error message might contain regex special chars, so we use simpler match
        with pytest.raises(CSVValidationError) as exc:
            parser.parse(strict=True)
        assert "Duplicate row_id" in str(exc.value)

    def test_comments_ignoring(self, csv_file):
        """Test that comments are ignored."""
        content = """# This is a comment
row_id,object_type,action,name,cidr,config
# Another comment
1,ip4_block,create,test-block,10.0.0.0/8,Default
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)
        rows = parser.parse()

        assert len(rows) == 1
        assert rows[0].row_id == "1"

    def test_multi_header_csv(self, csv_file):
        """Test parsing CSV with multiple headers (schema switching)."""
        # Note: zone_name is required for dns_zone
        content = """row_id,object_type,action,name,cidr,config
1,ip4_block,create,test-block,10.0.0.0/8,Default
row_id,object_type,action,zone_name,config,view_path
2,dns_zone,create,example.com,Default,Internal
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)
        rows = parser.parse()

        assert len(rows) == 2
        assert rows[0].object_type == "ip4_block"
        assert rows[1].object_type == "dns_zone"

    @pytest.mark.asyncio
    async def test_parse_stream(self, csv_file):
        """Test streaming parser."""
        content = """row_id,object_type,action,name,cidr,config
1,ip4_block,create,test-block,10.0.0.0/8,Default
2,ip4_block,create,test-block-2,11.0.0.0/8,Default
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)
        rows = []
        async for row in parser.parse_stream():
            rows.append(row)

        assert len(rows) == 2
        assert rows[0].row_id == "1"
        assert rows[1].row_id == "2"

    def test_whitespace_stripping(self, csv_file):
        """Test that whitespace is stripped from values."""
        content = """row_id,object_type,action,name,cidr,config
1,  ip4_block  ,  create  ,  test-block  ,  10.0.0.0/8  ,  Default
"""
        csv_file.write_text(content, encoding="utf-8")

        parser = CSVParser(csv_file)
        rows = parser.parse()

        assert rows[0].object_type == "ip4_block"
        assert rows[0].name == "test-block"
