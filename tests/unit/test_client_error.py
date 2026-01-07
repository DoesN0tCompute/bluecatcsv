from unittest.mock import AsyncMock, Mock

import pytest

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.utils.exceptions import BAMAPIError


@pytest.fixture
def mock_client_error():
    config = BAMConfig(base_url="http://bam.example.com", username="test", password="password")
    client = BAMClient(config)
    client.basic_auth_credentials = "fake_creds"  # Bypass auth
    client._client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_improved_error_message(mock_client_error):
    # Mock response with JSON error
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.is_error = True
    mock_response.text = (
        '{"code": "ERR_123", "message": "Database failure", "detail": "Traceback..."}'
    )
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json = Mock(
        return_value={"code": "ERR_123", "message": "Database failure", "detail": "Traceback..."}
    )

    mock_client_error._client.request = AsyncMock(return_value=mock_response)

    with pytest.raises(BAMAPIError) as excinfo:
        await mock_client_error.request("GET", "test")

    error_msg = str(excinfo.value)
    print(f"Got error message: {error_msg}")

    # Assert improved format
    assert "Database failure" in error_msg
    assert "ERR_123" in error_msg
    assert "Traceback" in error_msg
    assert "{" not in error_msg  # Should be parsed
