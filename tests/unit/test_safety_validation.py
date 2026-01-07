"""Tests for safety validation features."""

import pytest

from src.importer.models.operations import Operation, OperationType
from src.importer.utils.exceptions import ValidationError
from src.importer.validation.safety import (
    check_csv_for_dangerous_operations,
    validate_operation_safety,
)


class TestSafetyValidation:
    """Test safety validation for dangerous operations."""

    def test_validate_operation_safety_safe_operations(self):
        """Test that safe operations pass validation."""
        safe_operations = [
            Operation(
                row_id=1,
                operation_type=OperationType.DELETE,
                object_type="ip4_address",
                resource_id=123,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=2,
                operation_type=OperationType.DELETE,
                object_type="host_record",
                resource_id=456,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=3,
                operation_type=OperationType.CREATE,
                object_type="configuration",  # Creates are safe
                resource_id=None,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=4,
                operation_type=OperationType.UPDATE,
                object_type="view",  # Updates are safe
                resource_id=789,
                payload={},
                csv_row={},
            ),
        ]

        # Should not raise any errors
        validate_operation_safety(safe_operations, allow_dangerous_operations=False)
        validate_operation_safety(safe_operations, allow_dangerous_operations=True)

    def test_validate_operation_safety_block_critical_operations(self):
        """Test that critical operations (config/view) are ALWAYS blocked."""
        critical_operations = [
            Operation(
                row_id=1,
                operation_type=OperationType.DELETE,
                object_type="configuration",
                resource_id=123,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=2,
                operation_type=OperationType.DELETE,
                object_type="view",
                resource_id=456,
                payload={},
                csv_row={},
            ),
        ]

        # Config/view deletion is now ALWAYS blocked (ABSOLUTE SAFETY VIOLATION)
        with pytest.raises(ValidationError) as exc_info:
            validate_operation_safety(critical_operations, allow_dangerous_operations=False)

        assert "ABSOLUTE SAFETY VIOLATION" in str(exc_info.value)
        assert "configuration" in str(exc_info.value)
        assert "PERMANENTLY BLOCKED" in str(exc_info.value)

    def test_validate_operation_safety_block_high_risk_operations(self):
        """Test that high-risk operations are blocked by default."""
        high_risk_operations = [
            Operation(
                row_id=1,
                operation_type=OperationType.DELETE,
                object_type="ip4_block",
                resource_id=123,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=2,
                operation_type=OperationType.DELETE,
                object_type="ip4_network",
                resource_id=456,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=3,
                operation_type=OperationType.DELETE,
                object_type="dns_zone",
                resource_id=789,
                payload={},
                csv_row={},
            ),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validate_operation_safety(high_risk_operations, allow_dangerous_operations=False)

        assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)
        assert "ip4_block" in str(exc_info.value)
        assert "ip4_network" in str(exc_info.value)
        assert "dns_zone" in str(exc_info.value)
        assert "--allow-dangerous-operations" in str(exc_info.value)

    def test_validate_operation_safety_allow_dangerous_operations(self):
        """Test that high-risk operations (not config/view) are allowed with flag."""
        # Config/view are now NEVER allowed, so we test with other protected types
        dangerous_operations = [
            Operation(
                row_id=1,
                operation_type=OperationType.DELETE,
                object_type="ip4_block",
                resource_id=789,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=2,
                operation_type=OperationType.DELETE,
                object_type="ip4_network",
                resource_id=101112,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=3,
                operation_type=OperationType.DELETE,
                object_type="dns_zone",
                resource_id=131415,
                payload={},
                csv_row={},
            ),
        ]

        # Should not raise errors when flag is True
        validate_operation_safety(dangerous_operations, allow_dangerous_operations=True)

    def test_validate_operation_safety_multiple_dangerous_operations(self):
        """Test validation with multiple dangerous operations (high-risk types only)."""
        # Using high-risk types (not config/view) to test multiple ops
        dangerous_operations = [
            Operation(
                row_id=1,
                operation_type=OperationType.DELETE,
                object_type="ip4_block",
                resource_id=123,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=2,
                operation_type=OperationType.DELETE,
                object_type="ip4_network",
                resource_id=456,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=3,
                operation_type=OperationType.DELETE,
                object_type="ip4_address",  # This one is safe
                resource_id=789,
                payload={},
                csv_row={},
            ),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validate_operation_safety(dangerous_operations, allow_dangerous_operations=False)

        error_msg = str(exc_info.value)
        assert "2 dangerous operation" in error_msg
        assert "Row 1: DELETE ip4_block" in error_msg
        assert "Row 2: DELETE ip4_network" in error_msg
        assert "Row 3: DELETE ip4_address" not in error_msg

    def test_check_csv_for_dangerous_operations_safe_csv(self):
        """Test that safe CSV data passes validation."""
        safe_csv_data = [
            {
                "row_id": 1,
                "object_type": "ip4_address",
                "action": "delete",
                "name": "test-address",
            },
            {
                "row_id": 2,
                "object_type": "host_record",
                "action": "delete",
                "name": "test-host",
            },
            {
                "row_id": 3,
                "object_type": "configuration",
                "action": "create",
                "name": "test-config",
            },
            {
                "row_id": 4,
                "object_type": "ip4_block",
                "action": "update",
                "name": "test-block",
            },
            {
                "row_id": 5,
                "object_type": "ip4_network",
                "action": "create",
                "name": "test-network",
            },
            {
                "row_id": 6,
                "object_type": "dns_zone",
                "action": "update",
                "name": "test-zone",
            },
        ]

        # Should not raise any errors
        check_csv_for_dangerous_operations(safe_csv_data, allow_dangerous_operations=False)
        check_csv_for_dangerous_operations(safe_csv_data, allow_dangerous_operations=True)

    def test_check_csv_for_dangerous_operations_block_dangerous_csv(self):
        """Test that dangerous CSV operations are blocked (hits ABSOLUTE block first)."""
        dangerous_csv_data = [
            {
                "row_id": 1,
                "object_type": "configuration",
                "action": "delete",
                "name": "production-config",
            },
            {
                "row_id": 2,
                "object_type": "view",
                "action": "delete",
                "name": "production-view",
            },
        ]

        with pytest.raises(ValidationError) as exc_info:
            check_csv_for_dangerous_operations(dangerous_csv_data, allow_dangerous_operations=False)

        # Config/view deletion triggers ABSOLUTE blocking first
        error_msg = str(exc_info.value)
        assert "ABSOLUTE SAFETY VIOLATION" in error_msg
        assert "configuration" in error_msg
        assert "PERMANENTLY BLOCKED" in error_msg

    def test_check_csv_for_dangerous_operations_allow_dangerous_csv(self):
        """Test that high-risk CSV operations (not config/view) are allowed with flag."""
        # Config/view are NEVER allowed, so we test with other protected types
        dangerous_csv_data = [
            {
                "row_id": 1,
                "object_type": "ip4_block",
                "action": "delete",
                "name": "test-block",
            },
            {
                "row_id": 2,
                "object_type": "dns_zone",
                "action": "delete",
                "name": "test-zone",
            },
        ]

        # Should not raise errors when flag is True
        check_csv_for_dangerous_operations(dangerous_csv_data, allow_dangerous_operations=True)

    def test_check_csv_for_dangerous_operations_case_insensitive(self):
        """Test that object type matching is case insensitive."""
        dangerous_csv_data = [
            {
                "row_id": 1,
                "object_type": "CONFIGURATION",  # Uppercase
                "action": "DELETE",  # Uppercase
                "name": "test-config",
            },
        ]

        with pytest.raises(ValidationError) as exc_info:
            check_csv_for_dangerous_operations(dangerous_csv_data, allow_dangerous_operations=False)

        # Config deletion triggers ABSOLUTE blocking
        assert "ABSOLUTE SAFETY VIOLATION" in str(exc_info.value)

    def test_validate_operation_safety_empty_operations(self):
        """Test that empty operation lists pass validation."""
        validate_operation_safety([], allow_dangerous_operations=False)
        validate_operation_safety([], allow_dangerous_operations=True)

    def test_check_csv_for_dangerous_operations_empty_csv(self):
        """Test that empty CSV data passes validation."""
        check_csv_for_dangerous_operations([], allow_dangerous_operations=False)
        check_csv_for_dangerous_operations([], allow_dangerous_operations=True)

    def test_validate_operation_safety_mixed_safe_and_dangerous(self):
        """Test validation with mixed safe and config delete operations."""
        mixed_operations = [
            Operation(
                row_id=1,
                operation_type=OperationType.DELETE,
                object_type="ip4_address",  # Safe
                resource_id=123,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=2,
                operation_type=OperationType.DELETE,
                object_type="configuration",  # ABSOLUTE BLOCKED
                resource_id=456,
                payload={},
                csv_row={},
            ),
            Operation(
                row_id=3,
                operation_type=OperationType.CREATE,
                object_type="ip4_network",  # Safe
                resource_id=None,
                payload={},
                csv_row={},
            ),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validate_operation_safety(mixed_operations, allow_dangerous_operations=False)

        error_msg = str(exc_info.value)
        # ABSOLUTE block for config/view triggers first
        assert "ABSOLUTE SAFETY VIOLATION" in error_msg
        assert "Row 2: DELETE configuration" in error_msg
        assert "Row 1: DELETE ip4_address" not in error_msg
        assert "Row 3: CREATE ip4_network" not in error_msg
