"""Tests for DeferredResolutionError and deferred ID resolution in executor.

These tests verify that the executor properly raises DeferredResolutionError
when deferred dependencies cannot be resolved (Fix 1.2).
"""

import pytest
from importer.config import PolicyConfig
from importer.execution.executor import OperationExecutor
from importer.models.operations import Operation, OperationType
from importer.utils.exceptions import DeferredResolutionError


class MockBAMClient:
    """Mock BAM client for testing."""

    pass


class TestDeferredResolutionError:
    """Tests for DeferredResolutionError exception."""

    def test_exception_attributes(self) -> None:
        """Test that exception has correct attributes."""
        error = DeferredResolutionError(
            row_id="row_1",
            resource_type="block",
            deferred_key="_deferred_block_cidr",
            deferred_value="10.0.0.0/8",
        )

        assert error.row_id == "row_1"
        assert error.resource_type == "block"
        assert error.deferred_key == "_deferred_block_cidr"
        assert error.deferred_value == "10.0.0.0/8"

    def test_exception_message(self) -> None:
        """Test that exception message is descriptive."""
        error = DeferredResolutionError(
            row_id="row_5",
            resource_type="network",
            deferred_key="_deferred_network_cidr",
            deferred_value="10.1.0.0/24",
        )

        message = str(error)
        assert "Critical Dependency Failure" in message
        assert "network" in message
        assert "10.1.0.0/24" in message
        assert "row_5" in message
        assert "failed or was skipped" in message


class TestExecutorDeferredResolution:
    """Tests for deferred ID resolution in OperationExecutor."""

    @pytest.fixture
    def executor(self) -> OperationExecutor:
        """Create an executor with mock client."""
        client = MockBAMClient()
        policy = PolicyConfig()
        return OperationExecutor(client, policy)

    def test_resolve_deferred_block_success(self, executor: OperationExecutor) -> None:
        """Test successful resolution of deferred block ID."""
        # Pre-register a created block
        executor.created_blocks["10.0.0.0/8"] = 12345

        # Create an operation that needs this block
        operation = Operation(
            row_id="row_1",
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            resource_id=None,
            payload={"_deferred_block_cidr": "10.0.0.0/8", "name": "Test Network"},
            csv_row=None,
        )

        # Resolve deferred IDs
        executor._resolve_deferred_ids(operation)

        # Verify block_id was resolved
        assert operation.payload["block_id"] == 12345
        # Deferred key is removed after successful resolution
        assert "_deferred_block_cidr" not in operation.payload

    def test_resolve_deferred_block_failure(self, executor: OperationExecutor) -> None:
        """Test that missing deferred block raises DeferredResolutionError."""
        # Don't register any blocks - the block wasn't created
        operation = Operation(
            row_id="row_2",
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            resource_id=None,
            payload={"_deferred_block_cidr": "10.0.0.0/8", "name": "Test Network"},
            csv_row=None,
        )

        with pytest.raises(DeferredResolutionError) as exc_info:
            executor._resolve_deferred_ids(operation)

        error = exc_info.value
        assert error.row_id == "row_2"
        assert error.resource_type == "block"
        assert error.deferred_value == "10.0.0.0/8"

    def test_resolve_deferred_network_success(self, executor: OperationExecutor) -> None:
        """Test successful resolution of deferred network ID."""
        executor.created_networks["10.1.0.0/24"] = 67890

        operation = Operation(
            row_id="row_3",
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"_deferred_network_cidr": "10.1.0.0/24", "address": "10.1.0.10"},
            csv_row=None,
        )

        executor._resolve_deferred_ids(operation)

        assert operation.payload["network_id"] == 67890

    def test_resolve_deferred_network_failure(self, executor: OperationExecutor) -> None:
        """Test that missing deferred network raises DeferredResolutionError."""
        operation = Operation(
            row_id="row_4",
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"_deferred_network_cidr": "10.1.0.0/24", "address": "10.1.0.10"},
            csv_row=None,
        )

        with pytest.raises(DeferredResolutionError) as exc_info:
            executor._resolve_deferred_ids(operation)

        error = exc_info.value
        assert error.resource_type == "network"
        assert error.deferred_value == "10.1.0.0/24"

    def test_resolve_deferred_zone_success(self, executor: OperationExecutor) -> None:
        """Test successful resolution of deferred zone ID."""
        executor.created_zones["example.com"] = 11111

        operation = Operation(
            row_id="row_5",
            operation_type=OperationType.CREATE,
            object_type="host_record",
            resource_id=None,
            payload={"_deferred_zone_name": "example.com", "name": "www"},
            csv_row=None,
        )

        executor._resolve_deferred_ids(operation)

        assert operation.payload["zone_id"] == 11111

    def test_resolve_deferred_zone_failure(self, executor: OperationExecutor) -> None:
        """Test that missing deferred zone raises DeferredResolutionError."""
        operation = Operation(
            row_id="row_6",
            operation_type=OperationType.CREATE,
            object_type="host_record",
            resource_id=None,
            payload={"_deferred_zone_name": "missing.com", "name": "www"},
            csv_row=None,
        )

        with pytest.raises(DeferredResolutionError) as exc_info:
            executor._resolve_deferred_ids(operation)

        error = exc_info.value
        assert error.resource_type == "zone"
        assert error.deferred_value == "missing.com"

    def test_no_deferred_ids_no_error(self, executor: OperationExecutor) -> None:
        """Test that operations without deferred IDs don't raise errors."""
        operation = Operation(
            row_id="row_7",
            operation_type=OperationType.CREATE,
            object_type="ip4_block",
            resource_id=None,
            payload={"name": "Test Block", "range": "10.0.0.0/8"},
            csv_row=None,
        )

        # Should not raise any error
        executor._resolve_deferred_ids(operation)
