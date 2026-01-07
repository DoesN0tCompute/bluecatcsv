from unittest.mock import AsyncMock

import pytest

from src.importer.core.state_loader import StateLoader


@pytest.fixture
def mock_client():
    client = AsyncMock()
    # Mock client methods to return lists of dicts
    client.get_addresses_in_network.return_value = []
    client.get_child_networks.return_value = []
    client.get_zones_in_view.return_value = []
    client.get_resource_records_in_zone.return_value = []
    return client


@pytest.fixture
def state_loader(mock_client):
    return StateLoader(mock_client, cache_enabled=True)


@pytest.mark.asyncio
class TestStateLoaderBulk:

    async def test_bulk_load_addresses(self, state_loader, mock_client):
        # Setup
        network_id = 100
        addresses = ["10.0.0.1", "10.0.0.2"]

        mock_response = [
            {"id": 1, "type": "IP4Address", "properties": {"address": "10.0.0.1"}},
            {"id": 2, "type": "IP4Address", "properties": {"address": "10.0.0.2"}},
        ]
        mock_client.get_addresses_in_network.return_value = mock_response

        # Execute
        result = await state_loader.bulk_load_addresses(network_id, addresses)

        # Verify
        assert len(result) == 2
        assert "10.0.0.1" in result
        assert "10.0.0.2" in result
        assert result["10.0.0.1"].id == 1

        # Verify filter construction
        mock_client.get_addresses_in_network.assert_called_once()
        call_args = mock_client.get_addresses_in_network.call_args
        assert call_args[0] == (network_id,)
        assert "address:in(10.0.0.1,10.0.0.2)" in call_args[1]["filter"]

    async def test_bulk_load_addresses_empty(self, state_loader):
        result = await state_loader.bulk_load_addresses(100, [])
        assert result == {}

    async def test_bulk_load_networks(self, state_loader, mock_client):
        # Setup
        block_id = 200
        cidrs = ["10.1.0.0/24", "10.2.0.0/24"]

        mock_response = [
            {"id": 10, "type": "IP4Network", "properties": {"CIDR": "10.1.0.0/24"}},
            {"id": 20, "type": "IP4Network", "properties": {"CIDR": "10.2.0.0/24"}},
        ]
        mock_client.get_child_networks.return_value = mock_response

        # Execute
        result = await state_loader.bulk_load_networks(block_id, cidrs)

        # Verify
        assert len(result) == 2
        assert "10.1.0.0/24" in result
        assert result["10.1.0.0/24"].id == 10

        # Verify filter construction with quotes
        mock_client.get_child_networks.assert_called_once()
        filter_arg = mock_client.get_child_networks.call_args[1]["filter"]
        # Expected: range:in('10.1.0.0/24','10.2.0.0/24')
        assert "range:in('10.1.0.0/24','10.2.0.0/24')" in filter_arg

    async def test_bulk_load_zones(self, state_loader, mock_client):
        # Setup
        view_id = 300
        names = ["example.com", "foo.local"]

        mock_response = [
            {"id": 30, "type": "DNSZone", "properties": {"name": "example.com"}},
            {"id": 40, "type": "DNSZone", "properties": {"name": "foo.local"}},
        ]
        mock_client.get_zones_in_view.return_value = mock_response

        # Execute
        result = await state_loader.bulk_load_zones(view_id, names)

        # Verify
        assert len(result) == 2
        assert "example.com" in result

        # Verify filter construction
        mock_client.get_zones_in_view.assert_called_once()
        filter_arg = mock_client.get_zones_in_view.call_args[1]["filter"]
        assert "name:in('example.com','foo.local')" in filter_arg

    async def test_bulk_load_records(self, state_loader, mock_client):
        # Setup
        zone_id = 400
        names = ["www", "mail"]

        mock_response = [
            {"id": 50, "type": "HostRecord", "properties": {"name": "www"}},
            {
                "id": 51,
                "type": "AliasRecord",
                "properties": {"name": "www"},
            },  # Duplicate name scenario
            {"id": 60, "type": "MXRecord", "properties": {"name": "mail"}},
        ]
        mock_client.get_resource_records_in_zone.return_value = mock_response

        # Execute
        result = await state_loader.bulk_load_records(zone_id, names)

        # Verify
        assert len(result) == 2
        assert len(result["www"]) == 2
        assert len(result["mail"]) == 1

        # Verify filter
        mock_client.get_resource_records_in_zone.assert_called_once()
        filter_arg = mock_client.get_resource_records_in_zone.call_args[1]["filter"]
        assert "name:in('www','mail')" in filter_arg

    async def test_bulk_load_records_with_type(self, state_loader, mock_client):
        # Setup
        zone_id = 400
        names = ["www"]

        mock_client.get_resource_records_in_zone.return_value = []

        # Execute
        await state_loader.bulk_load_records(zone_id, names, record_type="HostRecord")

        # Verify filter has both parts
        mock_client.get_resource_records_in_zone.assert_called_once()
        filter_arg = mock_client.get_resource_records_in_zone.call_args[1]["filter"]
        assert "name:in('www')" in filter_arg
        assert "type:eq:HostRecord" in filter_arg

    async def test_chunking(self, state_loader, mock_client):
        # Setup many items to force chunking
        network_id = 100
        # 60 addresses (chunk size 50)
        addresses = [f"10.0.0.{i}" for i in range(60)]

        mock_client.get_addresses_in_network.return_value = []

        # Execute
        await state_loader.bulk_load_addresses(network_id, addresses)

        # Verify
        assert mock_client.get_addresses_in_network.call_count == 2
