"""Unit tests for Dependency Planner."""

from unittest.mock import MagicMock

import pytest

from src.importer.dependency.graph import DependencyGraph
from src.importer.dependency.planner import DependencyPlanner
from src.importer.models.operations import Operation, OperationType


class TestDependencyPlanner:
    """Test DependencyPlanner class."""

    @pytest.fixture
    def planner(self):
        """Create a dependency planner."""
        return DependencyPlanner()

    @pytest.fixture
    def create_op(self):
        """Factory for creating operations."""

        def _create_op(row_id, obj_type, payload_extras=None):
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
            elif obj_type == "dns_zone":
                kwargs["zone_name"] = f"example{row_id}.com"
                kwargs["view_path"] = "Internal"

            # Create partial mock row to satisfy getattr calls in planner
            csv_row = MagicMock()
            csv_row.row_id = row_id
            csv_row.object_type = obj_type
            for k, v in kwargs.items():
                setattr(csv_row, k, v)

            # Additional attributes often accessed
            csv_row.parent_path = None
            csv_row.network_path = None
            csv_row.block_path = None
            csv_row.zone_path = None
            csv_row.linked_record_name = None
            csv_row.cname = None
            csv_row.target = None
            csv_row.exchange = None
            csv_row.code = None

            payload = {}
            if payload_extras:
                payload.update(payload_extras)

            return Operation(
                row_id=row_id,
                operation_type=OperationType.CREATE,
                object_type=obj_type,
                resource_id=None,
                payload=payload,
                csv_row=csv_row,
            )

        return _create_op

    def test_build_graph_simple_block_network(self, planner, create_op):
        """Test building graph with block and network dependency."""
        graph = DependencyGraph()

        # Block 10.1.0.0/16
        op_block = create_op(1, "ip4_block")
        op_block.csv_row.cidr = "10.1.0.0/16"

        # Network 10.1.1.0/24 depends on block (via deferred lookup or just existing in map)
        op_net = create_op(2, "ip4_network")
        op_net.csv_row.cidr = "10.1.1.0/24"
        # Simulate auto-discovery finding the block created in same batch
        op_net.payload["_deferred_block_cidr"] = "10.1.0.0/16"

        planner.build_graph(graph, [op_block, op_net])

        node_block = "ip4_block:1"
        node_net = "ip4_network:2"

        assert node_block in graph.nodes
        assert node_net in graph.nodes

        # Check dependency
        net_node = graph.nodes[node_net]
        assert node_block in net_node.dependencies

    def test_build_graph_network_address(self, planner, create_op):
        """Test building graph with network and address dependency."""
        graph = DependencyGraph()

        op_net = create_op(1, "ip4_network")
        op_net.csv_row.cidr = "10.1.1.0/24"

        op_addr = create_op(2, "ip4_address")
        op_addr.csv_row.address = "10.1.1.5"
        op_addr.payload["_deferred_network_cidr"] = "10.1.1.0/24"

        planner.build_graph(graph, [op_net, op_addr])

        node_net = "ip4_network:1"
        node_addr = "ip4_address:2"

        addr_node = graph.nodes[node_addr]
        assert node_net in addr_node.dependencies

    def test_build_graph_explicit_parent_path(self, planner, create_op):
        """Test building graph with explicit parent path dependency."""
        graph = DependencyGraph()

        op_block = create_op(1, "ip4_block")
        op_block.csv_row.cidr = "10.1.0.0/16"

        op_net = create_op(2, "ip4_network")
        # Parent path pointing to block
        op_net.csv_row.parent_path = "Default/10.1.0.0/16"

        planner.build_graph(graph, [op_block, op_net])

        node_block = "ip4_block:1"
        node_net = "ip4_network:2"

        net_node = graph.nodes[node_net]
        assert node_block in net_node.dependencies

    def test_build_graph_ignores_errors(self, planner, create_op):
        """Test that operations with errors are skipped for dependencies."""
        graph = DependencyGraph()

        op_block = create_op(1, "ip4_block")
        op_block.csv_row.cidr = "10.1.0.0/16"
        op_block.payload["error"] = "Something wrong"

        op_net = create_op(2, "ip4_network")
        op_net.payload["_deferred_block_cidr"] = "10.1.0.0/16"

        planner.build_graph(graph, [op_block, op_net])

        # Block with error should not be a valid dependency target
        # So network should NOT have dependency on block (or fail silently)
        node_net = "ip4_network:2"
        net_node = graph.nodes[node_net]
        # Since block node wasn't added to valid_ids (due to error), or maybe it was added to graph but not map?
        # The logic: if "error" in op.payload: continue (in building maps loop)
        # So block not in 'blocks' map.
        assert not net_node.dependencies
