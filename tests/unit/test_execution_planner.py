"""Unit tests for Dependency Planner."""

from unittest.mock import MagicMock

import pytest

from src.importer.config import PolicyConfig
from src.importer.dependency.graph import DependencyGraph, DependencyNode
from src.importer.execution.planner import ExecutionBatch, ExecutionPlan, ExecutionPlanner
from src.importer.models.csv_row import IP4AddressRow, IP4BlockRow, IP4NetworkRow
from src.importer.models.operations import Operation, OperationType


class TestExecutionBatch:
    """Test ExecutionBatch class."""

    def test_execution_batch_creation(self):
        """Test creating an execution batch."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
        )
        op = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"address": "10.1.0.5"},
            csv_row=csv_row,
        )

        batch = ExecutionBatch(
            batch_id=1,
            operations=[op],
        )

        assert batch.batch_id == 1
        assert len(batch.operations) == 1
        assert batch.estimated_duration == 0.0

    def test_execution_batch_len(self):
        """Test len() of execution batch."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
        )
        op = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"address": "10.1.0.5"},
            csv_row=csv_row,
        )

        batch = ExecutionBatch(
            batch_id=1,
            operations=[op, op],
        )

        assert len(batch) == 2


class TestExecutionPlanner:
    """Test ExecutionPlanner class."""

    @pytest.fixture
    def planner(self):
        """Create an execution planner."""
        policy = MagicMock(spec=PolicyConfig)
        return ExecutionPlanner(policy)

    @pytest.fixture
    def create_op(self):
        """Factory for creating operations."""

        def _create_op(row_id, obj_type):
            row_cls = IP4AddressRow if obj_type == "ip4_address" else IP4NetworkRow
            if obj_type == "ip4_block":
                row_cls = IP4BlockRow

            kwargs = {
                "row_id": row_id,
                "object_type": obj_type,
                "action": "create",
                "config": "Default",
            }
            if obj_type == "ip4_address":
                kwargs["address"] = f"10.1.0.{row_id}"
            elif obj_type == "ip4_network":
                kwargs["cidr"] = f"10.1.{row_id}.0/24"
                kwargs["name"] = f"net_{row_id}"
            elif obj_type == "ip4_block":
                kwargs["cidr"] = f"10.{row_id}.0.0/16"
                kwargs["name"] = f"block_{row_id}"

            csv_row = row_cls(**kwargs)
            return Operation(
                row_id=row_id,
                operation_type=OperationType.CREATE,
                object_type=obj_type,
                resource_id=None,
                payload={},
                csv_row=csv_row,
            )

        return _create_op

    def test_create_plan_simple(self, planner, create_op):
        """Test creating a plan for simple dependencies."""
        graph = DependencyGraph()

        # A -> B -> C
        op_a = create_op(1, "ip4_block")
        op_b = create_op(2, "ip4_network")
        op_c = create_op(3, "ip4_address")

        graph.add_operation(op_a)
        graph.add_operation(op_b)
        graph.add_operation(op_c)

        graph.add_dependency("ip4_network:2", "ip4_block:1")
        graph.add_dependency("ip4_address:3", "ip4_network:2")

        plan = planner.create_plan(graph)

        assert isinstance(plan, ExecutionPlan)
        assert len(plan.batches) == 3
        # Should be strictly ordered due to dependencies
        assert plan.batches[0].operations[0] == op_a
        assert plan.batches[1].operations[0] == op_b
        assert plan.batches[2].operations[0] == op_c

    def test_create_plan_with_parallel_operations(self, planner, create_op):
        """Test creating a plan with parallel operations."""
        graph = DependencyGraph()

        # Independent operations
        op_a = create_op(1, "ip4_address")
        op_b = create_op(2, "ip4_address")
        op_c = create_op(3, "ip4_address")

        graph.add_operation(op_a)
        graph.add_operation(op_b)
        graph.add_operation(op_c)

        plan = planner.create_plan(graph)

        assert len(plan.batches) == 1
        assert len(plan.batches[0].operations) == 3

    def test_create_plan_with_max_batch_size(self, planner, create_op):
        """Test plan respects max batch size."""
        graph = DependencyGraph()

        # 5 independent operations
        for i in range(5):
            graph.add_operation(create_op(i + 1, "ip4_address"))

        plan = planner.create_plan(graph, max_batch_size=2)

        assert len(plan.batches) == 3  # 2, 2, 1
        assert len(plan.batches[0].operations) == 2
        assert len(plan.batches[1].operations) == 2
        assert len(plan.batches[2].operations) == 1

    def test_create_plan_metadata(self, planner, create_op):
        """Test plan metadata is populated."""
        graph = DependencyGraph()
        graph.add_operation(create_op(1, "ip4_address"))

        plan = planner.create_plan(graph)

        assert plan.total_operations == 1
        assert plan.estimated_total_duration > 0
        assert len(plan.batches) == 1

    def test_create_execution_batch(self, planner, create_op):
        """Test creating a single execution batch."""
        # Need to create DependencyNodes first as _create_execution_batch expects nodes
        op1 = create_op(1, "ip4_address")
        op2 = create_op(2, "ip4_address")
        node1 = DependencyNode(op1)
        node2 = DependencyNode(op2)
        nodes = [node1, node2]

        batch = planner._create_execution_batch(1, nodes)

        assert isinstance(batch, ExecutionBatch)
        assert batch.batch_id == 1
        assert len(batch.operations) == 2

    def test_split_batch(self, planner, create_op):
        """Test splitting a large batch."""
        # Use DependencyNodes
        nodes = [DependencyNode(create_op(i, "ip4_address")) for i in range(5)]

        batches = planner._split_batch(nodes, max_size=2)

        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1

    def test_optimize_plan(self, planner):
        """Test plan optimization."""
        batches = []
        plan = ExecutionPlan(batches=batches)
        optimized = planner.optimize_plan(plan)
        assert optimized == plan

    def test_get_plan_summary(self, planner, create_op):
        """Test getting plan summary."""
        graph = DependencyGraph()
        graph.add_operation(create_op(1, "ip4_address"))
        plan = planner.create_plan(graph)

        summary = planner.get_plan_summary(plan)
        assert "batches" in summary
        assert "total_operations" in summary
        assert summary["total_operations"] == 1

    def test_operation_durations_estimation(self, planner):
        """Test operation duration estimation for batches."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        op = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        node = DependencyNode(op)

        batch = planner._create_execution_batch(1, [node])
        # Default duration for IP4Address create is usually small
        assert batch.estimated_duration > 0

    def test_operation_durations_unknown_type(self, planner):
        """Test duration handling for unknown operation types."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        op = Operation(
            row_id=1,
            operation_type="unknown_type",  # Not in duration map but type hinting might complain
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        # Force invalid type for testing
        op.operation_type = "unknown_type"
        node = DependencyNode(op)

        batch = planner._create_execution_batch(1, [node])
        # Should fall back to default
        assert batch.estimated_duration == 0.5  # Default in get()

    def test_plan_with_mixed_operation_types(self, planner):
        """Test plan with mixed operation types in same batch."""
        csv_row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.1",
        )
        op1 = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )
        op2 = Operation(
            row_id=2,
            operation_type=OperationType.UPDATE,
            object_type="ip4_address",
            resource_id=101,
            payload={},
            csv_row=csv_row,
        )
        node1 = DependencyNode(op1)
        node2 = DependencyNode(op2)

        batch = planner._create_execution_batch(1, [node1, node2])
        assert len(batch) == 2
