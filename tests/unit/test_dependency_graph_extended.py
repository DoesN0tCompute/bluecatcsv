"""Extended tests for the DependencyGraph class focusing on edge cases and robustness."""

from unittest.mock import MagicMock

import pytest

from src.importer.dependency.graph import DependencyGraph
from src.importer.models.operations import Operation, OperationStatus, OperationType


class TestDependencyGraphExtended:
    """Extended test suite for DependencyGraph."""

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

    def test_cidr_in_path_strictness(self, graph):
        """
        Test _cidr_in_path strict segment matching.

        Protects against: False positives where a CIDR matches a substring
        of a path segment (e.g., '1.1.1.1' matching '1.1.1.10').
        """
        # Case 1: Exact match with prefix
        assert graph._cidr_in_path("10.0.0.0/8", "/IPv4/10.0.0.0/8") is True

        # Case 2: Exact match in deeper path
        assert graph._cidr_in_path("10.1.0.0/16", "/IPv4/10.0.0.0/8/10.1.0.0/16") is True

        # Case 3: Partial IP match (should fail)
        # 10.1.0.0 should not match 10.1.0.00 (string suffix)
        assert graph._cidr_in_path("10.1.0.0/16", "/IPv4/10.1.0.00/16") is False

        # Case 4: Prefix mismatch
        assert graph._cidr_in_path("10.0.0.0/8", "/IPv4/10.0.0.0/80") is False

        # Case 5: Partial segment match (e.g. 10.0.0.0 matching 110.0.0.0)
        assert graph._cidr_in_path("10.0.0.0/8", "/IPv4/110.0.0.0/8") is False

        # Case 6: IP only (no prefix in CIDR)
        assert graph._cidr_in_path("10.0.0.1", "/IPv4/10.0.0.0/8/10.0.0.1") is True
        assert graph._cidr_in_path("10.0.0.1", "/IPv4/10.0.0.0/8/10.0.0.11") is False

    def test_reference_dependencies_alias_to_host(self, graph):
        """
        Test that AliasRecord (CNAME) correctly depends on the target HostRecord.

        Protects against: CNAMEs being created before their target A records exist,
        which could lead to dangling records or validation errors.
        """
        # Target Host Record
        op_host = self.create_op(
            "host_record",
            "host1",
            operation_type=OperationType.CREATE,
            name="web.example.com",
            zone_name="example.com",
            view_path="Internal",
        )

        # Alias Record pointing to Host
        op_alias = self.create_op(
            "alias_record",
            "alias1",
            operation_type=OperationType.CREATE,
            name="www.example.com",
            linked_record_name="web.example.com",  # Points to host1
            zone_name="example.com",
            view_path="Internal",
        )

        graph.build_from_operations([op_host, op_alias])

        host_node_id = op_host.object_type + ":" + op_host.row_id
        alias_node_id = op_alias.object_type + ":" + op_alias.row_id

        alias_node = graph.nodes[alias_node_id]

        # Verify dependency exists
        assert host_node_id in alias_node.dependencies

        # Verify depth: Host (0) -> Alias (1)
        assert graph.nodes[host_node_id].depth < graph.nodes[alias_node_id].depth

    def test_global_delete_before_create(self, graph):
        """
        Test that ALL delete operations execute before ANY create operations,
        even if the create operation is for a parent resource of the deleted resource.

        Scenario:
        - Delete an IPv4 Address (Phase 3 in delete order)
        - Create a Block (Phase 0 in create order)

        Normal hierarchy: Block is parent of Address.
        But Phasing Rule: Deletes happen first.

        Protects against: Race conditions where we might try to create a parent
        while a child is being deleted, or general state inconsistency.
        """
        op_create_block = self.create_op(
            "ip4_block", "block_create", operation_type=OperationType.CREATE
        )

        op_delete_address = self.create_op(
            "ip4_address", "addr_delete", operation_type=OperationType.DELETE
        )

        graph.build_from_operations([op_create_block, op_delete_address])

        create_node = graph.nodes[op_create_block.object_type + ":" + op_create_block.row_id]
        delete_node = graph.nodes[op_delete_address.object_type + ":" + op_delete_address.row_id]

        # Check depths to verify execution order
        # Delete should happen first (lower depth)
        # Create should happen later (higher depth due to barriers)
        assert delete_node.depth < create_node.depth

        # Verify there is a dependency path from Delete to Create
        # We can walk the graph or check batches
        batches = graph.get_execution_batches()

        delete_batch_idx = -1
        create_batch_idx = -1

        for idx, batch in enumerate(batches):
            node_ids = [n.node_id for n in batch]
            if delete_node.node_id in node_ids:
                delete_batch_idx = idx
            if create_node.node_id in node_ids:
                create_batch_idx = idx

        assert delete_batch_idx != -1
        assert create_batch_idx != -1
        assert delete_batch_idx < create_batch_idx

    def test_self_dependency_prevention(self, graph):
        """
        Test that an operation cannot depend on itself.

        Protects against: Infinite loops or graph validity errors if logic
        accidentally links a node to itself.
        """
        op = self.create_op("network", "net1")
        node = graph.add_operation(op)

        # Try to add self-dependency
        graph.add_dependency(node.node_id, node.node_id)

        # Should be ignored
        assert len(node.dependencies) == 0
        assert len(node.dependents) == 0

        # Graph should still validate
        assert graph.validate() is True

    def test_orphan_operations_have_no_dependencies(self, graph):
        """
        Test that ORPHAN operations do not get automatic dependencies.

        Protects against: Orphan resources (which exist outside the tree we are managing)
        getting stuck waiting for tree resources.
        """
        # Block: 10.0.0.0/8
        op_block = self.create_op("ip4_block", "block1", config="Default", cidr="10.0.0.0/8")

        # Orphan Network: 10.0.0.0/16 inside the block
        # Even though it's inside, if marked ORPHAN, it shouldn't depend on the block creation
        # (Orphan ops are typically used for reference or "ignore" logic)
        op_orphan = self.create_op(
            "ip4_network",
            "orphan1",
            operation_type=OperationType.ORPHAN,
            config="Default",
            parent="10.0.0.0/8",  # Path matches block
            cidr="10.0.0.0/16",
        )

        graph.build_from_operations([op_block, op_orphan])

        orphan_node = graph.nodes[op_orphan.object_type + ":" + op_orphan.row_id]

        # Should have NO dependencies
        assert len(orphan_node.dependencies) == 0
