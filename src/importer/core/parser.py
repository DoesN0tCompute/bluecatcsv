"""CSV parser with schema validation.

Overview:
--------
The CSVParser reads CSV files and converts rows into strongly-typed Pydantic
models (CSVRow discriminated unions). This provides validation, type safety,
and clean error messages for malformed input.

Key Features:
------------
1. Dynamic Schema Switching - CSV can contain multiple object types, each with
   different columns. When a row starts with "row_id", it's treated as a new
   header line that defines the schema for subsequent rows.

2. Discriminated Union Models - The object_type field determines which Pydantic
   model is used for validation (IP4BlockRow, HostRecordRow, etc.)

3. Strict vs Non-Strict Modes:
   - strict=True: Fail on first error (for CI/validation)
   - strict=False: Collect all errors (for user feedback)

4. Comment Support - Lines starting with '#' are ignored

5. Extra Fields - Fields not in the model are preserved (useful for UDFs)

CSV Format:
----------
Standard format with headers on first line:
```
row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,10.0.0.0/8,Production
2,ip4_network,create,Default,10.1.0.0/24,Servers
```

Multi-type format (schema switch on header rows):
```
row_id,object_type,action,config,cidr,name
1,ip4_block,create,Default,10.0.0.0/8,Production
row_id,object_type,action,config,view_path,zone_name
2,dns_zone,create,Default,Internal,example.com
```

Error Handling:
--------------
- FileNotFoundError: CSV file doesn't exist
- CSVValidationError: Row fails Pydantic validation
- Duplicate row_id detection and warning
- Clear line numbers in error messages
"""

import csv
import io
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import structlog
from pydantic import ValidationError

from ..constants import SUPPORTED_CSV_VERSIONS
from ..models.csv_row import CSVRow
from ..utils.exceptions import CSVValidationError

logger = structlog.get_logger(__name__)


class CSVParser:
    """
    Parse CSV files into validated Pydantic models.

    Features:
    - Column order doesn't matter (uses DictReader with headers)
    - _version field is optional (defaults to "3.0")
    - Missing optional fields get default values
    - Extra fields are preserved (for UDFs)
    - Whitespace is automatically stripped from all string fields
    """

    def __init__(self, csv_path: Path) -> None:
        """
        Initialize parser with CSV file path.

        Args:
            csv_path: Path to CSV file to parse
        """
        self.csv_path = csv_path
        self.rows_parsed = 0
        self.errors: list[CSVValidationError] = []
        self._file_handle: Any | None = None
        self._reader: csv.reader | None = None
        self._line_number: int = 0
        self._current_headers: list[str] | None = None
        self._all_lines: list[list[str]] = []

    def parse(self, strict: bool = True) -> list[CSVRow]:
        """
        Parse CSV file into validated row models.

        Args:
            strict: If True, raise on first error. If False, collect all errors.

        Returns:
            List of validated CSVRow objects

        Raises:
            CSVValidationError: If rows fail Pydantic validation (in strict mode)
            FileNotFoundError: If CSV file doesn't exist
        """
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        logger.info("Starting CSV parse", csv_path=str(self.csv_path))

        rows: list[CSVRow] = []
        self.errors = []
        seen_row_ids: dict[Any, int] = {}  # Map row_id -> line_number

        with open(self.csv_path, encoding="utf-8-sig") as f:
            # Read all lines
            lines = f.readlines()

            # Filter out comment lines and strip whitespace
            non_comment_lines = [line for line in lines if not line.strip().startswith("#")]

            if not non_comment_lines:
                logger.warning("empty_csv", message="CSV file is empty or contains only comments")
                return []

            # Create a new string-like object from filtered lines
            csv_content = "".join(non_comment_lines)

            # Using csv.reader instead of DictReader to support dynamic header switches
            # This allows CSV files to change schemas mid-file (e.g., mixing different object types)
            reader = csv.reader(io.StringIO(csv_content))

            current_headers = None
            rows: list[CSVRow] = []
            seen_row_ids: dict[Any, int] = {}

            for line_num, row_list in enumerate(reader, start=1):
                # 1. Header Detection
                # Dynamic schema switching allows different CSV sections to have different columns
                # Header lines are identified by 'row_id' in the first column (required field)
                # This enables multi-type CSV files without pre-defining all columns
                if row_list and row_list[0].strip().lstrip("*") == "row_id":
                    current_headers = [h.strip().lstrip("*") for h in row_list]
                    logger.debug("Schema switch detected", headers=current_headers, line=line_num)
                    continue

                # 2. Skip completely empty rows
                if not row_list or all(not cell.strip() for cell in row_list):
                    continue

                # 3. Safety Check: Data found before any header
                if current_headers is None:
                    if strict:
                        raise CSVValidationError(
                            f"Line {line_num}: Data found before header definition"
                        )
                    continue

                # 4. Process Data Row
                try:
                    # Check for column count mismatch
                    if len(row_list) != len(current_headers):
                        logger.warning(
                            "Column count mismatch",
                            line=line_num,
                            expected=len(current_headers),
                            actual=len(row_list),
                            extra_columns=(
                                row_list[len(current_headers) :]
                                if len(row_list) > len(current_headers)
                                else None
                            ),
                        )

                    # Create the dictionary expected by the validation logic
                    # Pad row_list if shorter than headers, truncate if longer
                    padded_row = row_list[: len(current_headers)]
                    while len(padded_row) < len(current_headers):
                        padded_row.append("")
                    row_dict = dict(zip(current_headers, padded_row, strict=True))

                    # Clean empty string values to None
                    cleaned = self._clean_row_dict(row_dict)

                    # Validate version if present (but make it optional)
                    if "_version" in cleaned and cleaned["_version"] not in SUPPORTED_CSV_VERSIONS:
                        logger.warning(
                            "Unsupported CSV version",
                            line=line_num,
                            version=cleaned["_version"],
                            supported=list(SUPPORTED_CSV_VERSIONS),
                        )

                    # Pydantic discriminated union automatically picks correct model
                    row = self._validate_row(cleaned)

                    # Check for duplicate row_id with detailed reporting
                    if row.row_id in seen_row_ids:
                        first_line = seen_row_ids[row.row_id]
                        error = CSVValidationError(
                            f"Duplicate row_id '{row.row_id}' "
                            f"(first occurrence on line {first_line}, duplicate on line {line_num})",
                            line_number=line_num,
                        )
                        if strict:
                            logger.error(
                                "CSV validation failed - duplicate row_id",
                                line=line_num,
                                row_id=row.row_id,
                            )
                            raise error
                        self.errors.append(error)
                        continue

                    seen_row_ids[row.row_id] = line_num
                    rows.append(row)
                    self.rows_parsed += 1

                except ValidationError as e:
                    error = CSVValidationError(
                        f"Line {line_num}: {self._format_validation_error(e)}",
                        line_number=line_num,
                        original_error=e,
                    )
                    if strict:
                        raise error from e
                    self.errors.append(error)

                except Exception as e:
                    error = CSVValidationError(
                        f"Line {line_num}: Unexpected error: {e}",
                        line_number=line_num,
                        original_error=e,
                    )
                    if strict:
                        raise error from e
                    self.errors.append(error)

        if self.rows_parsed == 0:
            logger.warning(
                "CSV file is empty or contains only headers", csv_path=str(self.csv_path)
            )
            if strict:
                logger.debug("Strict mode: Accepting empty CSV as valid no-op")

        logger.info(
            "CSV parse complete",
            rows_parsed=self.rows_parsed,
            errors=len(self.errors),
            csv_path=str(self.csv_path),
        )

        return rows

    def _clean_row_dict(self, row_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Clean row dictionary by converting empty strings to None and stripping whitespace.

        Args:
            row_dict: Raw row dictionary from CSV reader

        Returns:
            Cleaned dictionary
        """
        cleaned = {}
        # Fields that should allow empty strings (for clearing values or semantic meaning)
        # These correspond to fields using strip_whitespace_preserve_empty
        # Note: "name" is preserved for DNS apex records (empty or "@" means zone apex)
        PRESERVE_EMPTY_FIELDS = {"description", "parent_code", "name"}

        for k, v in row_dict.items():
            if isinstance(v, str):
                v = v.strip()

            if k in PRESERVE_EMPTY_FIELDS:
                # For these fields, keep "" as "" (unless it was purely whitespace, which strip handles)
                cleaned[k] = v
            else:
                # For all other fields, convert "" to None
                cleaned[k] = v if v != "" else None

        return cleaned

    def _validate_row(self, cleaned: dict[str, Any]) -> CSVRow:
        """
        Validate a single row using Pydantic discriminated union.

        Args:
            cleaned: Cleaned row dictionary

        Returns:
            Validated CSVRow object

        Raises:
            ValidationError: If validation fails
        """
        # Check for required discriminator field
        if "object_type" not in cleaned or not cleaned["object_type"]:
            raise ValidationError.from_exception_data(
                "value_error",
                [
                    {
                        "type": "missing",
                        "loc": ("object_type",),
                        "msg": "Field required: object_type is required for discriminated union",
                        "input": cleaned,
                    }
                ],
            )

        # Pydantic v2 will automatically select the right model based on object_type
        from pydantic import TypeAdapter

        adapter = TypeAdapter(CSVRow)
        return adapter.validate_python(cleaned)

    def _format_validation_error(self, error: ValidationError) -> str:
        """
        Format Pydantic validation error into human-readable message.

        Args:
            error: Pydantic ValidationError

        Returns:
            Formatted error message
        """
        errors = error.errors()
        if not errors:
            return str(error)

        # Format first error (most relevant)
        first_error = errors[0]
        field = ".".join(str(loc) for loc in first_error["loc"])
        msg = first_error["msg"]

        if len(errors) > 1:
            return f"{field}: {msg} (and {len(errors) - 1} more errors)"
        else:
            return f"{field}: {msg}"

    def get_error_summary(self) -> str:
        """
        Get a summary of all errors encountered during parsing.

        Returns:
            Human-readable error summary
        """
        if not self.errors:
            return "No errors"

        summary = [f"Found {len(self.errors)} errors:"]
        for error in self.errors[:10]:  # Show first 10
            summary.append(f"  - Line {error.line_number}: {error}")

        if len(self.errors) > 10:
            summary.append(f"  ... and {len(self.errors) - 10} more errors")

        return "\n".join(summary)

    # Streaming methods for memory-efficient processing

    def __aiter__(self):
        """Make CSVParser an async iterator for streaming processing."""
        return self

    async def __anext__(self) -> CSVRow:
        """
        Yield one validated CSV row at a time.

        This method enables memory-efficient processing of large CSV files
        by yielding rows one by one instead of loading the entire file into memory.
        Supports multi-header CSVs with dynamic schema switching.

        Returns:
            Validated CSVRow object

        Raises:
            StopAsyncIteration: When all rows have been processed
            CSVValidationError: If strict mode is enabled and validation fails
        """
        if self._reader is None:
            # Initialize the reader on first iteration
            await self._initialize_streaming_reader()

        # Get the next row from the CSV reader
        while True:
            try:
                row_list = next(self._reader)
                self._line_number += 1

                # Skip completely empty rows
                if not row_list or all(not cell.strip() for cell in row_list):
                    continue

                # Check for header switch
                if row_list and row_list[0].strip().lstrip("*") == "row_id":
                    self._current_headers = [h.strip().lstrip("*") for h in row_list]
                    logger.debug(
                        "Schema switch detected in streaming",
                        headers=self._current_headers,
                        line=self._line_number,
                    )
                    continue

                # Safety check: Data before header
                if self._current_headers is None:
                    if hasattr(self, "_strict_mode") and self._strict_mode:
                        raise CSVValidationError(
                            f"Line {self._line_number}: Data found before header definition"
                        )
                    continue

                # Validate and process the row
                try:
                    # Create row dictionary from current headers
                    # Pad row_list if shorter than headers, truncate if longer
                    padded_row = row_list[: len(self._current_headers)]
                    while len(padded_row) < len(self._current_headers):
                        padded_row.append("")
                    row_dict = dict(zip(self._current_headers, padded_row, strict=True))

                    # Clean empty string values to None
                    cleaned = self._clean_row_dict(row_dict)

                    # Validate version if present (but make it optional)
                    if "_version" in cleaned and cleaned["_version"] not in SUPPORTED_CSV_VERSIONS:
                        logger.warning(
                            "Unsupported CSV version",
                            line=self._line_number,
                            version=cleaned["_version"],
                            supported=list(SUPPORTED_CSV_VERSIONS),
                        )

                    # Pydantic discriminated union automatically picks correct model
                    # based on object_type field
                    row = self._validate_row(cleaned)

                    self.rows_parsed += 1
                    return row

                except ValidationError as e:
                    error = CSVValidationError(
                        f"Line {self._line_number}: {self._format_validation_error(e)}",
                        line_number=self._line_number,
                    )

                    # In strict mode, raise immediately
                    if hasattr(self, "_strict_mode") and self._strict_mode:
                        logger.error(
                            "CSV row validation failed",
                            line=self._line_number,
                            error=str(error),
                        )
                        raise error from e

                    # In non-strict mode, collect errors and continue
                    self.errors.append(error)
                    logger.warning(
                        "CSV row validation failed (continuing)",
                        line=self._line_number,
                        error=str(error),
                    )
                    # Continue to next row
                    continue

                except Exception as e:
                    error = CSVValidationError(
                        f"Line {self._line_number}: Unexpected error: {e}",
                        line_number=self._line_number,
                        original_error=e,
                    )

                    if hasattr(self, "_strict_mode") and self._strict_mode:
                        logger.error(
                            "Unexpected CSV parsing error", line=self._line_number, error=str(e)
                        )
                        raise error from e

                    self.errors.append(error)
                    logger.warning(
                        "Unexpected error parsing CSV row (continuing)",
                        line=self._line_number,
                        error=str(e),
                    )
                    # Continue to next row
                    continue

            except StopIteration:
                # End of CSV file
                await self._cleanup_streaming_reader()
                raise StopAsyncIteration from None

    async def _initialize_streaming_reader(self) -> None:
        """Initialize the streaming CSV reader."""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        logger.debug("Initializing streaming CSV reader", csv_path=str(self.csv_path))

        # Open file for reading
        self._file_handle = open(self.csv_path, encoding="utf-8-sig")

        # Create a generator that filters comment lines on-the-fly
        # This avoids loading the entire file into memory
        def filter_comments(file_handle: Any) -> Any:
            """Generator that yields non-comment lines from file."""
            for line in file_handle:
                if not line.strip().startswith("#"):
                    yield line

        # Use csv.reader with the filtering generator for true streaming
        # This reads lines one at a time instead of loading everything into memory
        self._reader = csv.reader(filter_comments(self._file_handle))
        self._current_headers = None
        self._line_number = 0  # Reset line counter

    async def _cleanup_streaming_reader(self) -> None:
        """Clean up streaming resources."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
            self._reader = None

        logger.info(
            "Streaming CSV parse complete",
            rows_parsed=self.rows_parsed,
            errors=len(self.errors),
            csv_path=str(self.csv_path),
        )

    async def parse_stream(self, strict: bool = True) -> AsyncGenerator[CSVRow, None]:
        """
        Parse CSV file as a stream, yielding one validated row at a time.

        This method provides memory-efficient processing for large CSV files.
        Each row is validated and yielded immediately without storing all rows in memory.

        Args:
            strict: If True, raise on first error. If False, collect all errors and continue.

        Yields:
            Validated CSVRow objects one at a time

        Raises:
            CSVValidationError: If rows fail validation in strict mode
            FileNotFoundError: If CSV file doesn't exist
        """
        self._strict_mode = strict
        self.errors = []
        self.rows_parsed = 0

        logger.info("Starting streaming CSV parse", csv_path=str(self.csv_path))

        try:
            # Use the async iterator protocol
            async for row in self:
                yield row

        except Exception:
            await self._cleanup_streaming_reader()
            raise
        finally:
            # Ensure cleanup happens even if iteration is interrupted
            await self._cleanup_streaming_reader()
