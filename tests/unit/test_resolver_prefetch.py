from unittest.mock import AsyncMock, Mock

import pytest

from src.importer.core.resolver import Resolver


@pytest.fixture
def mock_client():
    client = AsyncMock()
    # Mock return values for methods used in bulk resolution
    client.get_child_networks.return_value = []
    client.get_zones_in_view.return_value = []
    return client


@pytest.fixture
def resolver(mock_client, tmp_path):
    # Using tmp_path for cache_dir
    return Resolver(mock_client, cache_dir=tmp_path / "cache", no_cache=True)


@pytest.mark.asyncio
class TestResolverPrefetch:

    async def test_bulk_resolve_networks(self, resolver, mock_client):
        # Setup
        parent_id = 100
        cidrs = ["10.0.0.0/24", "10.0.1.0/24"]

        mock_response = [
            {"id": 10, "type": "IP4Network", "properties": {"range": "10.0.0.0/24"}},
            {"id": 11, "type": "IP4Network", "properties": {"CIDR": "10.0.1.0/24"}},
        ]
        mock_client.get_child_networks.return_value = (
            mock_response  # Assuming method matches client
        )

        # Execute
        result = await resolver.bulk_resolve_networks(parent_id, cidrs)

        # Verify
        assert len(result) == 2
        assert result["10.0.0.0/24"] == 10
        assert result["10.0.1.0/24"] == 11

        # Verify filter
        mock_client.get_child_networks.assert_called_once()
        filter_arg = mock_client.get_child_networks.call_args[1]["filter"]
        assert "range:in('10.0.0.0/24','10.0.1.0/24')" in filter_arg

    async def test_bulk_resolve_zones(self, resolver, mock_client):
        # Setup
        view_id = 200
        names = ["example.com"]

        mock_response = [{"id": 20, "type": "DNSZone", "properties": {"name": "example.com"}}]
        mock_client.get_zones_in_view.return_value = mock_response

        # Execute
        result = await resolver.bulk_resolve_zones(view_id, names)

        # Verify
        assert result["example.com"] == 20

        # Verify filter
        mock_client.get_zones_in_view.assert_called_once()
        filter_arg = mock_client.get_zones_in_view.call_args[1]["filter"]
        assert "name:in('example.com')" in filter_arg

    async def test_prefetch_from_csv_structure(self, resolver):
        # Smoke test for the structural method
        rows = [Mock(object_type="ip4_network"), Mock(object_type="ip4_address")]
        await resolver.prefetch_from_csv(rows)
        # Should complete without error
