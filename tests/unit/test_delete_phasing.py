"""Tests for delete operation phasing in dependency graph.

These tests verify that DELETE operations are properly phased to run
BEFORE CREATE/UPDATE operations (Fix 2.2).
"""

import pytest
from importer.dependency.graph import DELETE_PHASE_ORDER, PHASE_ORDER, DependencyGraph
from importer.models.operations import Operation, OperationStatus, OperationType


class TestDeletePhaseOrder:
    """Tests for DELETE_PHASE_ORDER constant."""

    def test_delete_phase_order_is_reversed(self) -> None:
        """Verify DELETE_PHASE_ORDER is reverse of PHASE_ORDER."""
        assert DELETE_PHASE_ORDER == list(reversed(PHASE_ORDER))

    def test_delete_phases_have_same_types(self) -> None:
        """Verify delete phases contain all the same object types."""
        phase_types = set()
        for phase in PHASE_ORDER:
            phase_types.update(phase)

        delete_types = set()
        for phase in DELETE_PHASE_ORDER:
            delete_types.update(phase)

        assert phase_types == delete_types


class TestDeletePhasing:
    """Tests for delete phasing in DependencyGraph."""

    @pytest.fixture
    def graph(self) -> DependencyGraph:
        """Create a fresh dependency graph."""
        return DependencyGraph()

    def create_operation(
        self,
        row_id: str,
        op_type: OperationType,
        obj_type: str,
        resource_id: int | None = None,
    ) -> Operation:
        """Helper to create test operations."""
        return Operation(
            row_id=row_id,
            operation_type=op_type,
            object_type=obj_type,
            resource_id=resource_id,
            payload={},
            csv_row=None,
            status=OperationStatus.PENDING,
        )

    def test_delete_barriers_created(self, graph: DependencyGraph) -> None:
        """Test that delete phase barriers are created."""
        # Add delete operations for different phases
        delete_network = self.create_operation("d1", OperationType.DELETE, "ip4_network", 100)
        delete_zone = self.create_operation("d2", OperationType.DELETE, "dns_zone", 200)

        operations = [delete_network, delete_zone]
        graph.build_from_operations(operations)

        # Find delete phase barriers
        delete_barriers = [
            node
            for node in graph.nodes.values()
            if "barrier_delete_phase" in str(node.operation.row_id)
        ]

        # Should have barriers for delete phases with operations
        assert len(delete_barriers) >= 1

    def test_create_barriers_created(self, graph: DependencyGraph) -> None:
        """Test that create phase barriers are created."""
        # Add create operations for different phases
        create_block = self.create_operation("c1", OperationType.CREATE, "ip4_block")
        create_zone = self.create_operation("c2", OperationType.CREATE, "dns_zone")

        operations = [create_block, create_zone]
        graph.build_from_operations(operations)

        # Find create phase barriers
        create_barriers = [
            node
            for node in graph.nodes.values()
            if "barrier_create_phase" in str(node.operation.row_id)
        ]

        assert len(create_barriers) >= 1

    def test_deletes_before_creates_with_same_phase(self, graph: DependencyGraph) -> None:
        """Test that deletes run before creates in the same phase."""
        # Create operations in the same phase (ip4_network is phase 0)
        delete_network = self.create_operation("d1", OperationType.DELETE, "ip4_network", 100)
        create_network = self.create_operation("c1", OperationType.CREATE, "ip4_network")

        operations = [delete_network, create_network]
        graph.build_from_operations(operations)

        # Get execution batches
        batches = graph.get_execution_batches()

        # Find the batches containing our operations
        delete_batch_idx = None
        create_batch_idx = None

        for batch_idx, batch in enumerate(batches):
            for node in batch:
                if node.operation.row_id == "d1":
                    delete_batch_idx = batch_idx
                elif node.operation.row_id == "c1":
                    create_batch_idx = batch_idx

        # Delete should be in an earlier batch (lower index)
        assert delete_batch_idx is not None
        assert create_batch_idx is not None
        assert delete_batch_idx < create_batch_idx

    def test_delete_recreate_same_resource_ordered(self, graph: DependencyGraph) -> None:
        """Test delete+recreate of same resource type is properly ordered."""
        # Simulate delete and recreate of a zone
        delete_zone = self.create_operation("delete_zone", OperationType.DELETE, "dns_zone", 500)
        create_zone = self.create_operation("create_zone", OperationType.CREATE, "dns_zone")

        operations = [delete_zone, create_zone]
        graph.build_from_operations(operations)

        batches = graph.get_execution_batches()

        # Find batch indices
        delete_idx = None
        create_idx = None

        for batch_idx, batch in enumerate(batches):
            for node in batch:
                if node.operation.row_id == "delete_zone":
                    delete_idx = batch_idx
                elif node.operation.row_id == "create_zone":
                    create_idx = batch_idx

        # Delete MUST come before create
        assert delete_idx is not None, "Delete operation not found in plan"
        assert create_idx is not None, "Create operation not found in plan"
        assert (
            delete_idx < create_idx
        ), f"Delete (batch {delete_idx}) should come before Create (batch {create_idx})"

    def test_child_deleted_before_parent(self, graph: DependencyGraph) -> None:
        """Test that child resources are deleted before parents."""
        # Delete a record (phase 3 in normal order, phase 2 in delete order)
        delete_record = self.create_operation("d_record", OperationType.DELETE, "host_record", 300)
        # Delete a zone (phase 1 in normal order, phase 4 in delete order)
        delete_zone = self.create_operation("d_zone", OperationType.DELETE, "dns_zone", 200)

        operations = [delete_record, delete_zone]
        graph.build_from_operations(operations)

        batches = graph.get_execution_batches()

        # Find batch indices
        record_idx = None
        zone_idx = None

        for batch_idx, batch in enumerate(batches):
            for node in batch:
                if node.operation.row_id == "d_record":
                    record_idx = batch_idx
                elif node.operation.row_id == "d_zone":
                    zone_idx = batch_idx

        # Record (child) should be deleted before zone (parent)
        # In DELETE_PHASE_ORDER, children come before parents
        assert record_idx is not None
        assert zone_idx is not None
        assert (
            record_idx < zone_idx
        ), f"Record delete (batch {record_idx}) should come before zone delete (batch {zone_idx})"

    def test_mixed_operations_ordering(self, graph: DependencyGraph) -> None:
        """Test that mixed delete/create operations are properly ordered."""
        # Add various operations
        ops = [
            self.create_operation("delete_network", OperationType.DELETE, "ip4_network", 100),
            self.create_operation("delete_zone", OperationType.DELETE, "dns_zone", 200),
            self.create_operation("create_block", OperationType.CREATE, "ip4_block"),
            self.create_operation("create_zone", OperationType.CREATE, "dns_zone"),
            self.create_operation("update_record", OperationType.UPDATE, "host_record", 300),
        ]

        graph.build_from_operations(ops)

        batches = graph.get_execution_batches()

        # Find all delete and create/update operations
        delete_batches = []
        create_update_batches = []

        for batch_idx, batch in enumerate(batches):
            for node in batch:
                if node.operation.operation_type == OperationType.DELETE:
                    delete_batches.append(batch_idx)
                elif node.operation.operation_type in (OperationType.CREATE, OperationType.UPDATE):
                    create_update_batches.append(batch_idx)

        if delete_batches and create_update_batches:
            # All deletes should have lower batch indices than creates/updates
            max_delete = max(delete_batches)
            min_create = min(create_update_batches)
            assert (
                max_delete < min_create
            ), f"Max delete batch ({max_delete}) should be less than min create batch ({min_create})"
