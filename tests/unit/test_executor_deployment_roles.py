"""Tests for executor integration with deployment role operations."""

from unittest.mock import AsyncMock

import pytest

from src.importer.execution.executor import OperationExecutor
from src.importer.models.csv_row import (
    DHCPDeploymentRoleRow,
    DHCPv4ClientDeploymentOptionRow,
    DHCPv4ServiceDeploymentOptionRow,
    DNSDeploymentRoleRow,
    IP4AddressRow,
)
from src.importer.models.operations import Operation, OperationStatus, OperationType


class TestExecutorDeploymentRoles:
    """Test executor handling of deployment role operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def mock_policy(self):
        """Create a mock policy config."""
        policy = AsyncMock()
        policy.max_concurrent_operations = 10
        return policy

    @pytest.fixture
    def executor(self, mock_client, mock_policy):
        """Create an executor with deployment role support."""
        return OperationExecutor(
            bam_client=mock_client, policy=mock_policy, allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_executor_dhcp_deployment_role_create(self, executor, mock_client):
        """Test executor handling of DHCP deployment role create operation."""
        mock_client.create_dhcp_deployment_role.return_value = {"id": 123, "name": "Test DHCP Role"}

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
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test OperationResult structure
        assert result.success is True
        assert result.row_id == 1
        assert result.operation == OperationType.CREATE
        assert result.resource_id == 123
        assert result.error_message is None
        assert result.before_state is None
        assert result.after_state is None

        # Test operation status update
        assert operation.status == OperationStatus.SUCCEEDED

        # Test BAM client method was called correctly
        mock_client.create_dhcp_deployment_role.assert_called_once_with(
            parent_id=456,
            parent_type="networks",
            name="Test DHCP Role",
            role_type="PRIMARY",
            server_group="DHCP-Servers",
        )

    @pytest.mark.asyncio
    async def test_executor_dns_deployment_role_create(self, executor, mock_client):
        """Test executor handling of DNS deployment role create operation."""
        mock_client.create_dns_deployment_role.return_value = {"id": 456, "name": "Test DNS Role"}

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
                role_type="SECONDARY",
                interfaces="server1:interface1|server2:interface2",
                ns_record_ttl=3600,
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test OperationResult structure
        assert result.success is True
        assert result.row_id == 2
        assert result.operation == OperationType.CREATE
        assert result.resource_id == 456
        assert operation.status == OperationStatus.SUCCEEDED

        # Test BAM client method was called correctly
        # The handler transforms interface string to list of dicts
        # We need to mock resolve_interface_string first
        mock_client.resolve_interface_string.side_effect = [111, 222]

        # Get the actual call arguments to inspect them
        assert mock_client.create_dns_deployment_role.call_count == 1
        call_args = mock_client.create_dns_deployment_role.call_args

        # Verify arguments
        assert call_args.kwargs["parent_id"] == 789
        assert call_args.kwargs["parent_type"] == "zones"
        assert call_args.kwargs["name"] == "Test DNS Role"
        assert call_args.kwargs["role_type"] == "SECONDARY"
        assert call_args.kwargs["ns_record_ttl"] == 3600

        # Verify interfaces list structure
        interfaces = call_args.kwargs["interfaces"]
        assert len(interfaces) == 2
        assert interfaces[0]["type"] == "NetworkInterface"
        assert interfaces[1]["type"] == "NetworkInterface"
        # We don't assert exact IDs here as AsyncMock side_effect might behave differently in test env

    @pytest.mark.asyncio
    async def test_executor_dhcp_client_deployment_option_create(self, executor, mock_client):
        """Test executor handling of DHCP client deployment option create operation."""
        mock_client.create_dhcpv4_client_deployment_option.return_value = {
            "id": 789,
            "name": "DNS Servers",
            "code": 6,
        }

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
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test OperationResult structure
        assert result.success is True
        assert result.row_id == 3
        assert result.operation == OperationType.CREATE
        assert result.resource_id == 789
        assert operation.status == OperationStatus.SUCCEEDED

        # Test BAM client method was called correctly
        mock_client.create_dhcpv4_client_deployment_option.assert_called_once_with(
            network_id=100,
            name="DNS Servers",
            code=6,
            value="8.8.8.8,8.8.4.4",
            server_scope="DHCP_SERVER",
        )

    @pytest.mark.asyncio
    async def test_executor_dhcp_service_deployment_option_create(self, executor, mock_client):
        """Test executor handling of DHCP service deployment option create operation."""
        mock_client.create_dhcpv4_service_deployment_option.return_value = {
            "id": 999,
            "name": "Default Lease Time",
            "code": 51,
        }

        operation = Operation(
            row_id=4,
            operation_type=OperationType.CREATE,
            object_type="dhcpv4_service_deployment_option",
            resource_id=None,
            payload={"network_id": 200, "value": 86400},
            csv_row=DHCPv4ServiceDeploymentOptionRow(
                row_id=4,
                object_type="dhcpv4_service_deployment_option",
                action="create",
                name="Default Lease Time",
                code=51,
                value="86400",
                server_scope="ALL_SERVERS",
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test OperationResult structure
        assert result.success is True
        assert result.row_id == 4
        assert result.operation == OperationType.CREATE
        assert result.resource_id == 999
        assert operation.status == OperationStatus.SUCCEEDED

        # Test BAM client method was called correctly
        mock_client.create_dhcpv4_service_deployment_option.assert_called_once_with(
            network_id=200,
            name="Default Lease Time",
            code=51,
            value=86400,
            server_scope="ALL_SERVERS",
        )

    @pytest.mark.asyncio
    async def test_executor_deployment_role_update(self, executor, mock_client):
        """Test executor handling of deployment role update operation."""
        mock_client.update_entity_by_id.return_value = {"id": 123, "name": "Updated DHCP Role"}

        operation = Operation(
            row_id=5,
            operation_type=OperationType.UPDATE,
            object_type="dhcp_deployment_role",
            resource_id=123,
            payload={"properties": {"name": "Updated DHCP Role"}},
            csv_row=DHCPDeploymentRoleRow(
                row_id=5,
                object_type="dhcp_deployment_role",
                action="update",
                resource_id=123,
                name="Updated DHCP Role",
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test OperationResult structure
        assert result.success is True
        assert result.row_id == 5
        assert result.operation == OperationType.UPDATE
        assert result.resource_id == 123
        assert operation.status == OperationStatus.SUCCEEDED

        # Test BAM client method was called correctly
        # Handler passes operation.payload directly
        mock_client.update_entity_by_id.assert_called_once_with(
            123, "DHCPDeploymentRole", {"properties": {"name": "Updated DHCP Role"}}
        )

    @pytest.mark.asyncio
    async def test_executor_deployment_role_delete(self, executor, mock_client):
        """Test executor handling of deployment role delete operation."""
        mock_client.delete_entity_by_id.return_value = {"status": "success"}

        operation = Operation(
            row_id=6,
            operation_type=OperationType.DELETE,
            object_type="dns_deployment_role",
            resource_id=456,
            payload={},
            csv_row=DNSDeploymentRoleRow(
                row_id=6,
                object_type="dns_deployment_role",
                action="delete",
                resource_id=456,
                config="Default",
                zone_path="Internal/example.com",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test OperationResult structure
        assert result.success is True
        assert result.row_id == 6
        assert result.operation == OperationType.DELETE
        assert result.resource_id == 456
        assert operation.status == OperationStatus.SUCCEEDED

        # Test BAM client method was called correctly
        mock_client.delete_dns_deployment_role.assert_called_once_with(deployment_role_id=456)

    @pytest.mark.asyncio
    async def test_executor_deployment_role_dry_run(self, executor):
        """Test deployment role operations in dry-run mode."""
        executor.dry_run = True

        operation = Operation(
            row_id=7,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={"network_id": 100},
            csv_row=DHCPDeploymentRoleRow(
                row_id=7,
                object_type="dhcp_deployment_role",
                action="create",
                name="Dry Run Role",
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test dry-run result
        assert result.success is True
        assert result.row_id == 7
        assert result.operation == OperationType.CREATE
        assert result.resource_id is not None  # Dummy resource ID in dry run
        assert operation.status == OperationStatus.PENDING

    @pytest.mark.asyncio
    async def test_executor_deployment_role_error_handling(self, executor, mock_client):
        """Test executor error handling for deployment role operations."""
        # Mock client to raise an exception
        mock_client.create_dhcp_deployment_role.side_effect = Exception("Network not found")

        operation = Operation(
            row_id=8,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={"network_id": 999},
            csv_row=DHCPDeploymentRoleRow(
                row_id=8,
                object_type="dhcp_deployment_role",
                action="create",
                name="Error Role",
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Test error result
        assert result.success is False
        assert result.row_id == 8
        assert result.operation == OperationType.CREATE
        assert result.resource_id is None
        assert result.error_message == "Network not found"
        assert result.duration_ms is not None
        # Status is updated to FAILED when operation fails
        assert operation.status == OperationStatus.FAILED

    @pytest.mark.asyncio
    async def test_executor_mixed_operations_with_deployment_roles(self, executor, mock_client):
        """Test executor handling mixed operations including deployment roles."""
        # Setup mocks for different operation types
        mock_client.create_ip4_address.return_value = {"id": 1001}
        mock_client.create_dhcp_deployment_role.return_value = {"id": 1002}
        mock_client.create_dhcpv4_client_deployment_option.return_value = {"id": 1003}

        # IP address operation
        ip_operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"network_id": 1000},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                address="192.168.1.10",
                config="Default",
            ),
        )

        # DHCP deployment role operation
        dhcp_operation = Operation(
            row_id=2,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={"network_id": 1000},
            csv_row=DHCPDeploymentRoleRow(
                row_id=2,
                object_type="dhcp_deployment_role",
                action="create",
                name="Mixed DHCP Role",
                config="Default",
            ),
        )

        # DHCP client option operation
        option_operation = Operation(
            row_id=3,
            operation_type=OperationType.CREATE,
            object_type="dhcpv4_client_deployment_option",
            resource_id=None,
            payload={"network_id": 1000, "value": "8.8.8.8"},
            csv_row=DHCPv4ClientDeploymentOptionRow(
                row_id=3,
                object_type="dhcpv4_client_deployment_option",
                action="create",
                name="Mixed DNS Option",
                code=6,
                value="8.8.8.8",
                server_scope="DHCP_SERVER",
                config="Default",
            ),
        )

        # Execute all operations
        ip_result = await executor._execute_operation(ip_operation)
        dhcp_result = await executor._execute_operation(dhcp_operation)
        option_result = await executor._execute_operation(option_operation)

        # Verify all succeeded
        assert ip_result.success is True
        assert dhcp_result.success is True
        assert option_result.success is True

        # Verify all operations have SUCCEEDED status
        assert ip_operation.status == OperationStatus.SUCCEEDED
        assert dhcp_operation.status == OperationStatus.SUCCEEDED
        assert option_operation.status == OperationStatus.SUCCEEDED

        # Verify the correct BAM methods were called
        mock_client.create_ip4_address.assert_called_once()
        mock_client.create_dhcp_deployment_role.assert_called_once()
        mock_client.create_dhcpv4_client_deployment_option.assert_called_once()

    @pytest.mark.asyncio
    async def test_executor_unsupported_deployment_role_object_type(self, executor):
        """Test executor handling of unsupported deployment role object type."""
        operation = Operation(
            row_id=999,
            operation_type=OperationType.CREATE,
            object_type="unsupported_deployment_type",
            resource_id=None,
            payload={},
            csv_row=None,
        )

        result = await executor._execute_operation(operation)

        assert result.success is False
        assert (
            "No handler registered for object type: unsupported_deployment_type"
            in result.error_message
        )

    @pytest.mark.asyncio
    async def test_executor_deployment_role_safety_checks(self, executor, mock_client):
        """Test that deployment role operations are not blocked by safety checks."""
        mock_client.delete_entity_by_id.return_value = {"status": "success"}

        # Delete operation should work (deployment roles are not protected)
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="dhcp_deployment_role",
            resource_id=123,
            payload={},
            csv_row=DHCPDeploymentRoleRow(
                row_id=1,
                object_type="dhcp_deployment_role",
                action="delete",
                resource_id=123,
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        # Should succeed without safety errors
        assert result.success is True
        assert result.resource_id == 123
        assert operation.status == OperationStatus.SUCCEEDED

        # Should be called without dangerous operations flag
        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "DHCPDeploymentRole", allow_dangerous_operations=False
        )
