from unittest.mock import AsyncMock

import pytest

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig


@pytest.fixture
def mock_client():
    config = BAMConfig(base_url="http://bam.example.com", username="test", password="password")
    client = BAMClient(config)
    client.get = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_resolve_interface_ipv6_bracketed_interface(mock_client):
    """Test [IPv6]:interface format."""
    # Mock server lookup
    mock_client.get_server_by_name = AsyncMock(return_value={"id": 100})
    # Mock interfaces lookup
    mock_client.get_server_interfaces = AsyncMock(
        return_value=[{"id": 10, "name": "eth0", "server": {"id": 100}}]
    )

    # Execute
    result = await mock_client.resolve_interface_string("[fe80::1]:eth0")

    # Assert
    assert result == 10
    mock_client.get_server_by_name.assert_called_with("fe80::1")


@pytest.mark.asyncio
async def test_resolve_interface_ipv6_bracketed_server_only(mock_client):
    """Test [IPv6] format (server only)."""
    # Mock server lookup
    mock_client.get_server_by_name = AsyncMock(return_value={"id": 100})
    # Mock interfaces lookup
    mock_client.get_server_interfaces = AsyncMock(
        return_value=[{"id": 10, "name": "eth0", "server": {"id": 100}}]
    )

    # Execute
    result = await mock_client.resolve_interface_string("[fe80::1]")

    # Assert
    assert result == 10
    # Should look up the server using the content inside brackets or as is?
    # Usually if user wraps in brackets, they mean the IPv6 address.
    # BAM likely expects the IP or hostname as server name.
    # If the user provides [fe80::1], the server name is likely "fe80::1".
    mock_client.get_server_by_name.assert_called_with("fe80::1")
