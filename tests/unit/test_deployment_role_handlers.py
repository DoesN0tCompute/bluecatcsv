"""Tests for DHCP and DNS deployment role operation handlers."""

from unittest.mock import AsyncMock

import pytest

from src.importer.execution.handlers import (
    DHCPDeploymentRoleHandler,
    DHCPv4ClientDeploymentOptionHandler,
    DHCPv4ServiceDeploymentOptionHandler,
    DNSDeploymentRoleHandler,
)
from src.importer.models.csv_row import (
    DHCPDeploymentRoleRow,
    DHCPv4ClientDeploymentOptionRow,
    DHCPv4ServiceDeploymentOptionRow,
    DNSDeploymentRoleRow,
)
from src.importer.models.operations import Operation, OperationType


class TestDHCPDeploymentRoleHandler:
    """Test DHCP deployment role handler."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        return AsyncMock()

    @pytest.fixture
    def handler(self):
        """Create DHCP deployment role handler."""
        return DHCPDeploymentRoleHandler()

    @pytest.mark.asyncio
    async def test_create_dhcp_deployment_role_success(self, handler, mock_client):
        """Test successful DHCP deployment role creation."""
        mock_client.create_dhcp_deployment_role.return_value = {
            "id": 123,
            "name": "Primary DHCP Role",
        }

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
                name="Primary DHCP Role",
                role_type="PRIMARY",
                server_group="DHCP-Servers",
            ),
        )

        result = await handler.create(mock_client, operation)

        assert result["id"] == 123
        assert result["name"] == "Primary DHCP Role"
        mock_client.create_dhcp_deployment_role.assert_called_once_with(
            parent_id=456,
            parent_type="networks",
            name="Primary DHCP Role",
            role_type="PRIMARY",
            server_group="DHCP-Servers",
        )

    @pytest.mark.asyncio
    async def test_create_dhcp_deployment_role_with_optional_fields(self, handler, mock_client):
        """Test DHCP deployment role creation with optional fields."""
        mock_client.create_dhcp_deployment_role.return_value = {"id": 456}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={"network_id": 789},
            csv_row=DHCPDeploymentRoleRow(
                row_id=1,
                object_type="dhcp_deployment_role",
                action="create",
                name="Secondary DHCP Role",
                role_type="SECONDARY",
                server_group="Backup-Servers",
                server_group_id=999,
            ),
        )

        result = await handler.create(mock_client, operation)

        assert result["id"] == 456
        mock_client.create_dhcp_deployment_role.assert_called_once_with(
            parent_id=789,
            parent_type="networks",
            name="Secondary DHCP Role",
            role_type="SECONDARY",
            server_group="Backup-Servers",
            server_group_id=999,
        )

    @pytest.mark.asyncio
    async def test_create_dhcp_deployment_role_minimal_fields(self, handler, mock_client):
        """Test DHCP deployment role creation with minimal fields."""
        mock_client.create_dhcp_deployment_role.return_value = {"id": 789}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={"network_id": 100},
            csv_row=DHCPDeploymentRoleRow(
                row_id=1,
                object_type="dhcp_deployment_role",
                action="create",
                name="Minimal DHCP Role",
            ),
        )

        result = await handler.create(mock_client, operation)

        assert result["id"] == 789
        mock_client.create_dhcp_deployment_role.assert_called_once_with(
            parent_id=100, parent_type="networks", name="Minimal DHCP Role", role_type=None
        )

    @pytest.mark.asyncio
    async def test_update_dhcp_deployment_role(self, handler, mock_client):
        """Test DHCP deployment role update."""
        mock_client.update_entity_by_id.return_value = {"id": 123, "name": "Updated DHCP Role"}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="dhcp_deployment_role",
            resource_id=123,
            payload={"properties": {"name": "Updated DHCP Role"}},
            csv_row=DHCPDeploymentRoleRow(
                row_id=1,
                object_type="dhcp_deployment_role",
                action="update",
                resource_id=123,
                name="Updated DHCP Role",
            ),
        )

        result = await handler.update(mock_client, operation)

        assert result["id"] == 123
        assert result["name"] == "Updated DHCP Role"
        mock_client.update_entity_by_id.assert_called_once_with(
            123, "DHCPDeploymentRole", {"properties": {"name": "Updated DHCP Role"}}
        )

    @pytest.mark.asyncio
    async def test_delete_dhcp_deployment_role(self, handler, mock_client):
        """Test DHCP deployment role deletion."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="dhcp_deployment_role",
            resource_id=123,
            payload={},
            csv_row=DHCPDeploymentRoleRow(
                row_id=1, object_type="dhcp_deployment_role", action="delete", resource_id=123
            ),
        )

        await handler.delete(mock_client, operation)

        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "DHCPDeploymentRole", allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_get_required_payload_id_missing(self, handler):
        """Test missing required payload ID raises error."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcp_deployment_role",
            resource_id=None,
            payload={},  # Missing network_id
            csv_row=DHCPDeploymentRoleRow(
                row_id=1, object_type="dhcp_deployment_role", action="create", name="Test Role"
            ),
        )

        with pytest.raises(ValueError) as exc_info:
            await handler.create(AsyncMock(), operation)
        assert (
            "Missing parent ID (network_id or block_id) in payload for DHCP deployment role in row 1"
            in str(exc_info.value)
        )


class TestDNSDeploymentRoleHandler:
    """Test DNS deployment role handler."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        return AsyncMock()

    @pytest.fixture
    def handler(self):
        """Create DNS deployment role handler."""
        return DNSDeploymentRoleHandler()

    @pytest.mark.asyncio
    async def test_create_zone_level_dns_deployment_role(self, handler, mock_client):
        """Test zone-level DNS deployment role creation."""
        mock_client.create_dns_deployment_role.return_value = {"id": 123, "name": "Zone DNS Role"}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dns_deployment_role",
            resource_id=None,
            payload={"zone_id": 456},
            csv_row=DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="create",
                name="Zone DNS Role",
                zone_path="Internal/example.com",
                role_type="PRIMARY",
                interfaces="server1:interface1|server2:interface2",
                ns_record_ttl=3600,
            ),
        )

        # Mock the interface resolution
        mock_client.resolve_interface_string.side_effect = [101, 102]

        result = await handler.create(mock_client, operation)

        assert result["id"] == 123
        mock_client.create_dns_deployment_role.assert_called_once_with(
            parent_id=456,
            parent_type="zones",
            name="Zone DNS Role",
            role_type="PRIMARY",
            interfaces=[
                {"id": 101, "type": "NetworkInterface"},
                {"id": 102, "type": "NetworkInterface"},
            ],
            ns_record_ttl=3600,
        )

    @pytest.mark.asyncio
    async def test_create_network_level_dns_deployment_role(self, handler, mock_client):
        """Test network-level DNS deployment role creation."""
        mock_client.create_dns_deployment_role.return_value = {"id": 456}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dns_deployment_role",
            resource_id=None,
            payload={"network_id": 789},
            csv_row=DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="create",
                name="Network DNS Role",
                network_path="192.168.40.0/24",
                role_type="SECONDARY",
                interfaces="server3:interface5",
            ),
        )

        # Mock the interface resolution
        mock_client.resolve_interface_string.return_value = 201

        result = await handler.create(mock_client, operation)

        assert result["id"] == 456
        mock_client.create_dns_deployment_role.assert_called_once_with(
            parent_id=789,
            parent_type="networks",
            name="Network DNS Role",
            role_type="SECONDARY",
            interfaces=[{"id": 201, "type": "NetworkInterface"}],
        )

    @pytest.mark.asyncio
    async def test_create_block_level_dns_deployment_role(self, handler, mock_client):
        """Test block-level DNS deployment role creation."""
        mock_client.create_dns_deployment_role.return_value = {"id": 789}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dns_deployment_role",
            resource_id=None,
            payload={"block_id": 100},
            csv_row=DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="create",
                name="Block DNS Role",
                block_path="/IPv4/10.0.0.0/8",
                role_type="STUB",
                interfaces="4402278|4402274",
            ),
        )

        # Mock the interface resolution
        mock_client.resolve_interface_string.side_effect = [401, 402]

        result = await handler.create(mock_client, operation)

        assert result["id"] == 789
        mock_client.create_dns_deployment_role.assert_called_once_with(
            parent_id=100,
            parent_type="blocks",
            name="Block DNS Role",
            role_type="STUB",
            interfaces=[
                {"id": 401, "type": "NetworkInterface"},
                {"id": 402, "type": "NetworkInterface"},
            ],
        )

    @pytest.mark.asyncio
    async def test_create_dns_deployment_role_missing_parent_id(self, handler):
        """Test DNS deployment role creation fails without parent ID."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dns_deployment_role",
            resource_id=None,
            payload={},  # Missing zone_id, network_id, and block_id
            csv_row=DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="create",
                name="Orphan DNS Role",
                zone_path="Internal/example.com",  # Required by Pydantic
            ),
        )

        with pytest.raises(ValueError) as exc_info:
            await handler.create(AsyncMock(), operation)
        assert (
            "Missing parent ID (zone_id, network_id, or block_id) in payload for DNS deployment role in row 1"
            in str(exc_info.value)
        )

    @pytest.mark.asyncio
    async def test_update_dns_deployment_role(self, handler, mock_client):
        """Test DNS deployment role update."""
        mock_client.update_entity_by_id.return_value = {"id": 123, "name": "Updated DNS Role"}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="dns_deployment_role",
            resource_id=123,
            payload={"properties": {"name": "Updated DNS Role"}},
            csv_row=DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="update",
                resource_id=123,
                name="Updated DNS Role",
                zone_path="Internal/example.com",  # Required by Pydantic
            ),
        )

        result = await handler.update(mock_client, operation)

        assert result["id"] == 123
        mock_client.update_entity_by_id.assert_called_once_with(
            123,
            "DNSDeploymentRole",
            {"name": "Updated DNS Role", "properties": {"name": "Updated DNS Role"}},
        )

    @pytest.mark.asyncio
    async def test_delete_dns_deployment_role(self, handler, mock_client):
        """Test DNS deployment role deletion."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="dns_deployment_role",
            resource_id=123,
            payload={},
            csv_row=DNSDeploymentRoleRow(
                row_id=1,
                object_type="dns_deployment_role",
                action="delete",
                resource_id=123,
                zone_path="Internal/example.com",  # Required by Pydantic
            ),
        )

        await handler.delete(mock_client, operation)

        mock_client.delete_dns_deployment_role.assert_called_once_with(deployment_role_id=123)


class TestDHCPv4ClientDeploymentOptionHandler:
    """Test DHCPv4 client deployment option handler."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        return AsyncMock()

    @pytest.fixture
    def handler(self):
        """Create DHCPv4 client deployment option handler."""
        return DHCPv4ClientDeploymentOptionHandler()

    @pytest.mark.asyncio
    async def test_create_dhcp_client_deployment_option(self, handler, mock_client):
        """Test DHCP client deployment option creation."""
        mock_client.create_dhcpv4_client_deployment_option.return_value = {
            "id": 123,
            "name": "DNS Servers",
            "code": 6,
            "value": "8.8.8.8,8.8.4.4",
        }

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcpv4_client_deployment_option",
            resource_id=None,
            payload={"network_id": 456, "value": "8.8.8.8,8.8.4.4"},
            csv_row=DHCPv4ClientDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_client_deployment_option",
                action="create",
                name="DNS Servers",
                code=6,
                value="8.8.8.8,8.8.4.4",
                server_scope="DHCP_SERVER",
            ),
        )

        result = await handler.create(mock_client, operation)

        assert result["id"] == 123
        assert result["name"] == "DNS Servers"
        assert result["code"] == 6
        assert result["value"] == "8.8.8.8,8.8.4.4"
        mock_client.create_dhcpv4_client_deployment_option.assert_called_once_with(
            network_id=456,
            name="DNS Servers",
            code=6,
            value="8.8.8.8,8.8.4.4",
            server_scope="DHCP_SERVER",
        )

    @pytest.mark.asyncio
    async def test_create_dhcp_client_deployment_option_minimal(self, handler, mock_client):
        """Test DHCP client deployment option creation with minimal fields."""
        mock_client.create_dhcpv4_client_deployment_option.return_value = {"id": 456}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcpv4_client_deployment_option",
            resource_id=None,
            payload={"network_id": 789, "value": "example.com"},
            csv_row=DHCPv4ClientDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_client_deployment_option",
                action="create",
                name="Domain Name",
                code=15,
                value="example.com",
            ),
        )

        result = await handler.create(mock_client, operation)

        assert result["id"] == 456
        # server_scope is not passed when None (uses default)
        mock_client.create_dhcpv4_client_deployment_option.assert_called_once_with(
            network_id=789, name="Domain Name", code=15, value="example.com"
        )

    @pytest.mark.asyncio
    async def test_update_dhcp_client_deployment_option(self, handler, mock_client):
        """Test DHCP client deployment option update."""
        mock_client.update_dhcp_deployment_option.return_value = {
            "id": 123,
            "name": "Updated DNS Servers",
        }

        operation = Operation(
            row_id=1,
            operation_type=OperationType.UPDATE,
            object_type="dhcpv4_client_deployment_option",
            resource_id=123,
            payload={"value": "1.1.1.1,1.0.0.1"},
            csv_row=DHCPv4ClientDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_client_deployment_option",
                action="update",
                resource_id=123,
                name="Updated DNS Servers",
                value="1.1.1.1,1.0.0.1",
            ),
        )

        result = await handler.update(mock_client, operation)

        assert result["id"] == 123
        assert result["name"] == "Updated DNS Servers"
        # server_scope is not passed when None (uses default)
        mock_client.update_dhcp_deployment_option.assert_called_once_with(
            option_id=123, name="Updated DNS Servers", value="1.1.1.1,1.0.0.1"
        )

    @pytest.mark.asyncio
    async def test_delete_dhcp_client_deployment_option(self, handler, mock_client):
        """Test DHCP client deployment option deletion."""
        operation = Operation(
            row_id=1,
            operation_type=OperationType.DELETE,
            object_type="dhcpv4_client_deployment_option",
            resource_id=123,
            payload={},
            csv_row=DHCPv4ClientDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_client_deployment_option",
                action="delete",
                resource_id=123,
            ),
        )

        await handler.delete(mock_client, operation)

        mock_client.delete_dhcp_deployment_option.assert_called_once_with(option_id=123)


class TestDHCPv4ServiceDeploymentOptionHandler:
    """Test DHCPv4 service deployment option handler."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        return AsyncMock()

    @pytest.fixture
    def handler(self):
        """Create DHCPv4 service deployment option handler."""
        return DHCPv4ServiceDeploymentOptionHandler()

    @pytest.mark.asyncio
    async def test_create_dhcp_service_deployment_option(self, handler, mock_client):
        """Test DHCP service deployment option creation."""
        mock_client.create_dhcpv4_service_deployment_option.return_value = {
            "id": 123,
            "name": "Default Lease Time",
            "code": 51,
            "value": "86400",
        }

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcpv4_service_deployment_option",
            resource_id=None,
            payload={"network_id": 456, "value": 86400},
            csv_row=DHCPv4ServiceDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_service_deployment_option",
                action="create",
                name="Default Lease Time",
                code=51,
                value="86400",
                server_scope="DHCP_SERVER",
            ),
        )

        result = await handler.create(mock_client, operation)

        assert result["id"] == 123
        assert result["name"] == "Default Lease Time"
        assert result["code"] == 51
        assert result["value"] == "86400"
        mock_client.create_dhcpv4_service_deployment_option.assert_called_once_with(
            network_id=456,
            name="Default Lease Time",
            code=51,
            value=86400,
            server_scope="DHCP_SERVER",
        )

    @pytest.mark.asyncio
    async def test_create_dhcp_service_deployment_option_all_servers_scope(
        self, handler, mock_client
    ):
        """Test DHCP service deployment option with ALL_SERVERS scope."""
        mock_client.create_dhcpv4_service_deployment_option.return_value = {"id": 456}

        operation = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="dhcpv4_service_deployment_option",
            resource_id=None,
            payload={"network_id": 789, "value": 43200},
            csv_row=DHCPv4ServiceDeploymentOptionRow(
                row_id=1,
                object_type="dhcpv4_service_deployment_option",
                action="create",
                name="Maximum Lease Time",
                code=52,
                value="43200",
                server_scope="ALL_SERVERS",
            ),
        )

        result = await handler.create(mock_client, operation)

        assert result["id"] == 456
        mock_client.create_dhcpv4_service_deployment_option.assert_called_once_with(
            network_id=789,
            name="Maximum Lease Time",
            code=52,
            value=43200,
            server_scope="ALL_SERVERS",
        )

    @pytest.mark.asyncio
    async def test_handler_inheritance_from_base(self):
        """Test that deployment option handlers inherit from BaseHandler."""
        from src.importer.execution.handlers import BaseHandler

        client_handler = DHCPv4ClientDeploymentOptionHandler()
        service_handler = DHCPv4ServiceDeploymentOptionHandler()

        assert isinstance(client_handler, BaseHandler)
        assert isinstance(service_handler, BaseHandler)

        # Both should have the required methods
        assert hasattr(client_handler, "create")
        assert hasattr(client_handler, "update")
        assert hasattr(client_handler, "delete")
        assert hasattr(service_handler, "create")
        assert hasattr(service_handler, "update")
        assert hasattr(service_handler, "delete")
