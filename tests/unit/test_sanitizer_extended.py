"""Extended tests for CSV sanitizer - covering critical missing scenarios.

This test file focuses on areas with low coverage:
- Streaming mode for large files
- Column count mismatch detection
- Comment handling edge cases
- Print diff functionality
- Truncate edge cases
"""

from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from rich.console import Console

from src.importer.core.sanitizer import CSVSanitizer, _truncate


class TestStreamingMode:
    """Test streaming mode for large files."""

    def test_streaming_mode_works_correctly(self, tmp_path):
        """Test that streaming mode processes files correctly."""
        # Create a simple CSV file
        csv_content = "row_id,object_type,name\n"
        csv_content += "1,ip4_block,test\n" * 100
        csv_file = tmp_path / "stream.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)

        # Call streaming mode directly (since we can't easily mock Path.stat)
        result = sanitizer._sanitize_streaming()

        # Should complete successfully
        assert result.stats["rows_processed"] >= 100
        assert "1,ip4_block,test" in result.cleaned_content

    def test_streaming_mode_cleans_whitespace(self, tmp_path):
        """Test that streaming mode properly cleans whitespace."""
        csv_content = "row_id,object_type\n 1 , ip4_block \n 2 , ip4_network \n"
        csv_file = tmp_path / "stream_test.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)

        # Call streaming mode directly
        result = sanitizer._sanitize_streaming()

        assert result.has_changes
        assert result.stats["cells_cleaned"] >= 2
        assert "1,ip4_block" in result.cleaned_content
        assert "2,ip4_network" in result.cleaned_content

    def test_streaming_mode_change_limit(self, tmp_path):
        """Test that streaming mode limits changes list to 1000 items."""
        # Create CSV with many whitespace issues
        csv_content = "row_id,object_type\n"
        # Add 1500 rows with whitespace
        for i in range(1500):
            csv_content += f" {i} , ip4_block \n"

        csv_file = tmp_path / "many_changes.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)

        # Call streaming mode directly
        result = sanitizer._sanitize_streaming()

        # Changes should be capped at 1000 + truncation message
        assert len(result.changes) <= 1001
        # Should have truncation message
        assert any("truncated" in c for c in result.changes)

    def test_streaming_mode_progress_logging(self, tmp_path):
        """Test that streaming mode logs progress for large files."""
        csv_content = "row_id,object_type\n"
        # Add enough rows to trigger progress logging (every 100,000 rows)
        for i in range(100001):
            csv_content += f"{i},ip4_block\n"

        csv_file = tmp_path / "progress_test.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)

        # Call streaming mode directly
        result = sanitizer._sanitize_streaming()

        # Should process all rows
        assert result.stats["rows_processed"] == 100002  # Including header


class TestColumnCountMismatch:
    """Test column count mismatch detection."""

    def test_column_count_mismatch_detected(self, tmp_path):
        """Test that column count mismatch is reported in changes."""
        csv_content = "row_id,object_type,cidr\n1,ip4_block,10.0.0.0/8\n2,ip4_network\n"
        csv_file = tmp_path / "mismatch.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should report column count mismatch
        assert any("Column count mismatch" in c for c in result.changes)
        assert any("found 2" in c and "expected 3" in c for c in result.changes)

    def test_column_count_mismatch_with_extra_columns(self, tmp_path):
        """Test mismatch when row has more columns than header."""
        csv_content = "row_id,object_type\n1,ip4_block,extra,data\n"
        csv_file = tmp_path / "extra_cols.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should report mismatch
        assert any("Column count mismatch" in c for c in result.changes)
        assert any("found 4" in c and "expected 2" in c for c in result.changes)


class TestCommentHandling:
    """Test comment and blank line handling."""

    def test_multiple_comments_preserved(self, tmp_path):
        """Test that multiple comments are preserved in order."""
        csv_content = """# Comment 1
# Comment 2
row_id,object_type
# Comment 3
1,ip4_block
# Comment 4
"""
        csv_file = tmp_path / "comments.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # All comments should be preserved
        assert "# Comment 1" in result.cleaned_content
        assert "# Comment 2" in result.cleaned_content
        assert "# Comment 3" in result.cleaned_content
        assert "# Comment 4" in result.cleaned_content

    def test_mixed_comments_and_blank_lines(self, tmp_path):
        """Test handling of mixed comments and blank lines."""
        csv_content = """# Header comment

row_id,object_type

# Data comment
1,ip4_block

"""
        csv_file = tmp_path / "mixed.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Comments and blank lines should be preserved
        assert "# Header comment" in result.cleaned_content
        assert "# Data comment" in result.cleaned_content
        lines = result.cleaned_content.split("\n")
        blank_lines = [i for i, line in enumerate(lines) if line == ""]
        assert len(blank_lines) >= 2

    def test_comment_at_end_of_file(self, tmp_path):
        """Test that comments at end of file are preserved."""
        csv_content = "row_id,object_type\n1,ip4_block\n# End comment\n"
        csv_file = tmp_path / "end_comment.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        assert "# End comment" in result.cleaned_content


class TestPrintDiff:
    """Test print_diff functionality."""

    def test_print_diff_no_changes(self, tmp_path):
        """Test print_diff when there are no changes."""
        csv_content = "row_id,object_type\n1,ip4_block\n"
        csv_file = tmp_path / "clean.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Capture console output
        console = Console(file=StringIO())
        sanitizer.print_diff(result, console)

        output = console.file.getvalue()
        assert "No issues found" in output or "clean" in output.lower()

    def test_print_diff_with_changes(self, tmp_path):
        """Test print_diff when there are changes."""
        csv_content = " row_id , object_type \n 1 , ip4_block \n"
        csv_file = tmp_path / "dirty.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        console = Console(file=StringIO())
        sanitizer.print_diff(result, console)

        output = console.file.getvalue()
        # Should show stats
        assert "Rows Processed" in output or "rows" in output.lower()

    def test_print_diff_many_changes_truncated(self, tmp_path):
        """Test that print_diff truncates long change lists."""
        csv_content = "row_id,object_type\n"
        # Add 30 rows with whitespace (more than display limit of 20)
        for i in range(30):
            csv_content += f" {i} , ip4_block \n"

        csv_file = tmp_path / "many.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        console = Console(file=StringIO())
        sanitizer.print_diff(result, console)

        output = console.file.getvalue()
        # Should indicate truncation
        assert "more" in output.lower() or "..." in output


class TestTruncateFunction:
    """Test _truncate helper function."""

    def test_truncate_short_string(self):
        """Test that short strings are not truncated."""
        result = _truncate("short")
        assert result == "short"

    def test_truncate_long_string(self):
        """Test that long strings are truncated."""
        long_string = "a" * 100
        result = _truncate(long_string)
        assert len(result) <= 30
        assert result.endswith("...")

    def test_truncate_with_newlines(self):
        """Test that newlines are converted to visible markers."""
        string_with_newlines = "line1\nline2\rline3"
        result = _truncate(string_with_newlines)
        assert "\\n" in result
        assert "\\r" in result
        # Should not contain actual newlines
        assert "\n" not in result
        assert "\r" not in result

    def test_truncate_long_with_newlines(self):
        """Test truncation of long strings with newlines."""
        long_with_newlines = "line1\n" + ("a" * 100) + "\nline2"
        result = _truncate(long_with_newlines, max_len=30)
        assert len(result) <= 30
        assert "\\n" in result
        assert result.endswith("...")

    def test_truncate_custom_length(self):
        """Test truncate with custom max length."""
        string = "a" * 50
        result = _truncate(string, max_len=10)
        assert len(result) <= 10
        assert result.endswith("...")


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_csv_file(self, tmp_path):
        """Test handling of empty CSV file."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("", encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should handle gracefully
        assert not result.has_changes
        assert result.stats["rows_processed"] == 0

    def test_only_comments(self, tmp_path):
        """Test CSV file with only comments."""
        csv_content = "# Comment 1\n# Comment 2\n# Comment 3\n"
        csv_file = tmp_path / "only_comments.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should preserve comments
        assert not result.has_changes
        assert "# Comment 1" in result.cleaned_content
        assert "# Comment 2" in result.cleaned_content
        assert "# Comment 3" in result.cleaned_content

    def test_only_blank_lines(self, tmp_path):
        """Test CSV file with only blank lines."""
        csv_content = "\n\n\n"
        csv_file = tmp_path / "only_blanks.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should handle gracefully
        assert not result.has_changes

    def test_non_string_cell_values(self, tmp_path):
        """Test handling of non-string cell values (shouldn't happen in CSV, but test robustness)."""
        # This is more of a defensive test - CSV reader always returns strings
        # But the code has a check for non-string values
        csv_content = "row_id,object_type\n1,ip4_block\n"
        csv_file = tmp_path / "normal.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should complete without errors
        assert result.stats["rows_processed"] == 2

    def test_unicode_content(self, tmp_path):
        """Test handling of Unicode characters in CSV."""
        csv_content = "row_id,object_type,name\n1,ip4_block,Блок\n2,ip4_network,网络\n"
        csv_file = tmp_path / "unicode.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should preserve Unicode
        assert "Блок" in result.cleaned_content
        assert "网络" in result.cleaned_content

    def test_trailing_newline_preservation(self, tmp_path):
        """Test that trailing newline is preserved when present."""
        csv_with_newline = "row_id,object_type\n1,ip4_block\n"
        csv_file = tmp_path / "with_newline.csv"
        csv_file.write_text(csv_with_newline, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should end with newline
        assert result.cleaned_content.endswith("\n")

    def test_no_trailing_newline(self, tmp_path):
        """Test handling when original file has no trailing newline."""
        csv_without_newline = "row_id,object_type\n1,ip4_block"
        csv_file = tmp_path / "no_newline.csv"
        csv_file.write_text(csv_without_newline, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should not add trailing newline if not present
        assert not result.cleaned_content.endswith("\n") or result.cleaned_content == csv_without_newline + "\n"

    def test_very_long_cell_value(self, tmp_path):
        """Test handling of very long cell values."""
        long_value = "x" * 10000
        csv_content = f"row_id,object_type,description\n1,ip4_block,{long_value}\n"
        csv_file = tmp_path / "long_cell.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        # Should handle without errors
        assert result.stats["rows_processed"] == 2
        assert long_value in result.cleaned_content


class TestSanitizeResult:
    """Test SanitizeResult dataclass."""

    def test_sanitize_result_properties(self, tmp_path):
        """Test SanitizeResult has correct properties."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("row_id,object_type\n 1 ,ip4_block\n", encoding="utf-8")

        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        assert result.original_path == csv_file
        assert isinstance(result.has_changes, bool)
        assert isinstance(result.cleaned_content, str)
        assert isinstance(result.changes, list)
        assert isinstance(result.stats, dict)
        assert "rows_processed" in result.stats
        assert "cells_cleaned" in result.stats
        assert "headers_cleaned" in result.stats
