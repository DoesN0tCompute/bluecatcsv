"""Unit tests for device-related operation handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.importer.execution.handlers import (
    DeviceAddressHandler,
    DeviceHandler,
    DeviceSubtypeHandler,
    DeviceTypeHandler,
    get_handler,
)


class TestDeviceHandlerRegistry:
    """Test device handlers are registered correctly."""

    def test_device_type_handler_registered(self):
        """Test device_type handler is registered."""
        handler = get_handler("device_type")
        assert isinstance(handler, DeviceTypeHandler)

    def test_device_subtype_handler_registered(self):
        """Test device_subtype handler is registered."""
        handler = get_handler("device_subtype")
        assert isinstance(handler, DeviceSubtypeHandler)

    def test_device_handler_registered(self):
        """Test device handler is registered."""
        handler = get_handler("device")
        assert isinstance(handler, DeviceHandler)

    def test_device_address_handler_registered(self):
        """Test device_address handler is registered."""
        handler = get_handler("device_address")
        assert isinstance(handler, DeviceAddressHandler)


class TestDeviceTypeHandler:
    """Test DeviceTypeHandler functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.create_device_type = AsyncMock(
            return_value={"id": 100, "type": "DeviceType", "name": "Cisco"}
        )
        client.delete_device_type = AsyncMock()
        return client

    @pytest.fixture
    def mock_operation(self):
        """Create a mock operation for device type."""
        operation = MagicMock()
        operation.row_id = 1
        operation.object_type = "device_type"
        operation.payload = {"name": "Cisco"}
        operation.csv_row = MagicMock()
        operation.csv_row.name = "Cisco"
        return operation

    @pytest.mark.asyncio
    async def test_create_device_type(self, mock_client, mock_operation):
        """Test creating a device type."""
        handler = DeviceTypeHandler()
        result = await handler.create(mock_client, mock_operation)

        assert result["id"] == 100
        assert result["name"] == "Cisco"
        mock_client.create_device_type.assert_called_once_with(
            name="Cisco",
            user_defined_fields=None,
        )

    @pytest.mark.asyncio
    async def test_create_device_type_with_udfs(self, mock_client, mock_operation):
        """Test creating a device type with UDFs."""
        mock_operation.payload["user_defined_fields"] = {"Category": "Network"}
        handler = DeviceTypeHandler()
        await handler.create(mock_client, mock_operation)

        mock_client.create_device_type.assert_called_once_with(
            name="Cisco",
            user_defined_fields={"Category": "Network"},
        )

    @pytest.mark.asyncio
    async def test_delete_device_type(self, mock_client, mock_operation):
        """Test deleting a device type."""
        mock_operation.payload["device_type_id"] = 100
        handler = DeviceTypeHandler()

        await handler.delete(mock_client, mock_operation)

        mock_client.delete_device_type.assert_called_once_with(100)


class TestDeviceSubtypeHandler:
    """Test DeviceSubtypeHandler functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.create_device_subtype = AsyncMock(
            return_value={"id": 200, "type": "DeviceSubtype", "name": "Catalyst-3750"}
        )
        client.delete_device_subtype = AsyncMock()
        return client

    @pytest.fixture
    def mock_operation(self):
        """Create a mock operation for device subtype."""
        operation = MagicMock()
        operation.row_id = 1
        operation.object_type = "device_subtype"
        operation.payload = {"device_type_id": 100, "name": "Catalyst-3750"}
        operation.csv_row = MagicMock()
        operation.csv_row.name = "Catalyst-3750"
        return operation

    @pytest.mark.asyncio
    async def test_create_device_subtype(self, mock_client, mock_operation):
        """Test creating a device subtype."""
        handler = DeviceSubtypeHandler()
        result = await handler.create(mock_client, mock_operation)

        assert result["id"] == 200
        assert result["name"] == "Catalyst-3750"
        mock_client.create_device_subtype.assert_called_once_with(
            type_id=100,
            name="Catalyst-3750",
            user_defined_fields=None,
        )

    @pytest.mark.asyncio
    async def test_create_device_subtype_missing_type_id(self, mock_client, mock_operation):
        """Test creating device subtype without device_type_id raises error."""
        mock_operation.payload = {"name": "Catalyst-3750"}  # Missing device_type_id
        handler = DeviceSubtypeHandler()

        with pytest.raises(ValueError, match="Missing required device_type_id"):
            await handler.create(mock_client, mock_operation)

    @pytest.mark.asyncio
    async def test_delete_device_subtype(self, mock_client, mock_operation):
        """Test deleting a device subtype."""
        mock_operation.payload["device_subtype_id"] = 200
        handler = DeviceSubtypeHandler()

        await handler.delete(mock_client, mock_operation)

        mock_client.delete_device_subtype.assert_called_once_with(200)


class TestDeviceHandler:
    """Test DeviceHandler functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.create_device = AsyncMock(
            return_value={"id": 300, "type": "Device", "name": "firewall-01"}
        )
        client.delete_device = AsyncMock()
        return client

    @pytest.fixture
    def mock_operation(self):
        """Create a mock operation for device."""
        operation = MagicMock()
        operation.row_id = 1
        operation.object_type = "device"
        operation.payload = {
            "config_id": 1,
            "name": "firewall-01",
        }
        operation.csv_row = MagicMock()
        operation.csv_row.name = "firewall-01"
        return operation

    @pytest.mark.asyncio
    async def test_create_device_minimal(self, mock_client, mock_operation):
        """Test creating a device with minimal fields."""
        handler = DeviceHandler()
        result = await handler.create(mock_client, mock_operation)

        assert result["id"] == 300
        assert result["name"] == "firewall-01"
        mock_client.create_device.assert_called_once_with(
            config_id=1,
            name="firewall-01",
            device_type_id=None,
            device_subtype_id=None,
            addresses=None,
            user_defined_fields=None,
        )

    @pytest.mark.asyncio
    async def test_create_device_with_type_and_subtype(self, mock_client, mock_operation):
        """Test creating a device with type and subtype."""
        mock_operation.payload["device_type_id"] = 100
        mock_operation.payload["device_subtype_id"] = 200
        handler = DeviceHandler()

        await handler.create(mock_client, mock_operation)

        mock_client.create_device.assert_called_once_with(
            config_id=1,
            name="firewall-01",
            device_type_id=100,
            device_subtype_id=200,
            addresses=None,
            user_defined_fields=None,
        )

    @pytest.mark.asyncio
    async def test_create_device_missing_config_id(self, mock_client, mock_operation):
        """Test creating device without config_id raises error."""
        mock_operation.payload = {"name": "firewall-01"}  # Missing config_id
        handler = DeviceHandler()

        with pytest.raises(ValueError, match="Missing required config_id"):
            await handler.create(mock_client, mock_operation)

    @pytest.mark.asyncio
    async def test_delete_device(self, mock_client, mock_operation):
        """Test deleting a device."""
        mock_operation.payload["device_id"] = 300
        handler = DeviceHandler()

        await handler.delete(mock_client, mock_operation)

        mock_client.delete_device.assert_called_once_with(300)


class TestDeviceAddressHandler:
    """Test DeviceAddressHandler functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.link_address_to_device = AsyncMock(
            return_value={"id": 400, "type": "IPv4Address", "address": "10.0.1.1"}
        )
        client.unlink_address_from_device = AsyncMock()
        return client

    @pytest.fixture
    def mock_operation(self):
        """Create a mock operation for device address."""
        operation = MagicMock()
        operation.row_id = 1
        operation.object_type = "device_address"
        operation.payload = {
            "device_id": 300,
            "address_id": 500,
            "address_type": "IPv4Address",
        }
        operation.csv_row = MagicMock()
        return operation

    @pytest.mark.asyncio
    async def test_create_device_address_link(self, mock_client, mock_operation):
        """Test linking an address to a device."""
        handler = DeviceAddressHandler()
        result = await handler.create(mock_client, mock_operation)

        assert result["id"] == 400
        mock_client.link_address_to_device.assert_called_once_with(
            device_id=300,
            address_id=500,
            address_type="IPv4Address",
        )

    @pytest.mark.asyncio
    async def test_create_device_address_ipv6(self, mock_client, mock_operation):
        """Test linking an IPv6 address to a device."""
        mock_operation.payload["address_type"] = "IPv6Address"
        mock_client.link_address_to_device = AsyncMock(
            return_value={"id": 401, "type": "IPv6Address", "address": "2001:db8::1"}
        )
        handler = DeviceAddressHandler()

        await handler.create(mock_client, mock_operation)

        mock_client.link_address_to_device.assert_called_once_with(
            device_id=300,
            address_id=500,
            address_type="IPv6Address",
        )

    @pytest.mark.asyncio
    async def test_create_device_address_missing_device_id(self, mock_client, mock_operation):
        """Test creating device address without device_id raises error."""
        mock_operation.payload = {"address_id": 500}  # Missing device_id
        handler = DeviceAddressHandler()

        with pytest.raises(ValueError, match="Missing required device_id"):
            await handler.create(mock_client, mock_operation)

    @pytest.mark.asyncio
    async def test_create_device_address_missing_address_id(self, mock_client, mock_operation):
        """Test creating device address without address_id raises error."""
        mock_operation.payload = {"device_id": 300}  # Missing address_id
        handler = DeviceAddressHandler()

        with pytest.raises(ValueError, match="Missing required address_id"):
            await handler.create(mock_client, mock_operation)

    @pytest.mark.asyncio
    async def test_update_device_address_not_supported(self, mock_client, mock_operation):
        """Test that update raises NotImplementedError."""
        handler = DeviceAddressHandler()

        with pytest.raises(NotImplementedError):
            await handler.update(mock_client, mock_operation)

    @pytest.mark.asyncio
    async def test_delete_device_address(self, mock_client, mock_operation):
        """Test unlinking an address from a device."""
        handler = DeviceAddressHandler()

        await handler.delete(mock_client, mock_operation)

        mock_client.unlink_address_from_device.assert_called_once_with(300, 500)
