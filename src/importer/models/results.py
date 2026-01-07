"""Result types for import operations."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .operations import FieldChange, OperationType


@dataclass
class DiffResult:
    """
    Result of comparing desired state vs current state.

    Attributes:
        operation: Type of operation needed (create/update/delete/noop)
        resource_id: BAM resource ID (None for creates)
        field_changes: Dictionary of field changes for updates
        conflict_detected: Whether a conflict was detected
        conflict_reason: Reason for conflict if detected
        metadata: Additional metadata about the diff
    """

    operation: OperationType
    resource_id: int | None
    field_changes: dict[str, FieldChange] = field(default_factory=dict)
    conflict_detected: bool = False
    conflict_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """
        Check if there are any field changes.

        Returns:
            bool: True if there are changes, False otherwise.
        """
        return len(self.field_changes) > 0

    def get_change_summary(self) -> str:
        """
        Get a human-readable summary of changes.

        Returns:
            str: Summary of changes or 'No changes'.
        """
        if not self.field_changes:
            return "No changes"
        changes = [str(change) for change in self.field_changes.values()]
        return ", ".join(changes)


@dataclass
class OperationResult:
    """
    Result of executing a single operation.

    Attributes:
        row_id: CSV row identifier
        operation: Type of operation
        success: Whether operation succeeded
        resource_id: BAM resource ID (if applicable)
        error_message: Error details if failed
        duration_ms: Operation duration in milliseconds
        before_state: State before operation
        after_state: State after operation
    """

    row_id: str | int
    operation: OperationType
    success: bool
    resource_id: int | None = None
    error_message: str | None = None
    duration_ms: float | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportResult:
    """
    Overall result of an import operation.

    Attributes:
        batch_id: Unique batch identifier
        total_operations: Total number of operations
        succeeded: Number of successful operations
        failed: Number of failed operations
        skipped: Number of skipped operations
        duration_seconds: Total duration in seconds
        changelog_path: Path to changelog database
        rollback_csv_path: Path to rollback CSV (if generated)
        operation_results: Individual operation results
        started_at: Start timestamp
        completed_at: Completion timestamp
    """

    batch_id: str
    total_operations: int
    succeeded: int
    failed: int
    skipped: int
    duration_seconds: float
    changelog_path: Path | None = None
    rollback_csv_path: Path | None = None
    operation_results: list[OperationResult] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def success_rate(self) -> float:
        """
        Calculate success rate as percentage.

        Returns:
            float: Success rate percentage (0.0 to 100.0).
        """
        if self.total_operations == 0:
            return 0.0
        return (self.succeeded / self.total_operations) * 100

    @property
    def is_complete_success(self) -> bool:
        """
        Check if all operations succeeded.

        Returns:
            bool: True if no failures and no skipped operations, False otherwise.
        """
        return self.failed == 0 and self.skipped == 0

    def get_summary(self) -> str:
        """
        Get a human-readable summary.

        Returns:
            str: Summary string with batch ID, counts, and success rate.
        """
        return (
            f"Batch {self.batch_id}: "
            f"{self.succeeded}/{self.total_operations} succeeded, "
            f"{self.failed} failed, {self.skipped} skipped "
            f"({self.success_rate:.1f}% success rate)"
        )


@dataclass
class RollbackManifest:
    """
    Metadata for a rollback operation.

    Attributes:
        original_batch_id: Batch ID of original import
        rollback_csv: Path to rollback CSV file
        total_operations: Number of rollback operations
        created_at: When rollback was generated
        original_changelog: Path to original changelog
    """

    original_batch_id: str
    rollback_csv: Path
    total_operations: int
    created_at: datetime
    original_changelog: Path
