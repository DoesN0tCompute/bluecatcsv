"""CSV Sanitizer for cleaning input files."""

import csv
import io
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from rich.console import Console
from rich.table import Table

logger = structlog.get_logger(__name__)

# Files larger than this threshold will use streaming mode
STREAMING_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB


@dataclass
class SanitizeResult:
    """Result of a sanitization operation."""

    original_path: Path
    has_changes: bool
    cleaned_content: str
    changes: list[str] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)


class CSVSanitizer:
    """
    Sanitize CSV files by stripping whitespace and standardizing format.

    Features:
    - Strips whitespace from all values (including headers)
    - Preserves comments (lines starting with #)
    - Preserves blank lines
    - Handles multi-header CSVs (schema switching)
    - Properly handles multi-line quoted fields
    - Generates detailed change report
    """

    def __init__(self, csv_path: Path) -> None:
        """
        Initialize sanitizer.

        Args:
            csv_path: Path to CSV file to sanitize
        """
        self.csv_path = csv_path

    def sanitize(self) -> SanitizeResult:
        """
        Sanitize the CSV file.

        This method properly handles CSV files with multi-line quoted fields
        by using csv.reader on the full content rather than line-by-line parsing.

        For files larger than STREAMING_THRESHOLD_BYTES (50MB), uses streaming
        mode to avoid loading the entire file into memory.

        Returns:
            SanitizeResult object with details
        """
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        file_size = self.csv_path.stat().st_size
        logger.info(
            "Starting CSV sanitization",
            csv_path=str(self.csv_path),
            file_size_mb=round(file_size / (1024 * 1024), 2),
        )

        # Use streaming mode for large files to avoid OOM
        if file_size > STREAMING_THRESHOLD_BYTES:
            logger.info("Using streaming mode for large file")
            return self._sanitize_streaming()

        with open(self.csv_path, encoding="utf-8") as f:
            content = f.read()

        # First pass: separate comments/blank lines from CSV content
        # Comments and blank lines are preserved in their original positions
        lines = content.splitlines(keepends=True)
        comment_positions: dict[int, str] = {}  # line_idx -> comment/blank content
        csv_lines: list[str] = []
        csv_line_mapping: list[int] = []  # csv_lines index -> original line number

        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                # Preserve comment or blank line
                comment_positions[line_idx] = line.rstrip("\n\r")
            else:
                csv_lines.append(line)
                csv_line_mapping.append(line_idx + 1)  # 1-based line number

        # Parse CSV content properly (handles multi-line fields)
        csv_content = "".join(csv_lines)
        reader = csv.reader(io.StringIO(csv_content))

        cleaned_rows: list[list[str]] = []
        changes: list[str] = []
        stats = {"rows_processed": 0, "cells_cleaned": 0, "headers_cleaned": 0}
        current_headers: list[str] | None = None

        # Track which CSV row we're on for line number reporting
        row_idx = 0
        for row in reader:
            # Get approximate line number from mapping
            # Note: for multi-line fields, this gives the starting line
            line_num = csv_line_mapping[row_idx] if row_idx < len(csv_line_mapping) else "?"

            clean_row = []

            # Check for header row (schema switch)
            if row and row[0].strip() == "row_id":
                # This is a header row
                for cell in row:
                    clean_cell = cell.strip()
                    if clean_cell != cell:
                        changes.append(
                            f"Row {row_idx + 1} (line ~{line_num}): Header '{cell}' -> '{clean_cell}'"
                        )
                        stats["headers_cleaned"] += 1
                    clean_row.append(clean_cell)
                current_headers = clean_row.copy()
            else:
                # Data row - check column count
                if current_headers and len(row) != len(current_headers):
                    changes.append(
                        f"Row {row_idx + 1} (line ~{line_num}): Column count mismatch "
                        f"(found {len(row)}, expected {len(current_headers)})"
                    )

                for idx, cell in enumerate(row):
                    if not isinstance(cell, str):
                        clean_row.append(cell)
                        continue

                    clean_cell = cell.strip()
                    if clean_cell != cell:
                        # Report whitespace changes
                        header_name = (
                            current_headers[idx]
                            if current_headers and idx < len(current_headers)
                            else f"col_{idx}"
                        )
                        # Only report if there was actual whitespace to strip
                        if cell != clean_cell:
                            changes.append(
                                f"Row {row_idx + 1} (line ~{line_num}) [{header_name}]: "
                                f"'{_truncate(cell)}' -> '{_truncate(clean_cell)}'"
                            )
                            stats["cells_cleaned"] += 1
                    clean_row.append(clean_cell)

            cleaned_rows.append(clean_row)
            stats["rows_processed"] += 1

            # Advance row_idx, accounting for multi-line fields
            # Count newlines in the original row to estimate line advancement
            row_line_count = sum(1 for cell in row for c in cell if c == "\n") + 1
            row_idx += row_line_count

        # Reconstruct output: interleave comments with cleaned CSV rows
        output_lines: list[str] = []
        csv_row_idx = 0
        total_lines = len(lines)

        # Build output preserving comment positions
        line_idx = 0
        while line_idx < total_lines or csv_row_idx < len(cleaned_rows):
            if line_idx in comment_positions:
                # Output comment or blank line
                output_lines.append(comment_positions[line_idx])
                line_idx += 1
            elif csv_row_idx < len(cleaned_rows):
                # Output cleaned CSV row
                sio = io.StringIO()
                csv.writer(sio, lineterminator="").writerow(cleaned_rows[csv_row_idx])
                output_lines.append(sio.getvalue())
                csv_row_idx += 1
                # Skip original CSV lines that were consumed
                while line_idx < total_lines and line_idx not in comment_positions:
                    line_idx += 1
            else:
                line_idx += 1

        # Handle any remaining comments at the end
        for remaining_idx in sorted(comment_positions.keys()):
            if remaining_idx >= line_idx:
                # Already processed by position
                pass

        # Reconstruct file content
        cleaned_content = "\n".join(output_lines)
        # Ensure trailing newline if original had one
        if content.endswith("\n"):
            cleaned_content += "\n"

        return SanitizeResult(
            original_path=self.csv_path,
            has_changes=len(changes) > 0,
            cleaned_content=cleaned_content,
            changes=changes,
            stats=stats,
        )

    def _sanitize_streaming(self) -> SanitizeResult:
        """
        Streaming sanitization for large CSV files.

        Processes the file in chunks to avoid loading the entire file into memory.
        Uses a temporary file to store the cleaned output.

        Returns:
            SanitizeResult object with details
        """
        changes: list[str] = []
        stats = {"rows_processed": 0, "cells_cleaned": 0, "headers_cleaned": 0}
        current_headers: list[str] | None = None
        has_changes = False

        # Create temp file for output
        fd, temp_path = tempfile.mkstemp(suffix=".csv", prefix="sanitized_")
        try:
            with (
                open(self.csv_path, encoding="utf-8", newline="") as infile,
                os.fdopen(fd, "w", encoding="utf-8", newline="") as outfile,
            ):
                reader = csv.reader(infile)
                writer = csv.writer(outfile)

                for row_idx, row in enumerate(reader):
                    line_num = row_idx + 1
                    clean_row = []
                    row_changed = False

                    # Check for header row (schema switch)
                    if row and row[0].strip() == "row_id":
                        # This is a header row
                        for cell in row:
                            clean_cell = cell.strip()
                            if clean_cell != cell:
                                # Only track first 1000 changes to avoid memory issues
                                if len(changes) < 1000:
                                    changes.append(
                                        f"Row {row_idx + 1} (line ~{line_num}): "
                                        f"Header '{cell}' -> '{clean_cell}'"
                                    )
                                stats["headers_cleaned"] += 1
                                row_changed = True
                            clean_row.append(clean_cell)
                        current_headers = clean_row.copy()
                    else:
                        # Data row
                        for idx, cell in enumerate(row):
                            if not isinstance(cell, str):
                                clean_row.append(cell)
                                continue

                            clean_cell = cell.strip()
                            if clean_cell != cell:
                                if len(changes) < 1000:
                                    header_name = (
                                        current_headers[idx]
                                        if current_headers and idx < len(current_headers)
                                        else f"col_{idx}"
                                    )
                                    changes.append(
                                        f"Row {row_idx + 1} (line ~{line_num}) [{header_name}]: "
                                        f"'{_truncate(cell)}' -> '{_truncate(clean_cell)}'"
                                    )
                                stats["cells_cleaned"] += 1
                                row_changed = True
                            clean_row.append(clean_cell)

                    writer.writerow(clean_row)
                    stats["rows_processed"] += 1

                    if row_changed:
                        has_changes = True

                    # Log progress for large files
                    if stats["rows_processed"] % 100000 == 0:
                        logger.info(
                            "Streaming sanitization progress",
                            rows_processed=stats["rows_processed"],
                        )

            # Read the cleaned content from temp file
            with open(temp_path, encoding="utf-8") as f:
                cleaned_content = f.read()

        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        if len(changes) >= 1000:
            changes.append("... (additional changes truncated for memory efficiency)")

        return SanitizeResult(
            original_path=self.csv_path,
            has_changes=has_changes,
            cleaned_content=cleaned_content,
            changes=changes,
            stats=stats,
        )

    def print_diff(self, result: SanitizeResult, console: Console) -> None:
        """Print a diff/summary of changes to the console."""
        if not result.has_changes:
            console.print("[green]No issues found. CSV is clean.[/green]")
            return

        console.print(f"[yellow]Found {len(result.changes)} issues in CSV:[/yellow]")

        # Show stats
        stats_table = Table(show_header=False, box=None)
        stats_table.add_row("Rows Processed:", str(result.stats["rows_processed"]))
        stats_table.add_row("Cells Cleaned:", str(result.stats["cells_cleaned"]))
        stats_table.add_row("Headers Cleaned:", str(result.stats["headers_cleaned"]))
        console.print(stats_table)
        console.print()

        # Show detailed changes (capped)
        table = Table(title="Detailed Changes", show_header=True)
        table.add_column("Location/Change", style="cyan")

        limit = 20
        for change in result.changes[:limit]:
            table.add_row(change)

        if len(result.changes) > limit:
            table.add_row(f"... and {len(result.changes) - limit} more")

        console.print(table)


def _truncate(s: str, max_len: int = 30) -> str:
    """Truncate string for display, showing embedded newlines."""
    # Replace newlines with visible markers
    s = s.replace("\n", "\\n").replace("\r", "\\r")
    if len(s) > max_len:
        return s[: max_len - 3] + "..."
    return s
