"""Tests for BAM client ExternalHostRecord methods."""

import json

import httpx
import pytest
import respx

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.utils.exceptions import BAMAPIError


class TestBAMClientExternalHostRecord:
    """Test BAM client external host record operations."""

    @pytest.fixture
    def client(self):
        """Create a BAMClient for testing."""
        config = BAMConfig(
            base_url="https://bam.example.com",
            username="testuser",
            password="testpass",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        return BAMClient(config=config)

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_external_host_record_success(self, client):
        """Test successful external host record creation."""
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock the API response
        mock_route = respx.post("https://bam.example.com/api/v2/zones/12345/resourceRecords").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 67890,
                    "name": "host.external.com",
                    "type": "ExternalHostRecord",
                    "_links": {"self": {"href": "/api/v2/resourceRecords/67890"}},
                },
            )
        )

        result = await client.create_external_host_record(
            zone_id=12345,
            view_id=999,
            name="host.external.com",
            ttl=3600,
            comment="External host record",
        )

        # Verify result
        assert result["id"] == 67890
        assert result["name"] == "host.external.com"
        assert result["type"] == "ExternalHostRecord"

        # Verify request was made correctly
        assert mock_route.called
        request = mock_route.calls[0].request
        request_json = json.loads(request.content.decode())
        assert request_json == {
            "type": "ExternalHostRecord",
            "name": "host.external.com",
            "view": {"id": 999},
            "ttl": 3600,
            "comment": "External host record",
        }

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_external_host_record_minimal(self, client):
        """Test external host record creation with minimal parameters."""
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock the API response
        mock_route = respx.post("https://bam.example.com/api/v2/zones/12345/resourceRecords").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 67891,
                    "name": "minimal.external.com",
                    "type": "ExternalHostRecord",
                },
            )
        )

        result = await client.create_external_host_record(
            zone_id=12345, view_id=999, name="minimal.external.com"
        )

        # Verify result
        assert result["id"] == 67891
        assert result["name"] == "minimal.external.com"

        # Verify request was made correctly
        assert mock_route.called
        request = mock_route.calls[0].request
        request_json = json.loads(request.content.decode())
        assert request_json == {
            "type": "ExternalHostRecord",
            "name": "minimal.external.com",
            "view": {"id": 999},
        }

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_external_host_record_with_properties(self, client):
        """Test external host record creation with UDF properties."""
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock the API response
        mock_route = respx.post("https://bam.example.com/api/v2/zones/12345/resourceRecords").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 67892,
                    "name": "host.external.com",
                    "type": "ExternalHostRecord",
                    "userDefinedFields": {
                        "udf_owner": "External Team",
                        "udf_environment": "Production",
                    },
                },
            )
        )

        result = await client.create_external_host_record(
            zone_id=12345,
            view_id=999,
            name="host.external.com",
            properties={"udf_owner": "External Team", "udf_environment": "Production"},
        )

        # Verify result
        assert result["id"] == 67892
        assert "userDefinedFields" in result

        # Verify request was made correctly
        assert mock_route.called
        request = mock_route.calls[0].request
        assert "udf_owner" in request.content.decode()
        assert "udf_environment" in request.content.decode()

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_external_host_record_api_error(self, client):
        """Test external host record creation with API error."""
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock API error response
        respx.post("https://bam.example.com/api/v2/zones/12345/resourceRecords").mock(
            return_value=httpx.Response(
                400, json={"code": "INVALID_NAME", "message": "Invalid host name format"}
            )
        )

        with pytest.raises(BAMAPIError):
            await client.create_external_host_record(
                zone_id=12345, view_id=999, name="invalid..name"
            )
