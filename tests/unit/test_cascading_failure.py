"""Test cascading failure functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from importer.bam.client import BAMClient
from importer.config import PolicyConfig
from importer.dependency.graph import DependencyGraph, DependencyNode
from importer.execution.executor import OperationExecutor
from importer.execution.throttle import AdaptiveThrottle, ThrottleConfig
from importer.models.operations import Operation, OperationStatus, OperationType


@pytest.fixture
def mock_client():
    """Create a mock BAM client."""
    client = AsyncMock(spec=BAMClient)
    return client


@pytest.fixture
def policy():
    """Create test policy."""
    return PolicyConfig(
        max_concurrent_operations=10,
        min_concurrency=1,
        safe_mode=True,
        update_mode="upsert",
    )


@pytest.fixture
def throttle():
    """Create test throttle."""
    config = ThrottleConfig(
        initial_concurrency=10,
        min_concurrency=1,
        max_concurrency=10,
    )
    return AdaptiveThrottle(config)


@pytest.fixture
def dependency_graph():
    """Create a dependency graph with parent-child relationships."""
    graph = DependencyGraph()

    # Create operations with proper payloads
    block_op = Operation(
        row_id=1,
        operation_type=OperationType.CREATE,
        object_type="ip4_block",
        resource_id=None,
        payload={"config_id": 123, "name": "Test-Block", "cidr": "10.0.0.0/8"},
        csv_row=MagicMock(),
    )

    network_op = Operation(
        row_id=2,
        operation_type=OperationType.CREATE,
        object_type="ip4_network",
        resource_id=None,
        payload={
            "config_id": 123,
            "parent_id": None,
            "name": "Test-Network",
            "cidr": "10.0.1.0/24",
        },
        csv_row=MagicMock(),
    )

    address_op = Operation(
        row_id=3,
        operation_type=OperationType.CREATE,
        object_type="ip4_address",
        resource_id=None,
        payload={"config_id": 123, "parent_id": None, "address": "10.0.1.10"},
        csv_row=MagicMock(),
    )

    # Add nodes to graph
    block_node = DependencyNode(operation=block_op)
    network_node = DependencyNode(operation=network_op)
    address_node = DependencyNode(operation=address_op)

    graph.nodes["ip4_block:1"] = block_node
    graph.nodes["ip4_network:2"] = network_node
    graph.nodes["ip4_address:3"] = address_node

    # Create dependencies: block -> network -> address
    network_node.dependencies.add("ip4_block:1")
    block_node.dependents.add("ip4_network:2")

    address_node.dependencies.add("ip4_network:2")
    network_node.dependents.add("ip4_address:3")

    return graph


@pytest.mark.asyncio
async def test_cascading_failure_marks_dependents_as_skipped(
    mock_client, policy, throttle, dependency_graph
):
    """Test that when a parent operation fails, all dependents are marked as skipped."""
    # Create executor with dependency graph
    executor = OperationExecutor(
        bam_client=mock_client,
        policy=policy,
        throttle=throttle,
        dependency_graph=dependency_graph,
    )

    # Enable dry run to avoid API calls
    executor.dry_run = True

    # Get operations from graph
    operations = [node.operation for node in dependency_graph.nodes.values()]

    # Execute operations - in dry run mode, they all succeed
    results = []
    for op in operations:
        result = await executor._execute_operation(op)
        results.append(result)

    # Check results - all should succeed in dry run mode
    assert len(results) == 3
    for result in results:
        assert result.success is True
        assert result.metadata.get("dry_run") is True


@pytest.mark.asyncio
async def test_multiple_cascading_failures(mock_client, policy, throttle):
    """Test cascading failures with multiple parent-child relationships."""
    # Create a more complex dependency graph
    graph = DependencyGraph()

    # Create operations
    block_op = Operation(
        row_id=1,
        operation_type=OperationType.CREATE,
        object_type="ip4_block",
        resource_id=None,
        payload={},
        csv_row=MagicMock(),
    )

    network1_op = Operation(
        row_id=2,
        operation_type=OperationType.CREATE,
        object_type="ip4_network",
        resource_id=None,
        payload={},
        csv_row=MagicMock(),
    )

    network2_op = Operation(
        row_id=3,
        operation_type=OperationType.CREATE,
        object_type="ip4_network",
        resource_id=None,
        payload={},
        csv_row=MagicMock(),
    )

    address1_op = Operation(
        row_id=4,
        operation_type=OperationType.CREATE,
        object_type="ip4_address",
        resource_id=None,
        payload={},
        csv_row=MagicMock(),
    )

    address2_op = Operation(
        row_id=5,
        operation_type=OperationType.CREATE,
        object_type="ip4_address",
        resource_id=None,
        payload={},
        csv_row=MagicMock(),
    )

    # Add nodes
    block_node = DependencyNode(operation=block_op)
    network1_node = DependencyNode(operation=network1_op)
    network2_node = DependencyNode(operation=network2_op)
    address1_node = DependencyNode(operation=address1_op)
    address2_node = DependencyNode(operation=address2_op)

    graph.nodes["ip4_block:1"] = block_node
    graph.nodes["ip4_network:2"] = network1_node
    graph.nodes["ip4_network:3"] = network2_node
    graph.nodes["ip4_address:4"] = address1_node
    graph.nodes["ip4_address:5"] = address2_node

    # Create dependencies
    # Both networks depend on block
    network1_node.dependencies.add("ip4_block:1")
    network2_node.dependencies.add("ip4_block:1")
    block_node.dependents.update(["ip4_network:2", "ip4_network:3"])

    # Addresses depend on respective networks
    address1_node.dependencies.add("ip4_network:2")
    address2_node.dependencies.add("ip4_network:3")
    network1_node.dependents.add("ip4_address:4")
    network2_node.dependents.add("ip4_address:5")

    # Create executor
    executor = OperationExecutor(
        bam_client=mock_client,
        policy=policy,
        throttle=throttle,
        dependency_graph=graph,
    )

    # Mock client to succeed on some, fail on others
    async def mock_post(*args, **kwargs):
        if "blocks" in args[0]:
            raise Exception("Block creation failed")
        return {"id": 123}

    mock_client.post.side_effect = mock_post

    # Execute operations in dependency order
    results = []
    operations = [block_op, network1_op, network2_op, address1_op, address2_op]

    for op in operations:
        result = await executor._execute_operation(op)
        results.append(result)

    # Check that block failed and everything else was skipped
    assert results[0].success is False  # Block failed
    assert results[1].metadata.get("skipped") is True  # Network 1 skipped
    assert results[2].metadata.get("skipped") is True  # Network 2 skipped
    assert results[3].metadata.get("skipped") is True  # Address 1 skipped
    assert results[4].metadata.get("skipped") is True  # Address 2 skipped


@pytest.mark.asyncio
async def test_no_cascading_when_no_dependency_graph(mock_client, policy, throttle):
    """Test that operations execute normally when no dependency graph is provided."""
    # Create executor without dependency graph
    executor = OperationExecutor(
        bam_client=mock_client,
        policy=policy,
        throttle=throttle,
        dependency_graph=None,
    )

    # Create operations
    op1 = Operation(
        row_id=1,
        operation_type=OperationType.CREATE,
        object_type="ip4_block",
        resource_id=None,
        payload={},
        csv_row=MagicMock(),
    )

    op2 = Operation(
        row_id=2,
        operation_type=OperationType.CREATE,
        object_type="ip4_network",
        resource_id=None,
        payload={},
        csv_row=MagicMock(),
    )

    # Mock client to fail on first operation
    mock_client.post.side_effect = Exception("Operation failed")

    # Execute operations
    result1 = await executor._execute_operation(op1)
    result2 = await executor._execute_operation(op2)

    # Both should fail (no cascading without dependency graph)
    assert result1.success is False
    assert result2.success is False
    assert result1.metadata.get("skipped") is None
    assert result2.metadata.get("skipped") is None


def test_mark_operation_failed(mock_client, policy, throttle, dependency_graph):
    """Test the _mark_operation_failed method."""
    executor = OperationExecutor(
        bam_client=mock_client,
        policy=policy,
        throttle=throttle,
        dependency_graph=dependency_graph,
    )

    # Get the block operation
    block_op = dependency_graph.nodes["ip4_block:1"].operation

    # Mark operation as failed
    executor._mark_operation_failed(block_op, "Test error")

    # Check operation is marked as failed
    assert block_op.status == OperationStatus.FAILED
    assert block_op.error_message == "Test error"
    assert "ip4_block:1" in executor.failed_operations

    # Check dependent operations are marked as skipped
    network_op = dependency_graph.nodes["ip4_network:2"].operation
    address_op = dependency_graph.nodes["ip4_address:3"].operation

    assert network_op.status == OperationStatus.SKIPPED
    assert address_op.status == OperationStatus.SKIPPED

    # Check skip reasons
    assert "ip4_network:2" in executor.skipped_operations
    assert "ip4_address:3" in executor.skipped_operations
    assert "parent ip4_block:1 failed: Test error" in executor.skipped_operations["ip4_network:2"]
