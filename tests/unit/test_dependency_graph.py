"""Tests for the DependencyGraph class."""

from unittest.mock import MagicMock

import pytest

from src.importer.dependency.graph import DependencyGraph
from src.importer.models.operations import Operation, OperationStatus, OperationType


class TestDependencyGraph:
    """Test suite for DependencyGraph."""

    @pytest.fixture
    def graph(self):
        """Create a new DependencyGraph instance."""
        return DependencyGraph()

    def create_op(self, object_type, row_id, operation_type=OperationType.CREATE, **csv_attrs):
        """Helper to create an operation with a mock CSV row."""
        csv_row = MagicMock()
        for k, v in csv_attrs.items():
            setattr(csv_row, k, v)

        return Operation(
            object_type=object_type,
            operation_type=operation_type,
            row_id=row_id,
            payload={},
            resource_id=None,
            csv_row=csv_row,
            status=OperationStatus.PENDING,
        )

    def test_add_node(self, graph):
        """Test adding nodes to the graph."""
        op = Operation(
            object_type="network",
            operation_type=OperationType.CREATE,
            row_id="row1",
            payload={"name": "test"},
            resource_id=None,
            csv_row=None,
            status=OperationStatus.PENDING,
        )
        # add_node uses internal node_id generation, so we check what add_operation does
        node = graph.add_operation(op)

        assert node.node_id in graph.nodes
        assert graph.nodes[node.node_id].operation == op
        # DependencyNode property is node_id not id
        assert graph.nodes[node.node_id].node_id == "network:row1"

    def test_add_dependency(self, graph):
        """Test adding dependencies between nodes."""
        # Add parent node
        parent_op = Operation(
            object_type="block",
            operation_type=OperationType.CREATE,
            row_id="row1",
            payload={},
            resource_id=None,
            csv_row=None,
        )
        parent_node = graph.add_operation(parent_op)

        # Add child node
        child_op = Operation(
            object_type="network",
            operation_type=OperationType.CREATE,
            row_id="row2",
            payload={},
            resource_id=None,
            csv_row=None,
        )
        child_node = graph.add_operation(child_op)

        # Add dependency
        # Dependencies use node_ids
        graph.add_dependency(child_node.node_id, parent_node.node_id)

        # Verify dependency structure
        assert parent_node.node_id in graph.nodes[child_node.node_id].dependencies
        assert child_node.node_id in graph.nodes[parent_node.node_id].dependents
        assert graph.nodes[parent_node.node_id].depth == 0

    def test_get_execution_batches(self, graph):
        """Test topological sort and batch generation."""
        # A -> B -> C
        #      |
        #      v
        #      D
        # Create operations
        # Note: Operation constructor requires object_type, operation_type, etc.
        # graph.add_operation generates node_id as "{object_type}:{row_id}"

        ops = {
            "A": Operation(
                object_type="A",
                operation_type=OperationType.CREATE,
                row_id="A",
                payload={},
                resource_id=None,
                csv_row=None,
            ),
            "B": Operation(
                object_type="B",
                operation_type=OperationType.CREATE,
                row_id="B",
                payload={},
                resource_id=None,
                csv_row=None,
            ),
            "C": Operation(
                object_type="C",
                operation_type=OperationType.CREATE,
                row_id="C",
                payload={},
                resource_id=None,
                csv_row=None,
            ),
            "D": Operation(
                object_type="D",
                operation_type=OperationType.CREATE,
                row_id="D",
                payload={},
                resource_id=None,
                csv_row=None,
            ),
        }

        nodes = {}
        for key, op in ops.items():
            nodes[key] = graph.add_operation(op)

        # Add dependencies: dependent -> dependency (child -> parent)
        # B depends on A
        graph.add_dependency(nodes["B"].node_id, nodes["A"].node_id)
        # C depends on B
        graph.add_dependency(nodes["C"].node_id, nodes["B"].node_id)
        # D depends on B
        graph.add_dependency(nodes["D"].node_id, nodes["B"].node_id)

        # Get batches
        batches = graph.get_execution_batches()

        # Expected batches: [A], [B], [C, D] (or [D, C])
        assert len(batches) == 3

        # Batch 0: A
        assert len(batches[0]) == 1
        assert batches[0][0].node_id == nodes["A"].node_id

        # Batch 1: B
        assert len(batches[1]) == 1
        assert batches[1][0].node_id == nodes["B"].node_id

        # Batch 2: C and D
        assert len(batches[2]) == 2
        batch_ids = sorted([node.node_id for node in batches[2]])
        expected_ids = sorted([nodes["C"].node_id, nodes["D"].node_id])
        assert batch_ids == expected_ids

    def test_circular_dependency_detection(self, graph):
        """Test that circular dependencies are detected."""
        from src.importer.utils.exceptions import CyclicDependencyError

        # A -> B -> A
        op_a = Operation(
            object_type="A",
            operation_type=OperationType.CREATE,
            row_id="A",
            payload={},
            resource_id=None,
            csv_row=None,
        )
        op_b = Operation(
            object_type="B",
            operation_type=OperationType.CREATE,
            row_id="B",
            payload={},
            resource_id=None,
            csv_row=None,
        )

        node_a = graph.add_operation(op_a)
        node_b = graph.add_operation(op_b)

        graph.add_dependency(node_b.node_id, node_a.node_id)

        # This creates a cycle and should raise immediately based on add_dependency implementation
        try:
            graph.add_dependency(node_a.node_id, node_b.node_id)
            pytest.fail("Should have raised an error for circular dependency")
        except CyclicDependencyError as e:
            assert "cycle" in str(e)

        # Since add_dependency rejects the cycle, the graph should remain valid (A->B)
        # So get_execution_batches should succeed
        batches = graph.get_execution_batches()
        assert len(batches) == 2

    def test_independent_nodes(self, graph):
        """Test parallel execution of independent nodes."""
        # A, B, C (no dependencies)
        op_a = Operation(
            object_type="A",
            operation_type=OperationType.CREATE,
            row_id="A",
            payload={},
            resource_id=None,
            csv_row=None,
        )
        op_b = Operation(
            object_type="B",
            operation_type=OperationType.CREATE,
            row_id="B",
            payload={},
            resource_id=None,
            csv_row=None,
        )
        op_c = Operation(
            object_type="C",
            operation_type=OperationType.CREATE,
            row_id="C",
            payload={},
            resource_id=None,
            csv_row=None,
        )

        node_a = graph.add_operation(op_a)
        node_b = graph.add_operation(op_b)
        node_c = graph.add_operation(op_c)

        batches = graph.get_execution_batches()

        # Should be one batch with all nodes
        assert len(batches) == 1
        assert len(batches[0]) == 3
        batch_ids = sorted([node.node_id for node in batches[0]])
        expected_ids = sorted([node_a.node_id, node_b.node_id, node_c.node_id])
        assert batch_ids == expected_ids

    def test_missing_dependency(self, graph):
        """Test handling of dependencies on missing nodes."""
        op_a = Operation(
            object_type="A",
            operation_type=OperationType.CREATE,
            row_id="A",
            payload={},
            resource_id=None,
            csv_row=None,
        )
        node_a = graph.add_operation(op_a)

        # Try to depend on non-existent node "B"
        with pytest.raises(ValueError, match="not found"):
            graph.add_dependency(node_a.node_id, "B")

    def test_phasing_barriers(self, graph):
        """Test that operations are correctly separated by phase barriers."""
        # Phase 2: Block (after device_type phase 0 and device_subtype phase 1)
        op_block = self.create_op("ip4_block", "block1")
        # Phase 3: DNS Zone
        op_zone = self.create_op("dns_zone", "zone1")
        # Phase 5: Host Record
        op_host = self.create_op("host_record", "host1")

        ops = [op_block, op_zone, op_host]
        graph.build_from_operations(ops)

        # Check that barriers exist
        barrier_nodes = [
            n for n in graph.nodes.values() if n.operation.object_type == "system_barrier"
        ]
        assert len(barrier_nodes) >= 2  # At least 2 barriers for operations spanning phases

        block_node = graph.nodes[op_block.object_type + ":" + op_block.row_id]
        zone_node = graph.nodes[op_zone.object_type + ":" + op_zone.row_id]
        host_node = graph.nodes[op_host.object_type + ":" + op_host.row_id]

        # Verify Block is in Phase 2, so create phase 2 barrier should depend on it
        barrier_create_phase_2 = graph.nodes["system_barrier:barrier_create_phase_2"]
        assert block_node.node_id in barrier_create_phase_2.dependencies

        # Verify Zone is in Phase 3, so it should depend on previous barrier (create Phase 2 barrier)
        assert barrier_create_phase_2.node_id in zone_node.dependencies

        # Verify create Phase 3 barrier depends on Zone
        barrier_create_phase_3 = graph.nodes["system_barrier:barrier_create_phase_3"]
        assert zone_node.node_id in barrier_create_phase_3.dependencies

        # Verify Host is in Phase 5, so it should depend on previous barrier
        # Using depth to verify order
        assert block_node.depth < zone_node.depth
        assert zone_node.depth < host_node.depth

    def test_parent_child_dependency_network_block(self, graph):
        """Test dependency between Network and Block based on path."""
        # Block: 10.0.0.0/8
        op_block = self.create_op("ip4_block", "block1", config="Default", cidr="10.0.0.0/8")

        # Network: 10.1.0.0/16, parent path 10.0.0.0/8
        op_network = self.create_op(
            "ip4_network",
            "net1",
            config="Default",
            cidr="10.1.0.0/16",
            parent="10.0.0.0/8",
        )

        graph.build_from_operations([op_block, op_network])

        block_node_id = op_block.object_type + ":" + op_block.row_id
        net_node_id = op_network.object_type + ":" + op_network.row_id

        net_node = graph.nodes[net_node_id]
        assert block_node_id in net_node.dependencies

    def test_parent_child_dependency_address_network(self, graph):
        """Test dependency between Address and Network based on path."""
        # Network: 10.1.0.0/16
        op_network = self.create_op("ip4_network", "net1", config="Default", cidr="10.1.0.0/16")

        # Address: 10.1.0.1, parent path 10.1.0.0/16
        # Note: Address uses 'parent' to point to network CIDR in this logic
        op_address = self.create_op("ip4_address", "addr1", config="Default", parent="10.1.0.0/16")

        graph.build_from_operations([op_network, op_address])

        net_node_id = op_network.object_type + ":" + op_network.row_id
        addr_node_id = op_address.object_type + ":" + op_address.row_id

        addr_node = graph.nodes[addr_node_id]
        assert net_node_id in addr_node.dependencies

    def test_dns_record_dependency(self, graph):
        """Test dependency between DNS Record and Zone."""
        # Zone: example.com
        op_zone = self.create_op(
            "dns_zone",
            "zone1",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
        )

        # Host Record: host.example.com
        op_host = self.create_op(
            "host_record",
            "host1",
            config="Default",
            view_path="Internal",
            zone_name="example.com",
        )

        graph.build_from_operations([op_zone, op_host])

        zone_node_id = op_zone.object_type + ":" + op_zone.row_id
        host_node_id = op_host.object_type + ":" + op_host.row_id

        host_node = graph.nodes[host_node_id]
        assert zone_node_id in host_node.dependencies

    def test_dhcp_dependency_by_id(self, graph):
        """Test dependency between DHCP Range and Network by ID."""
        # Network
        op_network = self.create_op("ip4_network", "net1", network_id=12345)

        # DHCP Range
        op_range = self.create_op("ipv4_dhcp_range", "range1", network_id=12345)

        graph.build_from_operations([op_network, op_range])

        net_node_id = op_network.object_type + ":" + op_network.row_id
        range_node_id = op_range.object_type + ":" + op_range.row_id

        range_node = graph.nodes[range_node_id]
        assert net_node_id in range_node.dependencies

    def test_delete_dependency(self, graph):
        """Test that deleting a parent waits for deleting a child."""
        # Parent: Network
        op_parent = self.create_op(
            "ip4_network",
            "net1",
            operation_type=OperationType.DELETE,
            config="Default/10.0.0.0/8",
        )

        # Child: Address
        op_child = self.create_op(
            "ip4_address",
            "addr1",
            operation_type=OperationType.DELETE,
            config="Default/10.0.0.0/8/10.1.0.0/16",
        )

        # In _is_child_of, it checks if child_path.startswith(parent)
        # parent path: Default/10.0.0.0/8
        # child path: Default/10.0.0.0/8/10.1.0.0/16
        # Matches!

        graph.build_from_operations([op_parent, op_child])

        parent_node_id = op_parent.object_type + ":" + op_parent.row_id
        child_node_id = op_child.object_type + ":" + op_child.row_id

        # Parent DELETE should depend on Child DELETE (Child must be deleted first)
        parent_node = graph.nodes[parent_node_id]
        assert child_node_id in parent_node.dependencies

    def test_complex_cycle_detection(self, graph):
        """Test detection of a longer cycle A->B->C->A."""
        op_a = self.create_op("A", "a")
        op_b = self.create_op("B", "b")
        op_c = self.create_op("C", "c")

        node_a = graph.add_operation(op_a)
        node_b = graph.add_operation(op_b)
        node_c = graph.add_operation(op_c)

        graph.add_dependency(node_b.node_id, node_a.node_id)  # B depends on A
        graph.add_dependency(node_c.node_id, node_b.node_id)  # C depends on B

        from src.importer.utils.exceptions import CyclicDependencyError

        with pytest.raises(CyclicDependencyError):
            graph.add_dependency(node_a.node_id, node_c.node_id)  # A depends on C -> Cycle!

    def test_validate_graph(self, graph):
        """Test the validate method."""
        op_a = self.create_op("A", "a")
        graph.add_operation(op_a)
        assert graph.validate() is True

        # Corrupt the graph manually to fail validation
        graph.nodes[op_a.object_type + ":" + op_a.row_id].dependencies.add("non_existent")
        graph._validated = False  # Force re-validation

        with pytest.raises(ValueError, match="Invalid dependency reference"):
            graph.validate()
