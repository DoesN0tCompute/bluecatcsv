"""Integration tests for deployment role workflows."""

from unittest.mock import AsyncMock

import pytest

from src.importer.config import ImporterConfig, PolicyConfig
from src.importer.execution.executor import OperationExecutor
from src.importer.models.operations import OperationType


@pytest.mark.asyncio
async def test_executor_dhcp_deployment_role_workflow():
    """Test complete DHCP deployment role workflow through executor."""
    # Mock the BAM client
    mock_client = AsyncMock()
    mock_client.create_dhcp_deployment_role.return_value = {
        "id": 123,
        "name": "Test DHCP Role",
        "properties": {"type": "DHCPDeploymentRole"},
    }

    # Create config and policy
    ImporterConfig()
    policy = PolicyConfig(max_concurrent_operations=10)

    # Create executor
    executor = OperationExecutor(
        bam_client=mock_client, policy=policy, allow_dangerous_operations=False
    )

    # Create a test operation
    from src.importer.models.csv_row import DHCPDeploymentRoleRow
    from src.importer.models.operations import Operation

    operation = Operation(
        row_id=1,
        operation_type=OperationType.CREATE,
        object_type="dhcp_deployment_role",
        resource_id=None,
        payload={"network_id": 456},
        csv_row=DHCPDeploymentRoleRow(
            row_id=1,
            object_type="dhcp_deployment_role",
            action="create",
            name="Test DHCP Role",
            role_type="PRIMARY",
            server_group="DHCP-Servers",
        ),
    )

    # Execute the operation
    result = await executor._execute_operation(operation)

    # Verify success
    assert result.success is True
    assert result.row_id == 1
    assert result.resource_id == 123

    # Verify the BAM client was called correctly
    mock_client.create_dhcp_deployment_role.assert_called_once()
    call_args = mock_client.create_dhcp_deployment_role.call_args
    assert call_args.kwargs["parent_id"] == 456
    assert call_args.kwargs["parent_type"] == "networks"
    assert call_args.kwargs["name"] == "Test DHCP Role"
    assert call_args.kwargs["role_type"] == "PRIMARY"
    assert call_args.kwargs["server_group"] == "DHCP-Servers"


@pytest.mark.asyncio
async def test_executor_dns_deployment_role_workflow():
    """Test complete DNS deployment role workflow through executor."""
    # Mock the BAM client
    mock_client = AsyncMock()
    mock_client.create_dns_deployment_role.return_value = {
        "id": 456,
        "name": "Test DNS Role",
        "properties": {"type": "DNSDeploymentRole"},
    }
    # Mock interface resolution
    mock_client.resolve_interface_string.return_value = 12345

    # Create config and policy
    ImporterConfig()
    policy = PolicyConfig(max_concurrent_operations=10)

    # Create executor
    executor = OperationExecutor(
        bam_client=mock_client, policy=policy, allow_dangerous_operations=False
    )

    # Create a test operation
    from src.importer.models.csv_row import DNSDeploymentRoleRow
    from src.importer.models.operations import Operation

    operation = Operation(
        row_id=2,
        operation_type=OperationType.CREATE,
        object_type="dns_deployment_role",
        resource_id=None,
        payload={"zone_id": 789},
        csv_row=DNSDeploymentRoleRow(
            row_id=2,
            object_type="dns_deployment_role",
            action="create",
            name="Test DNS Role",
            zone_path="Internal/example.com",
            role_type="PRIMARY",
            interfaces="server1:interface1|server2:interface2",
        ),
    )

    # Execute the operation
    result = await executor._execute_operation(operation)

    # Verify success
    assert result.success is True
    assert result.row_id == 2
    assert result.resource_id == 456

    # Verify the BAM client was called correctly
    mock_client.create_dns_deployment_role.assert_called_once()
    call_args = mock_client.create_dns_deployment_role.call_args
    assert call_args.kwargs["parent_id"] == 789
    assert call_args.kwargs["parent_type"] == "zones"
    assert call_args.kwargs["name"] == "Test DNS Role"
    assert call_args.kwargs["role_type"] == "PRIMARY"
    assert len(call_args.kwargs["interfaces"]) == 2

    # Verify interface resolution was called
    assert mock_client.resolve_interface_string.call_count == 2
    mock_client.resolve_interface_string.assert_any_call("server1:interface1")
    mock_client.resolve_interface_string.assert_any_call("server2:interface2")


@pytest.mark.asyncio
async def test_executor_dhcp_deployment_option_workflow():
    """Test DHCP deployment option workflow through executor."""
    # Mock the BAM client
    mock_client = AsyncMock()
    mock_client.create_dhcpv4_client_deployment_option.return_value = {
        "id": 789,
        "name": "DNS Servers",
        "code": 6,
        "properties": {"type": "DHCPv4ClientOption"},
    }

    # Create config and policy
    ImporterConfig()
    policy = PolicyConfig(max_concurrent_operations=10)

    # Create executor
    executor = OperationExecutor(
        bam_client=mock_client, policy=policy, allow_dangerous_operations=False
    )

    # Create a test operation
    from src.importer.models.csv_row import DHCPv4ClientDeploymentOptionRow
    from src.importer.models.operations import Operation

    operation = Operation(
        row_id=3,
        operation_type=OperationType.CREATE,
        object_type="dhcpv4_client_deployment_option",
        resource_id=None,
        payload={"network_id": 100, "value": "8.8.8.8,8.8.4.4"},
        csv_row=DHCPv4ClientDeploymentOptionRow(
            row_id=3,
            object_type="dhcpv4_client_deployment_option",
            action="create",
            name="DNS Servers",
            code=6,
            value="8.8.8.8,8.8.4.4",
            server_scope="DHCP_SERVER",
        ),
    )

    # Execute the operation
    result = await executor._execute_operation(operation)

    # Verify success
    assert result.success is True
    assert result.row_id == 3
    assert result.resource_id == 789

    # Verify the BAM client was called correctly
    mock_client.create_dhcpv4_client_deployment_option.assert_called_once()
    call_args = mock_client.create_dhcpv4_client_deployment_option.call_args
    assert call_args.kwargs["network_id"] == 100
    assert call_args.kwargs["name"] == "DNS Servers"
    assert call_args.kwargs["code"] == 6
    assert call_args.kwargs["value"] == "8.8.8.8,8.8.4.4"
    assert call_args.kwargs["server_scope"] == "DHCP_SERVER"


@pytest.mark.asyncio
async def test_executor_mixed_deployment_role_workflow():
    """Test mixed deployment role operations through executor."""
    # Mock the BAM client
    mock_client = AsyncMock()
    mock_client.create_dhcp_deployment_role.return_value = {"id": 123}
    mock_client.create_dns_deployment_role.return_value = {"id": 456}
    mock_client.create_dhcpv4_client_deployment_option.return_value = {"id": 789}
    mock_client.resolve_interface_string.return_value = 12345

    # Create config and policy
    ImporterConfig()
    policy = PolicyConfig(max_concurrent_operations=10)

    # Create executor
    executor = OperationExecutor(
        bam_client=mock_client, policy=policy, allow_dangerous_operations=False
    )

    # Create multiple operations
    from src.importer.models.csv_row import (
        DHCPDeploymentRoleRow,
        DHCPv4ClientDeploymentOptionRow,
        DNSDeploymentRoleRow,
    )
    from src.importer.models.operations import Operation

    operations = [
        Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={"network_id": 456},
            csv_row=DHCPDeploymentRoleRow(
                row_id=1, object_type="dhcp_deployment_role", action="create", name="DHCP Role"
            ),
        ),
        Operation(
            row_id=2,
            operation_type=OperationType.CREATE,
            object_type="dns_deployment_role",
            resource_id=None,
            payload={"zone_id": 789},
            csv_row=DNSDeploymentRoleRow(
                row_id=2,
                object_type="dns_deployment_role",
                action="create",
                name="DNS Role",
                zone_path="Internal/example.com",
                interfaces="server1:interface1",
            ),
        ),
        Operation(
            row_id=3,
            operation_type=OperationType.CREATE,
            object_type="dhcpv4_client_deployment_option",
            resource_id=None,
            payload={"network_id": 100, "value": "8.8.8.8"},
            csv_row=DHCPv4ClientDeploymentOptionRow(
                row_id=3,
                object_type="dhcpv4_client_deployment_option",
                action="create",
                name="DNS Option",
                code=6,
                value="8.8.8.8",
            ),
        ),
    ]

    # Execute all operations
    results = []
    for operation in operations:
        result = await executor._execute_operation(operation)
        results.append(result)

    # Verify all succeeded
    assert len(results) == 3
    assert all(result.success for result in results)
    assert results[0].resource_id == 123
    assert results[1].resource_id == 456
    assert results[2].resource_id == 789

    # Verify each method was called
    mock_client.create_dhcp_deployment_role.assert_called_once()
    mock_client.create_dns_deployment_role.assert_called_once()
    mock_client.create_dhcpv4_client_deployment_option.assert_called_once()


@pytest.mark.asyncio
async def test_executor_deployment_role_error_handling():
    """Test error handling in deployment role workflows."""
    # Mock the BAM client to raise an exception
    mock_client = AsyncMock()
    mock_client.create_dhcp_deployment_role.side_effect = Exception("Network not found")

    # Create config and policy
    ImporterConfig()
    policy = PolicyConfig(max_concurrent_operations=10)

    # Create executor
    executor = OperationExecutor(
        bam_client=mock_client, policy=policy, allow_dangerous_operations=False
    )

    # Create a test operation that will fail
    from src.importer.models.csv_row import DHCPDeploymentRoleRow
    from src.importer.models.operations import Operation

    operation = Operation(
        row_id=1,
        operation_type=OperationType.CREATE,
        object_type="dhcp_deployment_role",
        resource_id=None,
        payload={"network_id": 999},  # Invalid network ID
        csv_row=DHCPDeploymentRoleRow(
            row_id=1, object_type="dhcp_deployment_role", action="create", name="Error Role"
        ),
    )

    # Execute the operation
    result = await executor._execute_operation(operation)

    # Verify error handling
    assert result.success is False
    assert result.row_id == 1
    assert result.error_message == "Network not found"
    assert result.resource_id is None

    # Verify the BAM client was called
    mock_client.create_dhcp_deployment_role.assert_called_once()


@pytest.mark.asyncio
async def test_executor_deployment_role_dry_run():
    """Test deployment role operations in dry-run mode."""
    # Mock the BAM client (should not be called)
    mock_client = AsyncMock()

    # Create config and policy
    ImporterConfig()
    policy = PolicyConfig(max_concurrent_operations=10)

    # Create executor in dry-run mode
    executor = OperationExecutor(
        bam_client=mock_client, policy=policy, allow_dangerous_operations=False
    )
    executor.dry_run = True

    # Create a test operation
    from src.importer.models.csv_row import DHCPDeploymentRoleRow
    from src.importer.models.operations import Operation

    operation = Operation(
        row_id=1,
        operation_type=OperationType.CREATE,
        object_type="dhcp_deployment_role",
        resource_id=None,
        payload={"network_id": 456},
        csv_row=DHCPDeploymentRoleRow(
            row_id=1, object_type="dhcp_deployment_role", action="create", name="Dry Run Role"
        ),
    )

    # Execute the operation
    result = await executor._execute_operation(operation)

    # Verify dry-run behavior
    assert result.success is True
    assert result.row_id == 1
    assert result.resource_id is not None

    # Verify the BAM client was NOT called
    mock_client.create_dhcp_deployment_role.assert_not_called()
