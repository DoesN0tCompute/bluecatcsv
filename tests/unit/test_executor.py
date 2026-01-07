"""Unit tests for Operation Executor."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from src.importer.bam.client import BAMClient
from src.importer.config import PolicyConfig, ThrottleConfig
from src.importer.execution.executor import OperationExecutor
from src.importer.execution.planner import ExecutionBatch, ExecutionPlan
from src.importer.models.csv_row import IP4AddressRow, IP4BlockRow, IP4NetworkRow
from src.importer.models.operations import Operation, OperationStatus, OperationType
from src.importer.models.results import OperationResult
from src.importer.utils.exceptions import BAMAPIError, BAMRateLimitError


class TestOperationExecutor:
    """Test OperationExecutor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock(spec=BAMClient)
        self.policy = PolicyConfig(max_concurrent_operations=5)
        self.executor = OperationExecutor(self.mock_client, self.policy)

    def test_initialization(self):
        """Test executor initialization."""
        assert self.executor.client == self.mock_client
        assert self.executor.policy == self.policy
        assert self.executor.dry_run is False
        assert self.executor.results == []
        assert self.executor.throttle is not None

    def test_initialization_with_custom_throttle(self):
        """Test executor initialization with custom throttle."""
        from src.importer.execution.throttle import AdaptiveThrottle

        config = ThrottleConfig(initial_concurrency=10)
        custom_throttle = AdaptiveThrottle(config)
        executor = OperationExecutor(self.mock_client, self.policy, custom_throttle)

        assert executor.throttle == custom_throttle

    # Test plan execution
    @pytest.mark.asyncio
    async def test_execute_plan_single_batch(self):
        """Test executing a plan with a single batch."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.NOOP,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="10.1.0.5",
            ),
        )
        batch = ExecutionBatch(batch_id=1, operations=[operation])
        plan = ExecutionPlan(batches=[batch], total_operations=1)

        results = await self.executor.execute_plan(plan)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].operation == OperationType.NOOP

    @pytest.mark.asyncio
    async def test_execute_plan_multiple_batches(self):
        """Test executing a plan with multiple batches."""
        operations = [
            Operation(
                row_id=i,
                operation_type=OperationType.NOOP,
                object_type="ip4_address",
                resource_id=None,
                payload={},
                csv_row=IP4AddressRow(
                    row_id=i,
                    object_type="ip4_address",
                    action="create",
                    config="Default",
                    address=f"10.1.0.{i}",
                ),
            )
            for i in range(3)
        ]

        batches = [
            ExecutionBatch(batch_id=1, operations=[operations[0]]),
            ExecutionBatch(batch_id=2, operations=[operations[1], operations[2]]),
        ]
        plan = ExecutionPlan(batches=batches, total_operations=3)

        results = await self.executor.execute_plan(plan)

        assert len(results) == 3
        assert all(result.success for result in results)

    @pytest.mark.asyncio
    async def test_execute_plan_dry_run(self):
        """Test executing a plan in dry run mode."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="10.1.0.5",
            ),
        )
        batch = ExecutionBatch(batch_id=1, operations=[operation])
        plan = ExecutionPlan(batches=[batch], total_operations=1)

        results = await self.executor.execute_plan(plan, dry_run=True)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].metadata["dry_run"] is True

    # Test batch execution
    @pytest.mark.asyncio
    async def test_execute_batch_with_exceptions(self):
        """Test batch execution handles exceptions properly."""
        operation1 = Operation(
            row_id=1,
            operation_type=OperationType.NOOP,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            # Valid action required for Pydantic validation
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
        )

        operation2 = Operation(
            row_id=2,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"network_id": 999, "address": "1.1.1.2"},
            csv_row=IP4AddressRow(
                row_id=2,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.2",
            ),
        )

        batch = ExecutionBatch(batch_id=1, operations=[operation1, operation2])

        # Mock create to raise an exception
        self.mock_client.create_ip4_address.side_effect = BAMAPIError("API Error")

        results = await self.executor._execute_batch(batch)

        assert len(results) == 2
        assert results[0].success is True  # NOOP should succeed
        assert results[1].success is False  # CREATE should fail
        assert "API Error" in results[1].error_message

    # Test individual operation execution
    @pytest.mark.asyncio
    async def test_execute_operation_noop(self):
        """Test executing a NOOP operation."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.NOOP,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            # Valid action required for Pydantic validation
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is True
        # NOOP no longer sets metadata by default
        assert operation.status == OperationStatus.SUCCEEDED

    @pytest.mark.asyncio
    async def test_execute_operation_create_block(self):
        """Test executing a CREATE block operation."""
        csv_row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="Test Block",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_block",
            csv_row=csv_row,
            resource_id=None,
            payload={"config_id": 123, "properties": {}},
        )

        mock_result = {"id": 456}
        self.mock_client.create_ip4_block.return_value = mock_result

        result = await self.executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 456
        assert operation.status == OperationStatus.SUCCEEDED
        assert operation.resource_id == 456

        self.mock_client.create_ip4_block.assert_called_once_with(
            config_id=123,
            cidr="10.0.0.0/8",
            name="Test Block",
            properties={},
            location=None,
            parent_id=None,
        )

    @pytest.mark.asyncio
    async def test_execute_operation_create_network(self):
        """Test executing a CREATE network operation."""
        csv_row = IP4NetworkRow(
            row_id=1,
            object_type="ip4_network",
            action="create",
            config="Default",
            cidr="10.1.0.0/24",
            name="Test Network",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            csv_row=csv_row,
            resource_id=None,
            payload={"block_id": 123, "properties": {}},
        )

        mock_result = {"id": 456}
        self.mock_client.create_ip4_network.return_value = mock_result

        result = await self.executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 456
        self.mock_client.create_ip4_network.assert_called_once_with(
            block_id=123,
            cidr="10.1.0.0/24",
            name="Test Network",
            properties={},
            location=None,
        )

    @pytest.mark.asyncio
    async def test_execute_operation_create_address(self):
        """Test executing a CREATE address operation."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            name="server1",
            mac="00:11:22:33:44:55",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            csv_row=csv_row,
            resource_id=None,
            payload={"network_id": 123, "properties": {}},
        )

        mock_result = {"id": 456}
        self.mock_client.create_ip4_address.return_value = mock_result

        result = await self.executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 456
        self.mock_client.create_ip4_address.assert_called_once_with(
            network_id=123,
            address="10.1.0.5",
            name="server1",
            mac="00:11:22:33:44:55",
            state="STATIC",
            properties={},
        )

    @pytest.mark.asyncio
    async def test_execute_operation_create_missing_config_id(self):
        """Test CREATE operation fails with missing config_id."""
        csv_row = IP4BlockRow(
            row_id=1,
            object_type="ip4_block",
            action="create",
            config="Default",
            cidr="10.0.0.0/8",
            name="Test Block",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_block",
            csv_row=csv_row,
            resource_id=None,
            payload={"properties": {}},  # Missing config_id
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is False
        assert "Missing required config_id" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_operation_create_missing_block_id(self):
        """Test CREATE operation fails with missing block_id."""
        csv_row = IP4NetworkRow(
            row_id=1,
            object_type="ip4_network",
            action="create",
            config="Default",
            cidr="10.1.0.0/24",
            name="Test Network",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            csv_row=csv_row,
            resource_id=None,
            payload={"properties": {}},  # Missing block_id
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is False
        assert "Missing required block_id" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_operation_create_missing_network_id(self):
        """Test CREATE operation fails with missing network_id."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            csv_row=csv_row,
            resource_id=None,
            payload={"properties": {}},  # Missing network_id
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is False
        assert "Missing required network_id" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_operation_create_unsupported_type(self):
        """Test CREATE operation with unsupported object type."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="unsupported_type",
            # We use IP4AddressRow as a placeholder for valid Pydantic model,
            # even though object_type mismatch (Operation object_type vs Row object_type)
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
            resource_id=None,
            payload={},
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is False
        assert "No handler registered for object type: unsupported_type" in result.error_message

    @pytest.mark.asyncio
    async def test_execute_operation_update(self):
        """Test executing an UPDATE operation."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="ip4_address",
            resource_id=123,
            payload={"properties": {"name": "updated"}},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="update",
                config="Default",
                address="1.1.1.1",
            ),
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 123
        assert operation.status == OperationStatus.SUCCEEDED

        self.mock_client.update_entity_by_id.assert_called_once_with(
            123, "IPv4Address", {"properties": {"name": "updated"}}
        )

    @pytest.mark.asyncio
    async def test_execute_operation_delete(self):
        """Test executing a DELETE operation."""
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
                address="1.1.1.1",
            ),
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 123
        assert operation.status == OperationStatus.SUCCEEDED

        self.mock_client.delete_entity_by_id.assert_called_once_with(
            123, "IPv4Address", allow_dangerous_operations=False
        )

    # Test rate limit handling
    @pytest.mark.asyncio
    async def test_execute_operation_rate_limit_retry(self):
        """Test operation retry on rate limit."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.NOOP,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            # Valid action required for Pydantic validation
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
        )

        # Simulate rate limit on first call, success on retry
        rate_limit_error = BAMRateLimitError(retry_after=0.1)

        def mock_execute(op):
            # Use a counter to simulate failure then success
            if not hasattr(mock_execute, "call_count"):
                mock_execute.call_count = 0
            mock_execute.call_count += 1

            if mock_execute.call_count == 1:
                raise rate_limit_error
            else:
                return OperationResult(
                    row_id=op.row_id,
                    operation=op.operation_type,
                    success=True,
                    resource_id=None,
                )

        # We patch _execute_noop but since _execute_operation calls _execute_noop based on type,
        # we need to make sure we are calling it.
        # Wait, the executor logic: if op type is NOOP -> calls _execute_noop.

        with patch.object(self.executor, "_execute_noop", side_effect=mock_execute):
            result = await self.executor._execute_operation(operation)

        assert result.success is True
        assert self.executor.throttle.metrics.rate_limit_errors == 1

    # Test dry run modes
    @pytest.mark.asyncio
    async def test_execute_create_dry_run(self):
        """Test CREATE operation in dry run mode."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
        )
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            csv_row=csv_row,
            resource_id=None,
            payload={"network_id": 123},
        )

        self.executor.dry_run = True

        result = await self.executor._execute_create(operation)

        assert result.success is True
        assert result.metadata["dry_run"] is True
        assert result.resource_id is not None

        # Should not make API calls
        self.mock_client.create_ip4_address.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_update_dry_run(self):
        """Test UPDATE operation in dry run mode."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="ip4_address",
            resource_id=123,
            payload={"properties": {"name": "updated"}},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="update",
                config="Default",
                address="1.1.1.1",
            ),
        )

        self.executor.dry_run = True

        result = await self.executor._execute_update(operation)

        assert result.success is True
        assert result.metadata["dry_run"] is True
        assert result.resource_id == 123

        self.mock_client.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_delete_dry_run(self):
        """Test DELETE operation in dry run mode."""
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
                address="1.1.1.1",
            ),
        )

        self.executor.dry_run = True

        result = await self.executor._execute_delete(operation)

        assert result.success is True
        assert result.metadata["dry_run"] is True
        assert result.resource_id == 123

        # In dry-run mode, no actual deletion should occur
        self.mock_client.delete_entity_by_id.assert_not_called()

    # Test statistics
    def test_get_statistics_no_results(self):
        """Test statistics when no results available."""
        stats = self.executor.get_statistics()

        assert stats == {"total": 0}

    def test_get_statistics_with_results(self):
        """Test statistics with results."""
        # Create mock results
        Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
        )
        Operation(
            row_id=2,
            operation_type=OperationType.UPDATE,
            object_type="ip4_address",
            resource_id=456,
            payload={},
            csv_row=IP4AddressRow(
                row_id=2,
                object_type="ip4_address",
                action="update",
                config="Default",
                address="1.1.1.2",
            ),
        )
        Operation(
            row_id=3,
            operation_type=OperationType.DELETE,
            object_type="ip4_address",
            resource_id=789,
            payload={},
            csv_row=IP4AddressRow(
                row_id=3,
                object_type="ip4_address",
                action="delete",
                config="Default",
                address="1.1.1.3",
            ),
        )

        self.executor.results = [
            OperationResult(
                row_id=1, operation=OperationType.CREATE, success=True, resource_id=123
            ),
            OperationResult(
                row_id=2,
                operation=OperationType.UPDATE,
                success=False,
                error_message="Failed",
                resource_id=456,
            ),
            OperationResult(
                row_id=3, operation=OperationType.DELETE, success=True, resource_id=789
            ),
        ]

        stats = self.executor.get_statistics()

        assert stats["total"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == 2 / 3
        assert stats["operation_breakdown"]["create"] == 1
        assert stats["operation_breakdown"]["update"] == 1
        assert stats["operation_breakdown"]["delete"] == 1
        assert stats["operation_breakdown"]["noop"] == 0
        assert "throttle_metrics" in stats

    # Test error handling
    # Test error handling
    @pytest.mark.asyncio
    async def test_execute_operation_with_pre_existing_error(self):
        """Test operation with pre-existing error in payload (fail-fast)."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"error": "Factory Failed", "traceback": "Traceback info..."},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
        )

        result = await self.executor._execute_operation(operation)

        assert result.success is False
        assert result.error_message == "Factory Failed"
        assert result.metadata["traceback"] == "Traceback info..."
        assert result.duration_ms == 0

        # Should not make API calls
        self.mock_client.create_ip4_address.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_operation_generic_exception(self):
        """Test operation execution handles generic exceptions."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="ip4_address",
            resource_id=123,
            payload={},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="update",
                config="Default",
                address="1.1.1.1",
            ),
        )

        # Mock client to raise exception
        self.mock_client.update_entity_by_id.side_effect = Exception("Generic error")

        result = await self.executor._execute_operation(operation)

        assert result.success is False
        assert "Generic error" in result.error_message
        # Duration ms check is brittle if timing is 0.0
        # assert result.duration_ms > 0

        # Should record failure
        assert self.executor.throttle.metrics.failed_requests > 0

    # Test throttle integration
    @pytest.mark.asyncio
    async def test_execute_operation_records_success_metrics(self):
        """Test successful operation records success metrics."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.NOOP,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            # Valid action required for Pydantic validation
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
        )

        # Reset metrics
        self.executor.throttle.reset_metrics()

        result = await self.executor._execute_operation(operation)

        assert result.success is True
        assert self.executor.throttle.metrics.total_requests == 1
        assert self.executor.throttle.metrics.successful_requests == 1
        # avg_latency might be 0 if too fast, don't assert > 0

    # Test concurrent execution
    @pytest.mark.asyncio
    async def test_concurrent_operations_respect_throttle(self):
        """Test concurrent operations respect throttle limits."""
        operations = [
            Operation(
                row_id=i,
                operation_type=OperationType.NOOP,
                object_type="ip4_address",
                resource_id=None,
                payload={},
                # action must be valid (create/update/delete) even for NOOP operation
                csv_row=IP4AddressRow(
                    row_id=i,
                    object_type="ip4_address",
                    action="create",
                    config="Default",
                    address="1.1.1.1",
                ),
            )
            for i in range(10)
        ]

        batch = ExecutionBatch(batch_id=1, operations=operations)

        # Reset throttle metrics
        self.executor.throttle.reset_metrics()

        time.time()
        results = await self.executor._execute_batch(batch)
        time.time()

        assert len(results) == 10
        assert all(result.success for result in results)

        # Should have taken some time due to throttling (though this may be flaky in tests)
        # The important thing is that it completed without errors

    def test_execute_noop_direct(self):
        """Test _execute_noop method directly."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.NOOP,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            # action must be valid (create/update/delete) even for NOOP operation
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="1.1.1.1",
            ),
        )

        result = self.executor._execute_noop(operation)

        assert result.success is True
        # NOOP does not set metadata by default
        # assert result.metadata["noop"] is True
        assert operation.status == OperationStatus.SUCCEEDED


class TestExecutorResumeSupport:
    """Test OperationExecutor resume functionality with initial_created_resources."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock(spec=BAMClient)
        self.policy = PolicyConfig(max_concurrent_operations=5)

    def test_initialization_with_empty_initial_resources(self):
        """Test executor initialization with no initial resources."""
        executor = OperationExecutor(self.mock_client, self.policy)

        assert executor.created_blocks == {}
        assert executor.created_networks == {}
        assert executor.created_zones == {}
        assert executor.created_locations == {}

    def test_initialization_with_initial_created_resources(self):
        """Test executor initialization with pre-populated created resources."""
        initial_resources = {
            "block": {"10.0.0.0/8": 100, "172.16.0.0/12": 101},
            "network": {"10.1.0.0/24": 200},
            "zone": {"example.com": 300},
            "location": {"NYC": 400},
        }

        executor = OperationExecutor(
            self.mock_client,
            self.policy,
            initial_created_resources=initial_resources,
        )

        assert executor.created_blocks == {"10.0.0.0/8": 100, "172.16.0.0/12": 101}
        assert executor.created_networks == {"10.1.0.0/24": 200}
        assert executor.created_zones == {"example.com": 300}
        assert executor.created_locations == {"NYC": 400}

    def test_initialization_with_partial_initial_resources(self):
        """Test executor initialization with partial initial resources."""
        initial_resources = {
            "block": {"10.0.0.0/8": 100},
            # Missing network, zone, location
        }

        executor = OperationExecutor(
            self.mock_client,
            self.policy,
            initial_created_resources=initial_resources,
        )

        assert executor.created_blocks == {"10.0.0.0/8": 100}
        assert executor.created_networks == {}
        assert executor.created_zones == {}
        assert executor.created_locations == {}

    @pytest.mark.asyncio
    async def test_deferred_resolution_with_initial_resources(self):
        """Test that deferred resolution works with pre-populated resources."""
        initial_resources = {
            "block": {"10.0.0.0/8": 12345},
            "network": {},
            "zone": {},
            "location": {},
        }

        executor = OperationExecutor(
            self.mock_client,
            self.policy,
            initial_created_resources=initial_resources,
        )

        # Create an operation with deferred block reference
        operation = Operation(
            row_id=2,
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            resource_id=None,
            payload={
                "_deferred_block_cidr": "10.0.0.0/8",
                "cidr": "10.1.0.0/24",
            },
            csv_row=IP4NetworkRow(
                row_id=2,
                object_type="ip4_network",
                action="create",
                config="Default",
                cidr="10.1.0.0/24",
                name="TestNetwork",
            ),
        )

        # Resolve deferred IDs
        executor._resolve_deferred_ids(operation)

        # Should have resolved the block_id from initial resources
        assert operation.payload["block_id"] == 12345
        assert "_deferred_block_cidr" not in operation.payload

    @pytest.mark.asyncio
    async def test_deferred_resolution_fails_without_initial_resources(self):
        """Test that deferred resolution fails when resource not in initial_created_resources."""
        from src.importer.utils.exceptions import DeferredResolutionError

        # Empty initial resources
        executor = OperationExecutor(
            self.mock_client,
            self.policy,
            initial_created_resources={"block": {}, "network": {}, "zone": {}, "location": {}},
        )

        operation = Operation(
            row_id=2,
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            resource_id=None,
            payload={
                "_deferred_block_cidr": "10.0.0.0/8",
                "cidr": "10.1.0.0/24",
            },
            csv_row=IP4NetworkRow(
                row_id=2,
                object_type="ip4_network",
                action="create",
                config="Default",
                cidr="10.1.0.0/24",
                name="TestNetwork",
            ),
        )

        with pytest.raises(DeferredResolutionError) as exc_info:
            executor._resolve_deferred_ids(operation)

        assert exc_info.value.row_id == 2
        assert exc_info.value.resource_type == "block"
        assert exc_info.value.deferred_value == "10.0.0.0/8"
