from src.importer.core.parser import CSVParser
from src.importer.models.csv_row import IP4NetworkRow


class TestParserHeaderNormalization:
    """Test normalization of CSV headers (stripping * prefix)."""

    def test_header_with_asterisk(self, tmp_path):
        """Test that headers with * prefix are normalized correctly."""
        csv_path = tmp_path / "test_asterisk.csv"
        # *row_id is required for detection, *object_type is required field
        csv_path.write_text(
            "*row_id,*object_type,*action,*config,*cidr,name\n"
            "1,ip4_network,create,Default,10.0.0.0/8,TestNet\n"
        )

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        row = rows[0]
        assert isinstance(row, IP4NetworkRow)
        assert str(row.row_id) == "1"  # Verify row_id detected
        assert row.cidr == "10.0.0.0/8"

    def test_header_mixed(self, tmp_path):
        """Test mix of clean and asterisk headers."""
        csv_path = tmp_path / "test_mixed.csv"
        csv_path.write_text(
            "*row_id,object_type,*action,config,*cidr,name\n"
            "1,ip4_network,create,Default,10.0.0.0/8,TestNet\n"
        )

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        row = rows[0]
        assert str(row.row_id) == "1"
        assert row.action == "create"
        assert row.cidr == "10.0.0.0/8"

    def test_header_stripping_whitespace(self, tmp_path):
        """Test that whitespace is handled correctly with asterisks."""
        csv_path = tmp_path / "test_whitespace.csv"
        # " *row_id " -> strip() -> "*row_id" -> lstrip("*") -> "row_id"
        csv_path.write_text(
            " *row_id , *object_type , *action , *config , *cidr , name \n"
            "1,ip4_network,create,Default,10.0.0.0/8,TestNet\n"
        )

        parser = CSVParser(csv_path)
        rows = parser.parse()

        assert len(rows) == 1
        row = rows[0]
        assert str(row.row_id) == "1"

    def test_streaming_header_normalization(self, tmp_path):
        """Test normalization in streaming mode."""
        csv_path = tmp_path / "test_stream.csv"
        csv_path.write_text(
            "*row_id,*object_type,*action,*cidr,*config,*name\n"
            "1,ip4_block,create,10.0.0.0/8,Default,TestBlock\n"
        )

        async def run_stream():
            parser = CSVParser(csv_path)
            rows = []
            async for row in parser.parse_stream():
                rows.append(row)
            return rows

        import asyncio

        rows = asyncio.run(run_stream())
        assert len(rows) == 1
        assert str(rows[0].row_id) == "1"
