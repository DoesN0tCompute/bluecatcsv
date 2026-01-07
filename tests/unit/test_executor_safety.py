"""Tests for executor safety features."""

from unittest.mock import AsyncMock

import pytest

from src.importer.execution.executor import OperationExecutor
from src.importer.models.csv_row import IP4AddressRow
from src.importer.models.operations import Operation, OperationType


class TestOperationExecutorSafety:
    """Test executor safety features for dangerous operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def mock_policy(self):
        """Create a mock policy config."""
        policy = AsyncMock()
        policy.max_concurrent_operations = 10
        return policy

    @pytest.fixture
    def safe_executor(self, mock_client, mock_policy):
        """Create an executor with safety features enabled."""
        return OperationExecutor(
            bam_client=mock_client, policy=mock_policy, allow_dangerous_operations=False
        )

    @pytest.fixture
    def dangerous_executor(self, mock_client, mock_policy):
        """Create an executor with dangerous operations allowed."""
        return OperationExecutor(
            bam_client=mock_client, policy=mock_policy, allow_dangerous_operations=True
        )

    @pytest.mark.asyncio
    async def test_safe_executor_allows_safe_deletions(self, safe_executor, mock_client):
        """Test that safe deletions work normally."""
        mock_client.delete_entity_by_id.return_value = {"status": "success"}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="ip4_address",
            resource_id=123,
            payload={},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="delete",
                config="Default",
                address="192.168.1.10",
            ),
        )

        result = await safe_executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 123
        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "IPv4Address", allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_safe_executor_blocks_configuration_deletion(self, safe_executor, mock_client):
        """Test that configuration deletion is blocked."""
        # Note: We use ip4_block here because configuration doesn't have a handler,
        # but we are testing that the safety flag is passed correctly to the client.
        # The actual blocking happens in the client or handler based on this flag.

        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="ip4_block",
            resource_id=123,
            payload={},
            csv_row={},
        )

        # Simulate client raising PermissionError when safe flag is on
        mock_client.delete_entity_by_id.side_effect = PermissionError(
            "CRITICAL SAFETY: Configuration deletion blocked"
        )

        result = await safe_executor._execute_operation(operation)

        # Executor catches exception and returns failure result
        assert result.success is False
        assert "CRITICAL SAFETY" in result.error_message

        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "IPv4Block", allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_safe_executor_blocks_view_deletion(self, safe_executor, mock_client):
        """Test that view deletion is blocked."""
        # Using ip4_block as proxy for a protected resource that has a handler
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="ip4_block",
            resource_id=456,
            payload={},
            csv_row={},
        )

        mock_client.delete_entity_by_id.side_effect = PermissionError(
            "CRITICAL SAFETY: View deletion blocked"
        )

        result = await safe_executor._execute_operation(operation)

        assert result.success is False
        assert "CRITICAL SAFETY" in result.error_message

        mock_client.delete_entity_by_id.assert_called_once_with(
            456, "IPv4Block", allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_dangerous_executor_allows_configuration_deletion(
        self, dangerous_executor, mock_client
    ):
        """Test that dangerous executor allows configuration deletion."""
        mock_client.delete_entity_by_id.return_value = {"status": "success"}

        # Use ip4_block as proxy since configuration handler doesn't exist
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="ip4_block",
            resource_id=123,
            payload={},
            csv_row={},
        )

        result = await dangerous_executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 123
        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "IPv4Block", allow_dangerous_operations=True
        )

    @pytest.mark.asyncio
    async def test_dangerous_executor_allows_view_deletion(self, dangerous_executor, mock_client):
        """Test that dangerous executor allows view deletion."""
        mock_client.delete_entity_by_id.return_value = {"status": "success"}

        # Use ip4_block as proxy
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="ip4_block",
            resource_id=456,
            payload={},
            csv_row={},
        )

        result = await dangerous_executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 456
        mock_client.delete_entity_by_id.assert_called_once_with(
            456, "IPv4Block", allow_dangerous_operations=True
        )

    @pytest.mark.asyncio
    async def test_executor_allows_safe_updates(self, safe_executor, mock_client):
        """Test that safe updates work normally (updates are not dangerous)."""
        mock_client.update_entity_by_id.return_value = {"status": "success"}

        # Use ip4_block as proxy
        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="ip4_block",
            resource_id=123,
            payload={"properties": {"name": "updated"}},
            csv_row={},
        )

        result = await safe_executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 123
        mock_client.update_entity_by_id.assert_called_once_with(
            123, "IPv4Block", {"properties": {"name": "updated"}}
        )

    @pytest.mark.asyncio
    async def test_executor_allows_safe_creates(self, safe_executor, mock_client):
        """Test that creates work normally (creates are not dangerous)."""
        # We need to use dry_run=True to avoid mocking the create call details
        safe_executor.dry_run = True

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_block",
            resource_id=None,
            payload={"properties": {"name": "new-config"}},
            csv_row={},
        )

        result = await safe_executor._execute_operation(operation)

        assert result.success is True
        assert result.metadata["dry_run"] is True

    @pytest.mark.asyncio
    async def test_executor_handles_unknown_object_type(self, safe_executor):
        """Test that unknown object types are handled properly."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="unknown_type",
            resource_id=123,
            payload={},
            csv_row={},
        )

        result = await safe_executor._execute_operation(operation)

        assert result.success is False
        assert "No handler registered for object type: unknown_type" in result.error_message

    def test_executor_initialization_with_safety_flag(self, mock_client, mock_policy):
        """Test executor initialization with safety flag."""
        # Test default (safe)
        executor_default = OperationExecutor(mock_client, mock_policy)
        assert executor_default.allow_dangerous_operations is False

        # Test explicit safe
        executor_safe = OperationExecutor(
            mock_client, mock_policy, allow_dangerous_operations=False
        )
        assert executor_safe.allow_dangerous_operations is False

        # Test dangerous
        executor_dangerous = OperationExecutor(
            mock_client, mock_policy, allow_dangerous_operations=True
        )
        assert executor_dangerous.allow_dangerous_operations is True

    @pytest.mark.asyncio
    async def test_executor_dry_run_mode_safety(self, safe_executor):
        """Test that dry-run mode works with safety features."""
        safe_executor.dry_run = True

        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="configuration",
            resource_id=123,
            payload={},
            csv_row={},
        )

        # In dry-run mode, the operation should succeed without actually calling delete
        result = await safe_executor._execute_operation(operation)

        assert result.success is True
        assert result.metadata == {"dry_run": True}


class TestValidateOperationSafetyAbsoluteBlock:
    """Test that config/view deletion is ALWAYS blocked via CSV import."""

    def test_config_deletion_blocked_even_with_allow_flag(self):
        """Config deletion is blocked even with allow_dangerous_operations=True."""
        from src.importer.utils.exceptions import ValidationError
        from src.importer.validation.safety import validate_operation_safety

        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="configuration",
            resource_id=123,
            payload={},
            csv_row={},
        )

        # Even with allow_dangerous_operations=True, should raise
        with pytest.raises(ValidationError) as exc_info:
            validate_operation_safety([operation], allow_dangerous_operations=True)

        assert "ABSOLUTE SAFETY VIOLATION" in str(exc_info.value)
        assert "PERMANENTLY BLOCKED" in str(exc_info.value)

    def test_view_deletion_blocked_even_with_allow_flag(self):
        """View deletion is blocked even with allow_dangerous_operations=True."""
        from src.importer.utils.exceptions import ValidationError
        from src.importer.validation.safety import validate_operation_safety

        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="view",
            resource_id=456,
            payload={},
            csv_row={},
        )

        # Even with allow_dangerous_operations=True, should raise
        with pytest.raises(ValidationError) as exc_info:
            validate_operation_safety([operation], allow_dangerous_operations=True)

        assert "ABSOLUTE SAFETY VIOLATION" in str(exc_info.value)
        assert "PERMANENTLY BLOCKED" in str(exc_info.value)

    def test_csv_check_blocks_config_deletion_unconditionally(self):
        """check_csv_for_dangerous_operations blocks config deletion unconditionally."""
        from src.importer.utils.exceptions import ValidationError
        from src.importer.validation.safety import check_csv_for_dangerous_operations

        csv_data = [
            {"row_id": 1, "object_type": "configuration", "action": "delete", "name": "TestConfig"}
        ]

        # Even with allow_dangerous_operations=True, should raise
        with pytest.raises(ValidationError) as exc_info:
            check_csv_for_dangerous_operations(csv_data, allow_dangerous_operations=True)

        assert "ABSOLUTE SAFETY VIOLATION" in str(exc_info.value)
        assert "PERMANENTLY BLOCKED" in str(exc_info.value)

    def test_csv_check_blocks_view_deletion_unconditionally(self):
        """check_csv_for_dangerous_operations blocks view deletion unconditionally."""
        from src.importer.utils.exceptions import ValidationError
        from src.importer.validation.safety import check_csv_for_dangerous_operations

        csv_data = [{"row_id": 1, "object_type": "view", "action": "delete", "name": "TestView"}]

        # Even with allow_dangerous_operations=True, should raise
        with pytest.raises(ValidationError) as exc_info:
            check_csv_for_dangerous_operations(csv_data, allow_dangerous_operations=True)

        assert "ABSOLUTE SAFETY VIOLATION" in str(exc_info.value)
        assert "PERMANENTLY BLOCKED" in str(exc_info.value)

    def test_other_protected_resources_still_require_flag(self):
        """Other protected resources (blocks, networks, zones) still use the flag."""
        from src.importer.utils.exceptions import ValidationError
        from src.importer.validation.safety import validate_operation_safety

        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="ip4_block",
            resource_id=789,
            payload={},
            csv_row={},
        )

        # Without flag, should raise
        with pytest.raises(ValidationError) as exc_info:
            validate_operation_safety([operation], allow_dangerous_operations=False)

        assert "CRITICAL SAFETY VIOLATION" in str(exc_info.value)

        # With flag, should NOT raise
        validate_operation_safety([operation], allow_dangerous_operations=True)
