from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.importer.bam.client import BAMAuthenticationError, BAMClient
from src.importer.config import BAMConfig


@pytest.fixture
def mock_config():
    return BAMConfig(
        base_url="https://example.com", username="user", password="pass", api_version="v2"
    )


@pytest.mark.asyncio
async def test_request_recursion_prevention(mock_config):
    """Test that infinite recursion on 401 is prevented."""
    client = BAMClient(mock_config)

    # Mock the internal client and its request method
    client._client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 401
    mock_response.headers = {}
    mock_response.text = "Unauthorized"
    client._client.request.return_value = mock_response

    # Mock authenticate to succeed and SET CREDENTIALS
    async def side_effect(force=False):
        client.basic_auth_credentials = "mock_creds"

    with patch.object(client, "authenticate", new_callable=AsyncMock) as mock_auth:
        mock_auth.side_effect = side_effect

        with pytest.raises(BAMAuthenticationError) as exc_info:
            await client.request("GET", "test")

        assert "Authentication failed after retry" in str(exc_info.value)

        # Verify call count
        # client.request (httpx) should be called twice:
        # 1. Initial request -> 401
        # 2. Retry request -> 401
        assert client._client.request.call_count == 2

        # authenticate should be called twice:
        # 1. Initial check (creds are None)
        # 2. Force re-auth after 401
        assert mock_auth.call_count == 2
