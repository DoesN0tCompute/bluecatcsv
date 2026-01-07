"""Tests for OperationFactory and related classes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.importer.core.operation_factory import (
    DeferredResolver,
    OperationFactory,
    PendingResources,
)
from src.importer.models.operations import OperationType


class TestPendingResources:
    """Test PendingResources dataclass."""

    def test_from_rows_empty(self):
        """Test creating PendingResources from empty rows list."""
        pending = PendingResources.from_rows([])
        assert len(pending.blocks) == 0
        assert len(pending.networks) == 0
        assert len(pending.zones) == 0

    def test_from_rows_blocks(self):
        """Test that blocks are correctly identified from rows."""
        row1 = MagicMock()
        row1.action = "create"
        row1.object_type = "ip4_block"
        row1.cidr = "10.0.0.0/8"
        row1.row_id = 1

        row2 = MagicMock()
        row2.action = "update"  # Should be skipped
        row2.object_type = "ip4_block"
        row2.cidr = "192.168.0.0/16"
        row2.row_id = 2

        pending = PendingResources.from_rows([row1, row2])

        assert len(pending.blocks) == 1
        assert pending.blocks["10.0.0.0/8"] == 1

    def test_from_rows_networks(self):
        """Test that networks are correctly identified from rows."""
        row = MagicMock()
        row.action = "create"
        row.object_type = "ip4_network"
        row.cidr = "10.1.0.0/24"
        row.row_id = 10

        pending = PendingResources.from_rows([row])

        assert len(pending.networks) == 1
        assert pending.networks["10.1.0.0/24"] == 10

    def test_from_rows_zones(self):
        """Test that zones are correctly identified from rows."""
        row = MagicMock()
        row.action = "create"
        row.object_type = "dns_zone"
        row.zone_name = "example.com"
        row.row_id = 100

        pending = PendingResources.from_rows([row])

        assert len(pending.zones) == 1
        assert pending.zones["example.com"] == 100

    def test_from_rows_mixed(self):
        """Test with a mix of object types."""
        rows = []

        # Block
        row1 = MagicMock()
        row1.action = "create"
        row1.object_type = "ip4_block"
        row1.cidr = "10.0.0.0/8"
        row1.row_id = 1
        rows.append(row1)

        # Network
        row2 = MagicMock()
        row2.action = "create"
        row2.object_type = "ip4_network"
        row2.cidr = "10.1.0.0/24"
        row2.row_id = 2
        rows.append(row2)

        # Zone
        row3 = MagicMock()
        row3.action = "create"
        row3.object_type = "dns_zone"
        row3.zone_name = "example.com"
        row3.row_id = 3
        rows.append(row3)

        # Address (should be ignored)
        row4 = MagicMock()
        row4.action = "create"
        row4.object_type = "ip4_address"
        row4.row_id = 4
        rows.append(row4)

        pending = PendingResources.from_rows(rows)

        assert len(pending.blocks) == 1
        assert len(pending.networks) == 1
        assert len(pending.zones) == 1


class TestDeferredResolver:
    """Test DeferredResolver class."""

    def test_register_and_get_created_resource(self):
        """Test registering and retrieving created resources."""
        pending = PendingResources()
        resolver = DeferredResolver(pending)

        resolver.register_created_resource("block", "10.0.0.0/8", 123)

        assert resolver.get_created_id("block", "10.0.0.0/8") == 123
        assert resolver.get_created_id("block", "192.168.0.0/16") is None

    def test_check_pending_block(self):
        """Test checking for pending blocks."""
        pending = PendingResources(
            blocks={"10.0.0.0/8": 1},
            networks={},
            zones={},
        )
        resolver = DeferredResolver(pending)

        assert resolver.check_pending_block("10.0.0.0/8") == 1
        assert resolver.check_pending_block("192.168.0.0/16") is None

    def test_check_pending_network(self):
        """Test checking for pending networks."""
        pending = PendingResources(
            blocks={},
            networks={"10.1.0.0/24": 5},
            zones={},
        )
        resolver = DeferredResolver(pending)

        assert resolver.check_pending_network("10.1.0.0/24") == 5
        assert resolver.check_pending_network("10.2.0.0/24") is None

    def test_check_pending_zone(self):
        """Test checking for pending zones."""
        pending = PendingResources(
            blocks={},
            networks={},
            zones={"example.com": 10},
        )
        resolver = DeferredResolver(pending)

        assert resolver.check_pending_zone("example.com") == 10
        assert resolver.check_pending_zone("other.com") is None

    def test_find_containing_pending_block(self):
        """Test finding a pending block that contains a network."""
        pending = PendingResources(
            blocks={"10.0.0.0/8": 1, "192.168.0.0/16": 2},
            networks={},
            zones={},
        )
        resolver = DeferredResolver(pending)

        # 10.1.0.0/24 is within 10.0.0.0/8
        result = resolver.find_containing_pending_block("10.1.0.0/24")
        assert result is not None
        block_cidr, row_id = result
        assert block_cidr == "10.0.0.0/8"
        assert row_id == 1

        # 172.16.0.0/24 is not within any pending block
        assert resolver.find_containing_pending_block("172.16.0.0/24") is None

    def test_find_containing_pending_network(self):
        """Test finding a pending network that contains an address."""
        pending = PendingResources(
            blocks={},
            networks={"10.1.0.0/24": 5, "192.168.1.0/24": 6},
            zones={},
        )
        resolver = DeferredResolver(pending)

        # 10.1.0.50 is within 10.1.0.0/24
        result = resolver.find_containing_pending_network("10.1.0.50")
        assert result is not None
        net_cidr, row_id = result
        assert net_cidr == "10.1.0.0/24"
        assert row_id == 5

        # 172.16.0.1 is not within any pending network
        assert resolver.find_containing_pending_network("172.16.0.1") is None


class TestOperationFactory:
    """Test OperationFactory class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAMClient."""
        client = MagicMock()
        client.get_configuration_by_name = AsyncMock(return_value={"id": 100, "name": "Default"})
        client.get_view_by_name_in_config = AsyncMock(return_value={"id": 200, "name": "default"})
        client.get_zone_by_fqdn = AsyncMock(return_value={"id": 300, "name": "example.com"})
        client.find_block_containing_network = AsyncMock(
            return_value={"id": 400, "range": "10.0.0.0/8"}
        )
        client.find_network_containing_address = AsyncMock(
            return_value={"id": 500, "range": "10.1.0.0/24"}
        )
        client.get_network_by_cidr = AsyncMock(return_value={"id": 501, "range": "10.1.0.0/24"})
        return client

    @pytest.fixture
    def mock_resolver(self):
        """Create a mock Resolver."""
        resolver = MagicMock()
        resolver.resolve = AsyncMock(return_value=123)
        return resolver

    def test_get_operation_type(self, mock_client, mock_resolver):
        """Test operation type mapping."""
        factory = OperationFactory(mock_client, mock_resolver)

        assert factory._get_operation_type("create") == OperationType.CREATE
        assert factory._get_operation_type("update") == OperationType.UPDATE
        assert factory._get_operation_type("delete") == OperationType.DELETE
        assert factory._get_operation_type("unknown") == OperationType.NOOP

    @pytest.mark.asyncio
    async def test_create_from_row_block(self, mock_client, mock_resolver):
        """Test creating operation for an ip4_block row."""
        row = MagicMock()
        row.row_id = 1
        row.action = "create"
        row.object_type = "ip4_block"
        row.config = "Default"
        row.cidr = "10.0.0.0/8"
        row.name = "TestBlock"
        row.model_dump = MagicMock(
            return_value={
                "cidr": "10.0.0.0/8",
                "name": "TestBlock",
                "config": "Default",
            }
        )

        factory = OperationFactory(mock_client, mock_resolver)
        operation = await factory.create_from_row(row)

        assert operation.row_id == 1
        assert operation.operation_type == OperationType.CREATE
        assert operation.object_type == "ip4_block"
        assert operation.payload["config_id"] == 100

    @pytest.mark.asyncio
    async def test_create_from_row_network_with_auto_discovery(self, mock_client, mock_resolver):
        """Test creating operation for an ip4_network with auto-discovered parent block."""
        row = MagicMock()
        row.row_id = 2
        row.action = "create"
        row.object_type = "ip4_network"
        row.config = "Default"
        row.cidr = "10.1.0.0/24"
        row.name = "TestNetwork"
        row.parent = None  # No explicit parent, should auto-discover
        row.model_dump = MagicMock(
            return_value={
                "cidr": "10.1.0.0/24",
                "name": "TestNetwork",
                "config": "Default",
            }
        )

        factory = OperationFactory(mock_client, mock_resolver)
        operation = await factory.create_from_row(row)

        assert operation.row_id == 2
        assert operation.operation_type == OperationType.CREATE
        assert operation.object_type == "ip4_network"
        assert operation.payload["config_id"] == 100
        assert operation.payload["block_id"] == 400  # Auto-discovered

    @pytest.mark.asyncio
    async def test_create_from_row_network_with_deferred_block(self, mock_client, mock_resolver):
        """Test creating operation with deferred block resolution."""
        # Create pending resources with a block being created in same batch
        pending = PendingResources(
            blocks={"10.0.0.0/8": 1},
            networks={},
            zones={},
        )

        row = MagicMock()
        row.row_id = 2
        row.action = "create"
        row.object_type = "ip4_network"
        row.config = "Default"
        row.cidr = "10.1.0.0/24"  # This is within 10.0.0.0/8
        row.name = "TestNetwork"
        row.parent = None
        row.model_dump = MagicMock(
            return_value={
                "cidr": "10.1.0.0/24",
                "name": "TestNetwork",
                "config": "Default",
            }
        )

        factory = OperationFactory(mock_client, mock_resolver, pending)
        operation = await factory.create_from_row(row)

        assert operation.payload["_deferred_block_cidr"] == "10.0.0.0/8"
        assert operation.payload["_deferred_block_row"] == 1
        # block_id should NOT be set since it's deferred
        assert "block_id" not in operation.payload

    @pytest.mark.asyncio
    async def test_create_from_row_address_with_deferred_network(self, mock_client, mock_resolver):
        """Test creating operation with deferred network resolution."""
        pending = PendingResources(
            blocks={},
            networks={"10.1.0.0/24": 5},
            zones={},
        )

        row = MagicMock()
        row.row_id = 3
        row.action = "create"
        row.object_type = "ip4_address"
        row.config = "Default"
        row.address = "10.1.0.50"
        row.parent = None
        row.model_dump = MagicMock(
            return_value={
                "address": "10.1.0.50",
                "config": "Default",
            }
        )

        factory = OperationFactory(mock_client, mock_resolver, pending)
        operation = await factory.create_from_row(row)

        assert operation.payload["_deferred_network_cidr"] == "10.1.0.0/24"
        assert operation.payload["_deferred_network_row"] == 5

    @pytest.mark.asyncio
    async def test_create_from_row_dns_zone(self, mock_client, mock_resolver):
        """Test creating operation for a dns_zone row."""
        row = MagicMock()
        row.row_id = 10
        row.action = "create"
        row.object_type = "dns_zone"
        row.config = "Default"
        row.view_path = "default"
        row.zone_name = "example.com"
        row.model_dump = MagicMock(
            return_value={
                "zone_name": "example.com",
                "view_path": "default",
                "config": "Default",
            }
        )

        factory = OperationFactory(mock_client, mock_resolver)
        operation = await factory.create_from_row(row)

        assert operation.row_id == 10
        assert operation.object_type == "dns_zone"
        assert operation.payload["view_id"] == 200
        assert operation.payload["name"] == "example.com"

    @pytest.mark.asyncio
    async def test_create_from_row_host_record_with_deferred_zone(self, mock_client, mock_resolver):
        """Test creating operation with deferred zone resolution."""
        pending = PendingResources(
            blocks={},
            networks={},
            zones={"example.com": 10},
        )

        row = MagicMock()
        row.row_id = 11
        row.action = "create"
        row.object_type = "host_record"
        row.config = "Default"
        row.view_path = "default"
        row.name = "www.example.com"
        row.zone_name = "example.com"
        row.addresses = ["10.1.0.50"]
        row.model_dump = MagicMock(
            return_value={
                "name": "www.example.com",
                "zone_name": "example.com",
                "addresses": ["10.1.0.50"],
                "view_path": "default",
                "config": "Default",
            }
        )

        factory = OperationFactory(mock_client, mock_resolver, pending)
        operation = await factory.create_from_row(row)

        assert operation.payload["_deferred_zone_name"] == "example.com"
        assert operation.payload["_deferred_zone_row"] == 10

    @pytest.mark.asyncio
    async def test_create_from_row_delete_operation(self, mock_client, mock_resolver):
        """Test creating delete operation."""
        row = MagicMock()
        row.row_id = 20
        row.action = "delete"
        row.object_type = "ip4_block"
        row.config = "Default"
        row.bam_id = 999
        row.model_dump = MagicMock(
            return_value={
                "config": "Default",
            }
        )

        factory = OperationFactory(mock_client, mock_resolver)
        operation = await factory.create_from_row(row)
        assert operation.resource_id == 999

    @pytest.mark.asyncio
    async def test_create_resource_path_capture(self, mock_client, mock_resolver):
        """Test that resource_path is captured for cache invalidation."""
        factory = OperationFactory(mock_client, mock_resolver)

        # 1. Block
        row_block = MagicMock()
        row_block.row_id = 1
        row_block.action = "create"
        row_block.object_type = "ip4_block"
        row_block.config = "Default"
        row_block.cidr = "10.0.0.0/8"
        row_block.parent = "Default"
        row_block.model_dump = MagicMock(return_value={"cidr": "10.0.0.0/8"})

        op_block = await factory.create_from_row(row_block)
        assert op_block.payload.get("resource_path") == "Default/10.0.0.0/8"

        # 2. Network (with explicit parent)
        row_net = MagicMock()
        row_net.row_id = 2
        row_net.action = "create"
        row_net.object_type = "ip4_network"
        row_net.config = "Default"
        row_net.cidr = "10.0.0.0/24"
        row_net.parent = "Default/10.0.0.0/8"
        row_net.model_dump = MagicMock(return_value={"cidr": "10.0.0.0/24"})

        op_net = await factory.create_from_row(row_net)
        assert op_net.payload.get("resource_path") == "Default/10.0.0.0/8/10.0.0.0/24"

        # 3. Zone
        row_zone = MagicMock()
        row_zone.row_id = 3
        row_zone.action = "create"
        row_zone.object_type = "dns_zone"
        row_zone.config = "Default"
        row_zone.view_path = "default"
        row_zone.zone_name = "example.com"
        row_zone.location_code = None
        row_zone.model_dump = MagicMock(return_value={"zone_name": "example.com"})

        op_zone = await factory.create_from_row(row_zone)
        # Debug info if failure
        if "resource_path" not in op_zone.payload:
            print(f"DEBUG: Payload content: {op_zone.payload}")
        assert op_zone.payload.get("resource_path") == "example.com"


class TestOperationFactoryIntegration:
    """Integration tests for OperationFactory with multiple related rows."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAMClient."""
        client = MagicMock()
        client.get_configuration_by_name = AsyncMock(return_value={"id": 100})
        client.get_view_by_name_in_config = AsyncMock(return_value={"id": 200})
        client.get_zone_by_fqdn = AsyncMock(return_value={"id": 300})
        return client

    @pytest.fixture
    def mock_resolver(self):
        """Create a mock Resolver."""
        resolver = MagicMock()
        resolver.resolve = AsyncMock(return_value=123)
        return resolver

    @pytest.mark.asyncio
    async def test_batch_with_dependencies(self, mock_client, mock_resolver):
        """Test processing a batch with internal dependencies."""
        # Create rows simulating a typical import:
        # 1. Create block
        # 2. Create network in block
        # 3. Create address in network

        rows = []

        # Block row
        block_row = MagicMock()
        block_row.row_id = 1
        block_row.action = "create"
        block_row.object_type = "ip4_block"
        block_row.config = "Default"
        block_row.cidr = "10.0.0.0/8"
        block_row.name = "TestBlock"
        block_row.model_dump = MagicMock(return_value={"cidr": "10.0.0.0/8", "name": "TestBlock"})
        rows.append(block_row)

        # Network row
        network_row = MagicMock()
        network_row.row_id = 2
        network_row.action = "create"
        network_row.object_type = "ip4_network"
        network_row.config = "Default"
        network_row.cidr = "10.1.0.0/24"
        network_row.name = "TestNetwork"
        network_row.parent = None
        network_row.model_dump = MagicMock(
            return_value={"cidr": "10.1.0.0/24", "name": "TestNetwork"}
        )
        rows.append(network_row)

        # Address row
        address_row = MagicMock()
        address_row.row_id = 3
        address_row.action = "create"
        address_row.object_type = "ip4_address"
        address_row.config = "Default"
        address_row.address = "10.1.0.50"
        address_row.parent = None
        address_row.model_dump = MagicMock(return_value={"address": "10.1.0.50"})
        rows.append(address_row)

        # Build pending resources from rows
        pending = PendingResources.from_rows(rows)

        # Verify pending resources
        assert "10.0.0.0/8" in pending.blocks
        assert "10.1.0.0/24" in pending.networks

        # Create operations using factory
        factory = OperationFactory(mock_client, mock_resolver, pending)

        operations = []
        for row in rows:
            op = await factory.create_from_row(row)
            operations.append(op)

        # Verify deferred resolutions
        # Network should have deferred block
        network_op = operations[1]
        assert network_op.payload.get("_deferred_block_cidr") == "10.0.0.0/8"

        # Address should have deferred network
        address_op = operations[2]
        assert address_op.payload.get("_deferred_network_cidr") == "10.1.0.0/24"
