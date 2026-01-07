"""Tests for DependencyGraph DNS record dependencies."""

from src.importer.dependency.graph import DependencyGraph
from src.importer.models.csv_row import (
    AliasRecordRow,
    ExternalHostRecordRow,
    HostRecordRow,
    MXRecordRow,
    SRVRecordRow,
)
from src.importer.models.operations import Operation, OperationStatus, OperationType


def create_operation(row_id, object_type, csv_row):
    return Operation(
        row_id=row_id,
        operation_type=OperationType.CREATE,
        object_type=object_type,
        resource_id=None,
        payload={},
        csv_row=csv_row,
        status=OperationStatus.PENDING,
    )


def test_alias_record_dependency():
    """Test ALIAS record depends on its linked HostRecord."""
    graph = DependencyGraph()

    # Host Record
    host_row = HostRecordRow(
        row_id="1",
        object_type="host_record",
        action="create",
        config="Def",
        view_path="Int",
        name="host.example.com",
        addresses="1.1.1.1",
    )
    host_op = create_operation("1", "host_record", host_row)
    host_node = graph.add_operation(host_op)

    # Alias Record
    alias_row = AliasRecordRow(
        row_id="2",
        object_type="alias_record",
        action="create",
        config="Def",
        view_path="Int",
        name="www",
        cname="host.example.com",
    )
    alias_op = create_operation("2", "alias_record", alias_row)
    alias_node = graph.add_operation(alias_op)

    # Build dependencies
    graph.build_from_operations([host_op, alias_op])

    # Check dependency
    assert host_node.node_id in alias_node.dependencies
    assert alias_node.node_id in host_node.dependents


def test_mx_record_dependency():
    """Test MX record depends on its exchange HostRecord."""
    graph = DependencyGraph()

    # Exchange Host
    host_row = HostRecordRow(
        row_id="1",
        object_type="host_record",
        action="create",
        config="Def",
        view_path="Int",
        name="mail.example.com",
        addresses="1.1.1.1",
    )
    host_op = create_operation("1", "host_record", host_row)
    host_node = graph.add_operation(host_op)

    # MX Record
    mx_row = MXRecordRow(
        row_id="2",
        object_type="mx_record",
        action="create",
        config="Def",
        view_path="Int",
        name="example.com",
        exchange="mail.example.com",
        preference=10,
    )
    mx_op = create_operation("2", "mx_record", mx_row)
    mx_node = graph.add_operation(mx_op)

    # Build dependencies
    graph.build_from_operations([host_op, mx_op])

    # Check dependency
    assert host_node.node_id in mx_node.dependencies


def test_srv_record_dependency():
    """Test SRV record depends on its target ExternalHostRecord."""
    graph = DependencyGraph()

    # Target External Host
    ext_host_row = ExternalHostRecordRow(
        row_id="1",
        object_type="external_host_record",
        action="create",
        config="Def",
        view_path="Int",
        zone_name="ext",
        name="sip.external.com",
    )
    ext_host_op = create_operation("1", "external_host_record", ext_host_row)
    ext_host_node = graph.add_operation(ext_host_op)

    # SRV Record
    srv_row = SRVRecordRow(
        row_id="2",
        object_type="srv_record",
        action="create",
        config="Def",
        view_path="Int",
        name="_sip._tcp",
        target="sip.external.com",
        port=5060,
        priority=10,
        weight=10,
    )
    srv_op = create_operation("2", "srv_record", srv_row)
    srv_node = graph.add_operation(srv_op)

    # Build dependencies
    graph.build_from_operations([ext_host_op, srv_op])

    # Check dependency
    assert ext_host_node.node_id in srv_node.dependencies
