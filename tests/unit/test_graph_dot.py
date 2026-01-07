from src.importer.dependency.graph import DependencyGraph, Operation
from src.importer.models.operations import OperationStatus, OperationType


def test_to_dot():
    """Test DOT generation."""
    graph = DependencyGraph()

    # Create valid Operations (requires pydantic model)
    # We can rely on the fact that Operation validation might be bypassed if we construct dicts or mocks?
    # No, Operation is a Pydantic model.
    # We need to provide minimal valid fields.

    op1 = Operation(
        row_id="1",
        operation_type=OperationType.CREATE,
        object_type="network",
        resource_id=None,
        payload={},
        csv_row=None,
        status=OperationStatus.PENDING,
    )
    op2 = Operation(
        row_id="2",
        operation_type=OperationType.CREATE,
        object_type="address",
        resource_id=None,
        payload={},
        csv_row=None,
        status=OperationStatus.PENDING,
    )

    graph.add_operation(op1)
    graph.add_operation(op2)

    # Add dependency: op2 depends on op1
    graph.add_dependency(dependent_id="address:2", dependency_id="network:1")

    dot = graph.to_dot()

    print(dot)  # For debug

    assert "digraph DependencyGraph {" in dot
    assert '"network:1" [label="network\\n1\\n(create)" fillcolor="#d4edda"];' in dot
    assert '"address:2" [label="address\\n2\\n(create)" fillcolor="#d4edda"];' in dot
    assert '"network:1" -> "address:2";' in dot
