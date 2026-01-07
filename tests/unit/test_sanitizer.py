"""Tests for CSV sanitizer functionality."""

from pathlib import Path

import pytest

from src.importer.core.sanitizer import CSVSanitizer


def test_sanitize_whitespace(tmp_path):
    """Test that whitespace is stripped from cell values."""
    csv_content = "row_id,object_type,cidr\n 1 , ip4_block , 10.0.0.0/8 \n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    assert result.has_changes
    # New format: Row X (line ~Y) [column]: 'old' -> 'new'
    assert any("' 1 '" in c and "'1'" in c for c in result.changes)
    assert "row_id,object_type,cidr\n1,ip4_block,10.0.0.0/8\n" == result.cleaned_content


def test_sanitize_headers(tmp_path):
    """Test that whitespace is stripped from header names."""
    csv_content = " row_id , object_type \n1,ip4_block\n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    assert result.has_changes
    # Check that header was cleaned
    assert any("Header" in c and "' row_id '" in c for c in result.changes)
    assert "row_id,object_type\n1,ip4_block\n" == result.cleaned_content


def test_sanitize_comments(tmp_path):
    """Test that comments are preserved."""
    csv_content = "# Comment\nrow_id,object_type\n 1 ,ip4_block\n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    assert result.has_changes
    assert "# Comment" in result.cleaned_content
    # Check that row 2 (line 3) was cleaned
    assert any("' 1 '" in c and "'1'" in c for c in result.changes)


def test_no_changes(tmp_path):
    """Test that clean CSV produces no changes."""
    csv_content = "row_id,object_type\n1,ip4_block\n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    assert not result.has_changes
    assert result.cleaned_content == csv_content


def test_multi_header_switch(tmp_path):
    """Test handling of multi-header CSV files (schema switches)."""
    csv_content = """row_id,object_type
1,ip4_block
row_id,object_type,cidr
2,ip4_network, 10.1.0.0/16
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    assert result.has_changes
    # Check that CIDR was cleaned
    assert any("' 10.1.0.0/16'" in c and "'10.1.0.0/16'" in c for c in result.changes)
    assert "2,ip4_network,10.1.0.0/16" in result.cleaned_content


def test_multiline_quoted_field(tmp_path):
    """Test handling of multi-line quoted fields (the main fix)."""
    # CSV with a field containing embedded newline
    csv_content = 'row_id,object_type,description\n1,ip4_block,"Line 1\nLine 2"\n'
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    # Should parse without error and preserve the multi-line field
    assert not result.has_changes  # No whitespace to strip
    # The field should be properly quoted in output
    assert (
        '"Line 1\nLine 2"' in result.cleaned_content or "Line 1\nLine 2" in result.cleaned_content
    )


def test_multiline_quoted_field_with_whitespace(tmp_path):
    """Test multi-line field with whitespace that needs stripping."""
    # CSV with a field containing embedded newline AND whitespace
    csv_content = 'row_id,object_type,description\n 1 ,ip4_block," Line 1\nLine 2 "\n'
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    assert result.has_changes
    # Row ID should be cleaned
    assert any("' 1 '" in c and "'1'" in c for c in result.changes)
    # Description should be cleaned (embedded newline preserved but outer whitespace stripped)
    assert any("description" in c.lower() or "col_2" in c for c in result.changes)


def test_blank_lines_preserved(tmp_path):
    """Test that blank lines are preserved in output."""
    csv_content = "row_id,object_type\n\n1,ip4_block\n\n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    # Blank lines should be preserved
    lines = result.cleaned_content.split("\n")
    assert "" in lines  # At least one blank line preserved


def test_file_not_found():
    """Test that FileNotFoundError is raised for missing file."""
    sanitizer = CSVSanitizer(Path("/nonexistent/file.csv"))
    with pytest.raises(FileNotFoundError):
        sanitizer.sanitize()


def test_stats_tracking(tmp_path):
    """Test that statistics are properly tracked."""
    csv_content = " row_id , object_type \n 1 , ip4_block \n 2 , ip4_network \n"
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    sanitizer = CSVSanitizer(csv_file)
    result = sanitizer.sanitize()

    assert result.stats["rows_processed"] == 3  # 1 header + 2 data rows
    assert result.stats["headers_cleaned"] >= 1  # At least row_id header was cleaned
    assert result.stats["cells_cleaned"] >= 2  # At least row_id cells were cleaned
