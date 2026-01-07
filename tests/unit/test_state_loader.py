"""Unit tests for State Loader."""

from unittest.mock import AsyncMock, patch

import pytest

from src.importer.bam.client import BAMClient
from src.importer.core.state_loader import StateLoader
from src.importer.models.state import ResourceIdentifier, ResourceState, StateLoadStrategy
from src.importer.utils.exceptions import ResourceNotFoundError


class TestStateLoader:
    """Test StateLoader class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = AsyncMock(spec=BAMClient)
        self.state_loader = StateLoader(self.mock_client)

    def test_init(self):
        """Test StateLoader initialization."""
        assert self.state_loader.client == self.mock_client
        assert self.state_loader.cache_enabled is True
        assert self.state_loader.cache == {}

    def test_init_cache_disabled(self):
        """Test StateLoader initialization with cache disabled."""
        loader = StateLoader(self.mock_client, cache_enabled=False)
        assert loader.cache_enabled is False

    def test_clear_cache(self):
        """Test cache clearing."""
        self.state_loader.cache[123] = "dummy_state"
        self.state_loader.clear_cache()
        assert len(self.state_loader.cache) == 0

    # Test load_resource_state
    @pytest.mark.asyncio
    async def test_load_resource_state_cache_hit(self):
        """Test resource state loading with cache hit."""
        identifiers = {"id": 123}
        cached_state = ResourceState(id=123, type="IP4Address", properties={"address": "10.1.0.5"})
        self.state_loader.cache[123] = cached_state

        result = await self.state_loader.load_resource_state(
            "ip4_address", identifiers, StateLoadStrategy.SHALLOW
        )

        assert result == cached_state
        self.mock_client.get_entity_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_resource_state_with_id(self):
        """Test loading resource state by ID."""
        identifiers = {"id": 123}
        api_data = {
            "id": 123,
            "type": "IP4Address",
            "properties": {"address": "10.1.0.5", "name": "server1"},
            "_etag": "abc123",
            "_version": 1,
        }
        expected_state = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1"},
            etag="abc123",
            version=1,
        )

        self.mock_client.get_entity_by_id.return_value = api_data

        result = await self.state_loader.load_resource_state(
            "ip4_address", identifiers, StateLoadStrategy.SHALLOW
        )

        assert result.id == expected_state.id
        assert result.properties == expected_state.properties

        self.mock_client.get_entity_by_id.assert_called_once_with(123, "IP4Address")
        assert 123 in self.state_loader.cache

    @pytest.mark.asyncio
    async def test_load_resource_state_with_name(self):
        """Test loading resource state by name."""
        identifiers = {"name": "server1"}
        api_response = {
            "_embedded": {
                "items": [
                    {
                        "id": 123,
                        "type": "IP4Address",
                        "properties": {"address": "10.1.0.5", "name": "server1"},
                    }
                ]
            }
        }

        self.mock_client.get.return_value = api_response

        result = await self.state_loader.load_resource_state(
            "ip4_address", identifiers, StateLoadStrategy.SHALLOW
        )

        assert result is not None
        assert result.id == 123
        assert result.properties["name"] == "server1"

    @pytest.mark.asyncio
    async def test_load_resource_state_not_found(self):
        """Test loading resource state when not found."""
        identifiers = {"id": 123}
        # ResourceNotFoundError requires (resource_type, identifier)
        self.mock_client.get_entity_by_id.side_effect = ResourceNotFoundError("IP4Address", "123")

        result = await self.state_loader.load_resource_state(
            "ip4_address", identifiers, StateLoadStrategy.SHALLOW
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_load_resource_state_children_strategy(self):
        """Test loading resource state with children strategy."""
        identifiers = {"id": 123}
        # For embedded fetch, the response contains both parent and children
        api_response = {
            "id": 123,
            "type": "IP4Network",
            "properties": {"CIDR": "10.1.0.0/24"},
            "_embedded": {
                "addresses": [  # Note: _get_child_collection_name maps ip4_network -> addresses
                    {
                        "id": 124,
                        "type": "IP4Address",
                        "properties": {"address": "10.1.0.1"},
                    }
                ]
            },
        }

        # The StateLoader will try embedded fetch first for CHILDREN strategy
        self.mock_client.get.return_value = api_response

        result = await self.state_loader.load_resource_state(
            "ip4_network", identifiers, StateLoadStrategy.CHILDREN
        )

        assert result is not None
        assert result.id == 123
        assert len(result.children) == 1
        assert result.children[0].id == 124

    @pytest.mark.asyncio
    async def test_load_resource_state_deep_strategy(self):
        """Test loading resource state with deep strategy."""
        identifiers = {"id": 123}
        api_data = {
            "id": 123,
            "type": "IP4Network",
            "properties": {"CIDR": "10.1.0.0/24"},
        }
        # Mock get_addresses_in_network to return addresses for the network
        children_data = [
            {
                "id": 124,
                "type": "IP4Address",
                "properties": {"address": "10.1.0.1"},
            }
        ]

        self.mock_client.get_entity_by_id.return_value = api_data
        # For DEEP strategy, it calls _fetch_children which now uses get_addresses_in_network
        self.mock_client.get_addresses_in_network = AsyncMock(return_value=children_data)

        result = await self.state_loader.load_resource_state(
            "ip4_network", identifiers, StateLoadStrategy.DEEP
        )

        assert result is not None
        assert result.id == 123
        assert len(result.children) == 1
        assert result.children[0].id == 124

    @pytest.mark.asyncio
    async def test_load_resource_state_no_valid_identifiers(self):
        """Test loading resource state with no valid identifiers."""
        identifiers = {"invalid": "value"}

        result = await self.state_loader.load_resource_state(
            "ip4_address", identifiers, StateLoadStrategy.SHALLOW
        )

        assert result is None
        self.mock_client.get.assert_not_called()

    # Test batch loading
    @pytest.mark.asyncio
    async def test_batch_load(self):
        """Test batch loading of resources."""
        resources = [
            ResourceIdentifier(resource_type="ip4_address", id=123),
            ResourceIdentifier(resource_type="ip4_address", id=124),
        ]
        api_data1 = {
            "id": 123,
            "type": "IP4Address",
            "properties": {"address": "10.1.0.1"},
        }
        api_data2 = {
            "id": 124,
            "type": "IP4Address",
            "properties": {"address": "10.1.0.2"},
        }

        self.mock_client.get_entity_by_id.side_effect = [api_data1, api_data2]

        result = await self.state_loader.batch_load(resources, StateLoadStrategy.SHALLOW)

        assert len(result) == 2
        key1 = resources[0].key
        key2 = resources[1].key
        assert key1 in result
        assert key2 in result
        assert result[key1].id == 123
        assert result[key2].id == 124

    @pytest.mark.asyncio
    async def test_batch_load_with_concurrency_limit(self):
        """Test batch loading with concurrency limit."""
        resources = [ResourceIdentifier(resource_type="ip4_address", id=100 + i) for i in range(5)]

        # Mock responses for each resource
        api_responses = [
            {
                "id": 100 + i,
                "type": "IP4Address",
                "properties": {"address": f"10.1.0.{i}"},
            }
            for i in range(5)
        ]
        self.mock_client.get_entity_by_id.side_effect = api_responses

        result = await self.state_loader.batch_load(
            resources, StateLoadStrategy.SHALLOW, max_concurrency=2
        )

        assert len(result) == 5
        for i, res in enumerate(resources):
            assert res.key in result
            assert result[res.key].id == 100 + i

    @pytest.mark.asyncio
    async def test_batch_load_with_exceptions(self):
        """Test batch loading handles exceptions gracefully."""
        resources = [
            ResourceIdentifier(resource_type="ip4_address", id=123),
            ResourceIdentifier(resource_type="ip4_address", id=124),
        ]
        api_data = {
            "id": 123,
            "type": "IP4Address",
            "properties": {"address": "10.1.0.1"},
        }

        self.mock_client.get_entity_by_id.side_effect = [
            api_data,
            ResourceNotFoundError("IP4Address", "124"),
        ]

        result = await self.state_loader.batch_load(resources, StateLoadStrategy.SHALLOW)

        assert len(result) == 2
        assert resources[0].key in result
        assert result[resources[0].key] is not None

        # Expect None for the resource not found
        assert resources[1].key in result
        assert result[resources[1].key] is None

    # Test endpoint building
    def test_build_search_endpoint_configuration(self):
        """Test building search endpoint for configuration."""
        endpoint, params = self.state_loader._build_search_endpoint(
            "configuration",
            {"name": "TestConfig"},
            ["name:eq:TestConfig"],
            100,
        )

        assert endpoint == "configurations"
        assert params["limit"] == 100
        assert params["filter"] == "name:eq:TestConfig"

    def test_build_search_endpoint_block_with_config(self):
        """Test building search endpoint for block under configuration."""
        endpoint, params = self.state_loader._build_search_endpoint(
            "ip4_block",
            {"config_id": 1, "cidr": "10.0.0.0/8"},
            ["CIDR:eq:10.0.0.0/8"],
            100,
        )

        assert endpoint == "configurations/1/blocks"
        assert params["limit"] == 100
        assert params["filter"] == "CIDR:eq:10.0.0.0/8"

    def test_build_search_endpoint_block_without_config(self):
        """Test building search endpoint for block without configuration."""
        endpoint, params = self.state_loader._build_search_endpoint(
            "ip4_block",
            {"cidr": "10.0.0.0/8"},
            ["CIDR:eq:10.0.0.0/8"],
            100,
        )

        assert endpoint == "blocks"
        assert params["limit"] == 100
        assert params["filter"] == "CIDR:eq:10.0.0.0/8"

    def test_build_search_endpoint_network_with_block(self):
        """Test building search endpoint for network under block."""
        endpoint, params = self.state_loader._build_search_endpoint(
            "ip4_network",
            {"block_id": 2, "cidr": "10.1.0.0/24"},
            ["CIDR:eq:10.1.0.0/24"],
            100,
        )

        assert endpoint == "blocks/2/networks"
        assert params["limit"] == 100
        assert params["filter"] == "CIDR:eq:10.1.0.0/24"

    def test_build_search_endpoint_address_with_network(self):
        """Test building search endpoint for address under network."""
        endpoint, params = self.state_loader._build_search_endpoint(
            "ip4_address",
            {"network_id": 3, "address": "10.1.0.5"},
            ["address:eq:10.1.0.5"],
            100,
        )

        assert endpoint == "networks/3/addresses"
        assert params["limit"] == 100
        assert params["filter"] == "address:eq:10.1.0.5"

    def test_build_search_endpoint_host_record_with_zone(self):
        """Test building search endpoint for host record under zone."""
        endpoint, params = self.state_loader._build_search_endpoint(
            "host_record",
            {"zone_id": 4, "name": "server1"},
            ["name:eq:server1"],
            100,
        )

        assert endpoint == "zones/4/resourceRecords"
        assert params["limit"] == 100
        assert params["filter"] == "type:eq:HostRecord,name:eq:server1"

    def test_build_search_endpoint_generic_entity(self):
        """Test building search endpoint for generic entity raises ValueError."""
        with pytest.raises(ValueError):
            self.state_loader._build_search_endpoint(
                "custom_type",
                {"name": "custom1"},
                ["name:eq:custom1"],
                100,
            )

    def test_build_search_endpoint_no_filters(self):
        """Test building search endpoint with no filters."""
        endpoint, params = self.state_loader._build_search_endpoint("ip4_address", {}, [], 100)

        assert endpoint == "addresses"
        assert params["limit"] == 100
        assert "filter" not in params

    # Test fetching children
    @pytest.mark.asyncio
    async def test_fetch_children_configuration(self):
        """Test fetching children of configuration."""
        # Mock get_ip4_blocks to return blocks list directly (pagination handled internally)
        blocks_data = [
            {
                "id": 101,
                "type": "IP4Block",
                "properties": {"CIDR": "10.0.0.0/8"},
            }
        ]

        self.mock_client.get_ip4_blocks = AsyncMock(return_value=blocks_data)

        children = await self.state_loader._fetch_children(1, "configuration")

        assert len(children) == 1
        assert children[0].id == 101
        assert children[0].type == "IP4Block"
        self.mock_client.get_ip4_blocks.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_fetch_children_block(self):
        """Test fetching children of block."""
        # Mock get_child_networks to return networks list directly (pagination handled internally)
        networks_data = [
            {
                "id": 102,
                "type": "IP4Network",
                "properties": {"CIDR": "10.1.0.0/24"},
            }
        ]

        self.mock_client.get_child_networks = AsyncMock(return_value=networks_data)

        children = await self.state_loader._fetch_children(101, "ip4_block")

        assert len(children) == 1
        assert children[0].id == 102
        self.mock_client.get_child_networks.assert_called_once_with(101)

    @pytest.mark.asyncio
    async def test_fetch_children_network(self):
        """Test fetching children of network."""
        # Mock get_addresses_in_network to return addresses list directly (pagination handled internally)
        addresses_data = [
            {
                "id": 103,
                "type": "IP4Address",
                "properties": {"address": "10.1.0.1"},
            }
        ]

        self.mock_client.get_addresses_in_network = AsyncMock(return_value=addresses_data)

        children = await self.state_loader._fetch_children(102, "network")

        assert len(children) == 1
        assert children[0].id == 103
        self.mock_client.get_addresses_in_network.assert_called_once_with(102)

    @pytest.mark.asyncio
    async def test_fetch_children_unsupported_type(self):
        """Test fetching children for unsupported resource type."""
        children = await self.state_loader._fetch_children(1, "unsupported_type")

        assert len(children) == 0
        self.mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_children_with_exception(self):
        """Test fetching children handles exceptions."""
        self.mock_client.get.side_effect = Exception("API Error")

        children = await self.state_loader._fetch_children(1, "configuration")

        assert len(children) == 0

    # Test subtree fetching
    @pytest.mark.asyncio
    async def test_fetch_subtree(self):
        """Test fetching full subtree."""

        # Mock _fetch_children to return predictable data
        async def mock_fetch_children(resource_id, resource_type):
            if resource_id == 1:  # Root
                return [ResourceState(id=2, type="IP4Network", properties={"CIDR": "10.1.0.0/24"})]
            elif resource_id == 2:  # Child
                return [ResourceState(id=3, type="IP4Address", properties={"address": "10.1.0.1"})]
            return []

        with patch.object(self.state_loader, "_fetch_children", side_effect=mock_fetch_children):
            descendants = await self.state_loader._fetch_subtree(1, "configuration")

        assert len(descendants) == 2  # Child + grandchild
        assert any(d.id == 2 for d in descendants)
        assert any(d.id == 3 for d in descendants)

    # Test resource parsing
    def test_parse_resource_state_complete(self):
        """Test parsing complete resource state."""
        data = {
            "id": 123,
            "type": "IP4Address",
            "properties": {
                "address": "10.1.0.5",
                "name": "server1",
                "mac": "00:11:22:33:44:55",
            },
            "_etag": "abc123",
            "_version": 1,
            "_links": {"self": {"href": "/api/v2/addresses/123"}},
        }

        state = self.state_loader._parse_resource_state(data)

        assert state.id == 123
        assert state.type == "IP4Address"
        assert state.properties["address"] == "10.1.0.5"
        assert state.properties["name"] == "server1"
        assert state.etag == "abc123"
        assert state.version == 1
        assert state.children is None

    def test_parse_resource_state_minimal(self):
        """Test parsing minimal resource state."""
        data = {
            "id": 123,
            "type": "IP4Address",
            "properties": {"address": "10.1.0.5"},
        }

        state = self.state_loader._parse_resource_state(data)

        assert state.id == 123
        assert state.type == "IP4Address"
        assert state.properties["address"] == "10.1.0.5"
        assert state.etag is None
        assert state.version is None
        assert state.children is None

    def test_parse_resource_state_missing_properties(self):
        """Test parsing resource state without properties."""
        data = {"id": 123, "type": "IP4Address"}

        state = self.state_loader._parse_resource_state(data)

        assert state.id == 123
        assert state.type == "IP4Address"
        assert state.properties == {}
