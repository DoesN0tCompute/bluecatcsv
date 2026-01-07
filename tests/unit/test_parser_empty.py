from src.importer.core.parser import CSVParser


def test_parse_empty_file(tmp_path):
    """Test parsing an empty file."""
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("")

    parser = CSVParser(csv_file)

    # Should accept empty file and return empty list
    rows = parser.parse(strict=True)
    assert rows == []


def test_parse_only_comments(tmp_path):
    """Test parsing a file with only comments."""
    csv_file = tmp_path / "comments.csv"
    csv_file.write_text("# This is a comment\n# Another comment")

    parser = CSVParser(csv_file)

    # Should accept comment-only file and return empty list
    rows = parser.parse(strict=True)
    assert rows == []


def test_parse_headers_only(tmp_path):
    """Test parsing a file with only headers."""
    csv_file = tmp_path / "headers.csv"
    csv_file.write_text("row_id,object_type,name,action\n")

    parser = CSVParser(csv_file)

    # Should accept header-only file and return empty list
    rows = parser.parse(strict=True)
    assert rows == []
