"""Tests for executor DHCP operations."""

from unittest.mock import AsyncMock

import pytest

from src.importer.execution.executor import OperationExecutor
from src.importer.models.csv_row import (
    DHCPDeploymentRoleRow,
    IP4AddressRow,
    IPv4DHCPRangeRow,
)
from src.importer.models.operations import Operation, OperationStatus, OperationType


class TestOperationExecutorDHCPOperations:
    """Test executor handling of DHCP operations."""

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
        """Create an executor with DHCP support."""
        return OperationExecutor(
            bam_client=mock_client, policy=mock_policy, allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_executor_dhcp_range_create_operation(self, executor, mock_client):
        """Test executor handling of DHCP range create operation."""
        mock_client.create_ipv4_dhcp_range.return_value = {"id": 123, "name": "Test Range"}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ipv4_dhcp_range",
            resource_id=None,
            payload={
                "config_id": 1,
                "network_id": 456,
                "name": "Test Range",
                "range": "10.1.1.100-10.1.1.200",
            },
            csv_row=IPv4DHCPRangeRow(
                row_id=1,
                object_type="ipv4_dhcp_range",
                action="create",
                name="Test Range",
                config="Default",
                range="10.1.1.100-10.1.1.200",
            ),
        )

        result = await executor._execute_operation(operation)

        assert result.success is True
        assert operation.status == OperationStatus.SUCCEEDED

        # Verify the BAM client method was called correctly
        mock_client.create_ipv4_dhcp_range.assert_called_once_with(
            config_id=1,
            network_id=456,
            name="Test Range",
            dhcp_range="10.1.1.100-10.1.1.200",
            split_around_static_addresses=None,
            low_water_mark=None,
            high_water_mark=None,
        )

    @pytest.mark.asyncio
    async def test_executor_dhcp_deployment_role_create_operation(self, executor, mock_client):
        """Test executor handling of DHCP deployment role create operation."""
        mock_client.create_dhcp_deployment_role.return_value = {"id": 654, "name": "Test Role"}

        operation = Operation(
            row_id=5,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={
                "network_id": 100,
                "name": "Test Role",
                "role_type": "PRIMARY",
                "server_group": "DHCP-Servers",
            },
            csv_row=DHCPDeploymentRoleRow(
                row_id=5,
                object_type="dhcp_deployment_role",
                action="create",
                name="Test Role",
                role_type="PRIMARY",
                server_group="DHCP-Servers",
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        assert result.success is True
        assert operation.status == OperationStatus.SUCCEEDED

        # Verify the dedicated method was called with correct parameters
        mock_client.create_dhcp_deployment_role.assert_called_once_with(
            parent_id=100,
            parent_type="networks",
            name="Test Role",
            role_type="PRIMARY",
            server_group="DHCP-Servers",
        )

    @pytest.mark.asyncio
    async def test_executor_dhcp_range_update_operation(self, executor, mock_client):
        """Test executor handling of DHCP range update operation."""
        mock_client.update_entity_by_id.return_value = {"id": 123, "name": "Updated Range"}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="ipv4_dhcp_range",
            resource_id=123,
            payload={"name": "Updated Range"},
            csv_row=IPv4DHCPRangeRow(
                row_id=1,
                object_type="ipv4_dhcp_range",
                action="update",
                resource_id=123,
                name="Updated Range",
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 123
        assert operation.status == OperationStatus.SUCCEEDED

        mock_client.update_entity_by_id.assert_called_once_with(
            123, "IPv4DHCPRange", {"name": "Updated Range"}
        )

    @pytest.mark.asyncio
    async def test_executor_dhcp_range_delete_operation(self, executor, mock_client):
        """Test executor handling of DHCP range delete operation."""
        mock_client.delete_entity_by_id.return_value = {"status": "success"}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="ipv4_dhcp_range",
            resource_id=123,
            payload={},
            csv_row=IPv4DHCPRangeRow(
                row_id=1,
                object_type="ipv4_dhcp_range",
                action="delete",
                resource_id=123,
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        assert result.success is True
        assert result.resource_id == 123
        assert operation.status == OperationStatus.SUCCEEDED

        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "IPv4DHCPRange", allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_executor_unsupported_dhcp_object_type(self, executor):
        """Test executor handling of unsupported DHCP object type."""
        operation = Operation(
            row_id=999,
            operation_type=OperationType.CREATE,
            object_type="unsupported_dhcp_type",
            resource_id=None,
            payload={},
            csv_row=None,
        )

        result = await executor._execute_operation(operation)

        assert result.success is False
        assert (
            "No handler registered for object type: unsupported_dhcp_type" in result.error_message
        )

    @pytest.mark.asyncio
    async def test_executor_dhcp_operation_in_dry_run(self, executor):
        """Test DHCP operations in dry-run mode."""
        executor.dry_run = True

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ipv4_dhcp_range",
            resource_id=None,
            payload={
                "config_id": 1,
                "network_id": 456,
                "name": "Test Range",
                "range": "10.1.1.100-10.1.1.200",
            },
            csv_row=IPv4DHCPRangeRow(
                row_id=1,
                object_type="ipv4_dhcp_range",
                action="create",
                name="Test Range",
                range="10.1.1.100-10.1.1.200",
                config="Default",
            ),
        )

        result = await executor._execute_operation(operation)

        assert result.success is True
        assert result.metadata["dry_run"] is True
        # Operation status is not updated in dry run
        assert operation.status == OperationStatus.PENDING

    @pytest.mark.asyncio
    async def test_executor_mixed_operations(self, executor, mock_client):
        """Test executor handling of mixed IP and DHCP operations."""
        mock_client.create_ip4_address.return_value = {"id": 999}
        mock_client.create_ipv4_dhcp_range.return_value = {"id": 123}

        # First create an IP address
        ip_operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_address",
            resource_id=None,
            payload={"address": "10.1.1.50", "network_id": 999},
            csv_row=IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                address="10.1.1.50",
                config="Default",
            ),
        )

        # Then create a DHCP range
        dhcp_operation = Operation(
            row_id=2,
            operation_type=OperationType.CREATE,
            object_type="ipv4_dhcp_range",
            resource_id=None,
            payload={
                "config_id": 1,
                "network_id": 999,
                "name": "Mixed Range",
                "range": "10.1.1.100-10.1.1.200",
            },
            csv_row=IPv4DHCPRangeRow(
                row_id=2,
                object_type="ipv4_dhcp_range",
                action="create",
                name="Mixed Range",
                range="10.1.1.100-10.1.1.200",
                config="Default",
            ),
        )

        # Execute both operations
        ip_result = await executor._execute_operation(ip_operation)
        dhcp_result = await executor._execute_operation(dhcp_operation)

        # Verify both succeeded
        assert ip_result.success is True
        assert dhcp_result.success is True

        # Verify both operations have SUCCEEDED status
        assert ip_operation.status == OperationStatus.SUCCEEDED
        assert dhcp_operation.status == OperationStatus.SUCCEEDED

        # Verify the correct BAM methods were called
        mock_client.create_ip4_address.assert_called_once_with(
            network_id=999, address="10.1.1.50", name=None, mac=None, state="STATIC", properties={}
        )
        mock_client.create_ipv4_dhcp_range.assert_called_once_with(
            config_id=1,
            network_id=999,
            name="Mixed Range",
            dhcp_range="10.1.1.100-10.1.1.200",
            split_around_static_addresses=None,
            low_water_mark=None,
            high_water_mark=None,
        )
