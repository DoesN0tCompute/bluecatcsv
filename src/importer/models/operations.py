"""Operation types and models."""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .csv_row import CSVRow


class OperationType(str, Enum):
    """Type of operation to perform."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NOOP = "noop"
    ORPHAN = "orphan"


class OperationStatus(str, Enum):
    """Status of an operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Operation:
    """
    Represents a single operation to be executed.

    Attributes:
        row_id: Unique identifier from CSV (can be int or str)
        operation_type: Type of operation (create/update/delete)
        object_type: BAM object type
        resource_id: BAM resource ID (None for creates)
        payload: Data to send to BAM
        csv_row: Original CSV row data
        status: Current operation status
        error_message: Error details if failed
        dependency_level: Execution level (for ordering)
    """

    row_id: str | int
    operation_type: OperationType
    object_type: str
    resource_id: int | None
    payload: dict[str, Any]
    csv_row: "CSVRow"
    status: OperationStatus = OperationStatus.PENDING
    error_message: str | None = None
    dependency_level: int | None = None

    def mark_success(self) -> None:
        """Mark operation as succeeded."""
        self.status = OperationStatus.SUCCEEDED

    def mark_failure(self, error: str) -> None:
        """
        Mark operation as failed with error message.

        Args:
            error: The error message explaining the failure.
        """
        self.status = OperationStatus.FAILED
        self.error_message = error

    def mark_skipped(self, reason: str) -> None:
        """
        Mark operation as skipped.

        Args:
            reason: The reason why the operation was skipped.
        """
        self.status = OperationStatus.SKIPPED
        self.error_message = reason


@dataclass
class FieldChange:
    """
    Represents a change to a single field.

    Attributes:
        field_name: Name of the field being changed.
        old_value: The original value of the field.
        new_value: The new value of the field.
    """

    field_name: str
    old_value: Any
    new_value: Any

    def __str__(self) -> str:
        """
        Human-readable string representation.

        Returns:
            str: A string describing the change (e.g., "name: old -> new").
        """
        return f"{self.field_name}: {self.old_value} → {self.new_value}"
