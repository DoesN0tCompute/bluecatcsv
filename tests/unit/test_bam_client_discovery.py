"""Tests for BAMClient resource discovery methods."""

from unittest.mock import AsyncMock

import pytest

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.utils.exceptions import ResourceNotFoundError


class TestBAMClientDiscovery:
    """Test BAMClient discovery methods."""

    @pytest.fixture
    def config(self):
        """Create a mock configuration."""
        return BAMConfig(
            base_url="https://bam.example.com",
            username="test",
            password="password",
            api_version="v2",
        )

    @pytest.fixture
    def client(self, config):
        """Create a BAMClient instance with mocked httpx client."""
        client = BAMClient(config)
        client._client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_find_network_containing_address_success(self, client):
        """Test finding network containing address with multiple candidates."""
        config_id = 1
        address = "10.1.0.50"

        # Mock API response with two networks containing the IP
        # 10.0.0.0/8 (less specific) and 10.1.0.0/16 (more specific)
        candidates = [
            {"id": 100, "name": "LargeNet", "range": "10.0.0.0/8"},
            {"id": 101, "name": "SmallNet", "range": "10.1.0.0/16"},
        ]

        # Mock the get call
        client.get = AsyncMock(return_value={"data": candidates})

        result = await client.find_network_containing_address(config_id, address)

        # Should verify the API call arguments
        client.get.assert_called_once_with(
            "networks",
            params={"filter": f"configuration.id:{config_id} and range:contains('{address}')"},
        )

        # Should return the most specific match (longest prefix)
        assert result["id"] == 101
        assert result["range"] == "10.1.0.0/16"

    @pytest.mark.asyncio
    async def test_find_network_containing_address_no_match(self, client):
        """Test finding network when no candidates return."""
        config_id = 1
        address = "192.168.1.1"

        # Mock API response with empty data
        client.get = AsyncMock(return_value={"data": []})

        with pytest.raises(ResourceNotFoundError) as exc:
            await client.find_network_containing_address(config_id, address)

        assert address in str(exc.value)

    @pytest.mark.asyncio
    async def test_find_block_containing_address_success(self, client):
        """Test finding block containing address."""
        config_id = 1
        address = "10.1.0.50"

        # Mock API response
        candidates = [
            {"id": 200, "name": "ParentBlock", "range": "10.0.0.0/8"},
        ]

        client.get = AsyncMock(return_value={"data": candidates})

        result = await client.find_block_containing_address(config_id, address)

        # Verify API call
        client.get.assert_called_once_with(
            "blocks",
            params={"filter": f"configuration.id:{config_id} and range:contains('{address}')"},
        )

        assert result["id"] == 200

    @pytest.mark.asyncio
    async def test_find_block_containing_network(self, client):
        """Test finding block containing network."""
        config_id = 1
        network_cidr = "10.1.1.0/24"
        network_address = "10.1.1.0"

        # Mock candidates
        candidates = [
            {"id": 300, "range": "10.0.0.0/8"},  # Valid parent
            {"id": 301, "range": "192.168.0.0/16"},  # Irrelevant
        ]

        client.get = AsyncMock(return_value={"data": candidates})

        result = await client.find_block_containing_network(config_id, network_cidr)

        # Verify API call uses network address
        client.get.assert_called_once_with(
            "blocks",
            params={
                "filter": f"configuration.id:{config_id} and range:contains('{network_address}')"
            },
        )

        assert result["id"] == 300
