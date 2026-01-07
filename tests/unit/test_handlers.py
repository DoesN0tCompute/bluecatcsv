"""Unit tests for operation handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.importer.execution.handlers import (
    HANDLER_REGISTRY,
    IPv4AddressHandler,
    IPv4BlockHandler,
    IPv4NetworkHandler,
    get_handler,
    get_supported_object_types,
    register_handler,
)


class TestHandlerRegistry:
    """Test handler registry functionality."""

    def test_get_handler_ip4_block(self):
        """Test getting handler for ip4_block."""
        handler = get_handler("ip4_block")
        assert isinstance(handler, IPv4BlockHandler)

    def test_get_handler_block_alias(self):
        """Test getting handler for block alias."""
        handler = get_handler("block")
        assert isinstance(handler, IPv4BlockHandler)

    def test_get_handler_ip4_network(self):
        """Test getting handler for ip4_network."""
        handler = get_handler("ip4_network")
        assert isinstance(handler, IPv4NetworkHandler)

    def test_get_handler_network_alias(self):
        """Test getting handler for network alias."""
        handler = get_handler("network")
        assert isinstance(handler, IPv4NetworkHandler)

    def test_get_handler_ip4_address(self):
        """Test getting handler for ip4_address."""
        handler = get_handler("ip4_address")
        assert isinstance(handler, IPv4AddressHandler)

    def test_get_handler_address_alias(self):
        """Test getting handler for address alias."""
        handler = get_handler("address")
        assert isinstance(handler, IPv4AddressHandler)

    def test_get_handler_unsupported_type(self):
        """Test getting handler for unsupported object type."""
        with pytest.raises(
            ValueError, match="No handler registered for object type: unsupported_type"
        ):
            get_handler("unsupported_type")

    def test_get_supported_object_types(self):
        """Test getting list of supported object types."""
        supported_types = get_supported_object_types()

        # Should include major types
        assert "ip4_block" in supported_types
        assert "ip4_network" in supported_types
        assert "ip4_address" in supported_types
        assert "block" in supported_types  # alias
        assert "network" in supported_types  # alias
        assert "address" in supported_types  # alias

        # Should be a list (not a set)
        assert isinstance(supported_types, list)

    def test_register_new_handler(self):
        """Test registering a new handler."""
        # Create a mock handler
        mock_handler = MagicMock()

        # Register it for a new type
        register_handler("test_type", mock_handler)

        # Verify it was registered
        assert get_handler("test_type") is mock_handler

        # Clean up
        del HANDLER_REGISTRY["test_type"]


class TestIPv4BlockHandler:
    """Test IPv4BlockHandler functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.create_ip4_block = AsyncMock(return_value={"id": 123})
        return client

    @pytest.fixture
    def mock_operation(self):
        """Create a mock operation for IP4 block creation."""
        operation = MagicMock()
        operation.row_id = 1
        operation.object_type = "ip4_block"
        operation.payload = {"config_id": 456, "properties": {}}
        operation.csv_row = MagicMock()
        operation.csv_row.cidr = "10.0.0.0/8"
        operation.csv_row.name = "Test Block"
        return operation

    @pytest.mark.asyncio
    async def test_create_success(self, mock_client, mock_operation):
        """Test successful IP4 block creation."""
        handler = IPv4BlockHandler()

        result = await handler.create(mock_client, mock_operation)

        assert result["id"] == 123
        mock_client.create_ip4_block.assert_called_once_with(
            config_id=456,
            cidr="10.0.0.0/8",
            name="Test Block",
            properties={},
            location=None,
            parent_id=None,
        )

    @pytest.mark.asyncio
    async def test_create_missing_config_id(self, mock_client, mock_operation):
        """Test IP4 block creation with missing config_id."""
        mock_operation.payload = {}  # Remove config_id

        handler = IPv4BlockHandler()

        with pytest.raises(ValueError, match="Missing required config_id"):
            await handler.create(mock_client, mock_operation)

    @pytest.mark.asyncio
    async def test_update(self, mock_client, mock_operation):
        """Test IP4 block update."""
        mock_client.update_entity_by_id = AsyncMock(return_value={"id": 123})
        mock_operation.resource_id = 123

        handler = IPv4BlockHandler()

        result = await handler.update(mock_client, mock_operation)

        assert result["id"] == 123
        mock_client.update_entity_by_id.assert_called_once_with(
            123, "IPv4Block", mock_operation.payload
        )

    @pytest.mark.asyncio
    async def test_delete(self, mock_client, mock_operation):
        """Test IP4 block deletion."""
        mock_client.delete_entity_by_id = AsyncMock()
        mock_operation.resource_id = 123

        handler = IPv4BlockHandler()

        await handler.delete(mock_client, mock_operation)

        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "IPv4Block", allow_dangerous_operations=False
        )

    @pytest.mark.asyncio
    async def test_delete_dangerous(self, mock_client, mock_operation):
        """Test IP4 block deletion with dangerous flag."""
        mock_client.delete_entity_by_id = AsyncMock()
        mock_operation.resource_id = 123

        handler = IPv4BlockHandler()

        await handler.delete(mock_client, mock_operation, allow_dangerous_operations=True)

        mock_client.delete_entity_by_id.assert_called_once_with(
            123, "IPv4Block", allow_dangerous_operations=True
        )


class TestBaseHandlerMethods:
    """Test BaseHandler utility methods."""

    @pytest.fixture
    def mock_operation(self):
        """Create a mock operation."""
        operation = MagicMock()
        operation.payload = {"config_id": 123, "test_value": "test"}
        operation.row_id = 1
        # Set spec for csv_row so it behaves like an object with attributes, not MagicMock
        from types import SimpleNamespace

        operation.csv_row = SimpleNamespace()
        return operation

    def test_get_required_payload_id_success(self, mock_operation):
        """Test successful required payload ID extraction."""
        from src.importer.execution.handlers import BaseHandler

        handler = BaseHandler()
        result = handler._get_required_payload_id(mock_operation, "config_id")
        assert result == 123

    def test_get_required_payload_id_missing(self, mock_operation):
        """Test required payload ID extraction when missing."""
        from src.importer.execution.handlers import BaseHandler

        handler = BaseHandler()

        with pytest.raises(ValueError, match="Missing required missing_key"):
            handler._get_required_payload_id(mock_operation, "missing_key")

    def test_get_required_payload_id_invalid_string(self, mock_operation):
        """Test required payload ID extraction with invalid string."""
        from src.importer.execution.handlers import BaseHandler

        handler = BaseHandler()
        mock_operation.payload["config_id"] = "invalid"

        with pytest.raises(ValueError, match="Invalid config_id"):
            handler._get_required_payload_id(mock_operation, "config_id")

    def test_get_optional_attr_present(self, mock_operation):
        """Test getting optional attribute when present."""
        from src.importer.execution.handlers import BaseHandler

        handler = BaseHandler()
        mock_operation.csv_row.test_attr = "test_value"

        result = handler._get_optional_attr(mock_operation, "test_attr")
        assert result == "test_value"

    def test_get_optional_attr_missing(self, mock_operation):
        """Test getting optional attribute when missing."""
        from src.importer.execution.handlers import BaseHandler

        handler = BaseHandler()

        result = handler._get_optional_attr(mock_operation, "missing_attr")
        assert result is None

    def test_get_optional_attr_with_default(self, mock_operation):
        """Test getting optional attribute with default value."""
        from src.importer.execution.handlers import BaseHandler

        handler = BaseHandler()

        result = handler._get_optional_attr(mock_operation, "missing_attr", "default")
        assert result == "default"


class TestIntegration:
    """Integration tests for handler system."""

    def test_all_handlers_in_registry(self):
        """Test that all handlers are properly registered."""
        from src.importer.execution.handlers import (
            DHCPDeploymentRoleHandler,
            DHCPv4ClientDeploymentOptionHandler,
            DHCPv4ServiceDeploymentOptionHandler,
            DNSDeploymentRoleHandler,
            IPv4AddressHandler,
            IPv4BlockHandler,
            IPv4DHCPRangeHandler,
            IPv4NetworkHandler,
        )

        expected_handlers = {
            "ip4_block": IPv4BlockHandler,
            "block": IPv4BlockHandler,
            "ip4_network": IPv4NetworkHandler,
            "network": IPv4NetworkHandler,
            "ip4_address": IPv4AddressHandler,
            "address": IPv4AddressHandler,
            "ipv4_dhcp_range": IPv4DHCPRangeHandler,
            "dhcp_deployment_role": DHCPDeploymentRoleHandler,
            "dns_deployment_role": DNSDeploymentRoleHandler,
            "dhcpv4_client_deployment_option": DHCPv4ClientDeploymentOptionHandler,
            "dhcpv4_service_deployment_option": DHCPv4ServiceDeploymentOptionHandler,
        }

        for object_type, expected_handler_class in expected_handlers.items():
            handler = get_handler(object_type)
            assert isinstance(
                handler, expected_handler_class
            ), f"Handler for {object_type} is not instance of {expected_handler_class.__name__}"

    def test_handler_registry_completeness(self):
        """Test that handler registry contains all expected object types."""
        supported_types = get_supported_object_types()

        # Should have at least these core types
        required_types = [
            "ip4_block",
            "block",
            "ip4_network",
            "network",
            "ip4_address",
            "address",
            "ipv4_dhcp_range",
            "dns_deployment_role",
            "dhcpv4_client_deployment_option",
            "dhcpv4_service_deployment_option",
        ]

        for required_type in required_types:
            assert (
                required_type in supported_types
            ), f"Required object type '{required_type}' not in supported types"


class TestDHCPDeploymentRoleHandler:
    """Test DHCPDeploymentRoleHandler functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.create_dhcp_deployment_role = AsyncMock(return_value={"id": 789})
        # Mock resolve_interface_string to return ID based on string hash or simple mapping
        client.resolve_interface_string = AsyncMock(side_effect=lambda x: abs(hash(x)) % 10000)
        return client

    @pytest.fixture
    def mock_operation(self):
        """Create a mock operation."""
        operation = MagicMock()
        operation.row_id = 1
        operation.object_type = "dhcp_deployment_role"
        operation.payload = {
            "network_id": 456,
            "interfaces": "server1:eth0|server2:eth0",
            "properties": {},
        }
        operation.csv_row = MagicMock()
        operation.csv_row.get_interface_list = MagicMock(
            return_value=["server1:eth0", "server2:eth0"]
        )
        return operation

    @pytest.mark.asyncio
    async def test_create_with_secondary(self, mock_client, mock_operation):
        """Test creating DHCP deployment role with primary and secondary interfaces."""
        from src.importer.execution.handlers import DHCPDeploymentRoleHandler

        handler = DHCPDeploymentRoleHandler()
        await handler.create(mock_client, mock_operation)

        # Verify client was called with correct interfaces structure
        mock_client.create_dhcp_deployment_role.assert_called_once()
        call_kwargs = mock_client.create_dhcp_deployment_role.call_args[1]

        interfaces = call_kwargs["interfaces"]
        assert len(interfaces) == 2

        # First interface should be PRIMARY
        assert interfaces[0]["deploymentRoleInterfaceType"] == "PRIMARY"

        # Second interface should be SECONDARY
        assert interfaces[1]["deploymentRoleInterfaceType"] == "SECONDARY"
