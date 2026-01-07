"""Tests for BAM client server resolution functionality."""

import httpx
import pytest
import respx

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig
from src.importer.utils.exceptions import BAMAPIError, ResourceNotFoundError


@pytest.mark.asyncio
async def test_get_server_by_name_success() -> None:
    """Test successful server lookup by name."""
    # Mock the API response
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock the servers endpoint with filter
        servers_route = respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": 12345, "name": "test-server", "service": "DHCP,DNS"}]}
            )
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.get_server_by_name("test-server")

        assert result is not None
        assert result["id"] == 12345
        assert result["name"] == "test-server"
        assert servers_route.called
        assert "filter" in servers_route.calls.last.request.url.params


@pytest.mark.asyncio
async def test_get_server_by_name_not_found() -> None:
    """Test server lookup when server is not found."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock empty response
        servers_route = respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.get_server_by_name("non-existent-server")

        assert result is None
        assert servers_route.called


@pytest.mark.asyncio
async def test_get_server_interfaces_success() -> None:
    """Test successful interface retrieval for a server."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock the server interfaces endpoint
        interfaces_route = respx.get(
            "https://bam.example.com/api/v2/servers/12345/interfaces"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {"id": 67890, "name": "eth0", "IPAddresses": [{"address": "192.168.1.10"}]},
                        {"id": 67891, "name": "eth1", "IPAddresses": [{"address": "10.1.1.10"}]},
                    ]
                },
            )
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.get_server_interfaces(12345)

        assert len(result) == 2
        assert result[0]["id"] == 67890
        assert result[0]["name"] == "eth0"
        assert result[1]["id"] == 67891
        assert result[1]["name"] == "eth1"
        assert interfaces_route.called


@pytest.mark.asyncio
async def test_resolve_server_name_to_interface_id_success() -> None:
    """Test successful server name to interface ID resolution."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock server lookup
        servers_route = respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 12345, "name": "test-server"}]})
        )

        # Mock interfaces lookup
        interfaces_route = respx.get(
            "https://bam.example.com/api/v2/servers/12345/interfaces"
        ).mock(return_value=httpx.Response(200, json={"data": [{"id": 67890, "name": "eth0"}]}))

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.resolve_server_name_to_interface_id("test-server")

        assert result == 67890
        assert servers_route.called
        assert interfaces_route.called


@pytest.mark.asyncio
async def test_resolve_server_name_to_interface_id_server_not_found() -> None:
    """Test resolution when server is not found."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock empty server response
        respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.resolve_server_name_to_interface_id("non-existent-server")

        assert result is None


@pytest.mark.asyncio
async def test_resolve_interface_string_numeric_id() -> None:
    """Test resolving numeric interface ID with validation."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock interface validation
        interface_route = respx.get("https://bam.example.com/api/v2/interfaces/12345").mock(
            return_value=httpx.Response(200, json={"id": 12345, "name": "eth0"})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.resolve_interface_string("12345")

        assert result == 12345
        assert interface_route.called


@pytest.mark.asyncio
async def test_resolve_interface_string_numeric_id_not_found() -> None:
    """Test resolving numeric interface ID that does not exist."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock interface validation failure
        interface_route = respx.get("https://bam.example.com/api/v2/interfaces/99999").mock(
            return_value=httpx.Response(404, json={"error": "Not Found"})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        with pytest.raises(ResourceNotFoundError):
            await client.resolve_interface_string("99999")

        assert interface_route.called


@pytest.mark.asyncio
async def test_resolve_interface_string_server_name() -> None:
    """Test resolving server name to interface ID."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock server lookup
        respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 12345, "name": "test-server"}]})
        )

        # Mock interfaces lookup
        respx.get("https://bam.example.com/api/v2/servers/12345/interfaces").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 67890, "name": "eth0"}]})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.resolve_interface_string("test-server")

        assert result == 67890


@pytest.mark.asyncio
async def test_resolve_interface_string_server_interface_format() -> None:
    """Test resolving server:interface format."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock server lookup
        respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 12345, "name": "test-server"}]})
        )

        # Mock interfaces lookup
        respx.get("https://bam.example.com/api/v2/servers/12345/interfaces").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": 67890, "name": "eth0"}, {"id": 67891, "name": "eth1"}]}
            )
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        result = await client.resolve_interface_string("test-server:eth1")

        assert result == 67891


@pytest.mark.asyncio
async def test_resolve_interface_string_server_not_found() -> None:
    """Test resolving interface when server is not found."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock empty server response
        respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await client.resolve_interface_string("non-existent-server")

        assert "Server not found: non-existent-server" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolve_interface_string_interface_not_found() -> None:
    """Test resolving interface when interface name is not found."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock server lookup
        respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 12345, "name": "test-server"}]})
        )

        # Mock interfaces lookup (different interface name)
        respx.get("https://bam.example.com/api/v2/servers/12345/interfaces").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 67890, "name": "eth0"}]})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await client.resolve_interface_string("test-server:non-existent-interface")

        assert "Interface not found: non-existent-interface on server test-server" in str(
            exc_info.value
        )


@pytest.mark.asyncio
async def test_resolve_interface_string_server_no_interfaces() -> None:
    """Test resolving server name when server has no interfaces."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock server lookup
        respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 12345, "name": "test-server"}]})
        )

        # Mock empty interfaces response
        respx.get("https://bam.example.com/api/v2/servers/12345/interfaces").mock(
            return_value=httpx.Response(200, json={"data": []})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        with pytest.raises(ResourceNotFoundError) as exc_info:
            await client.resolve_interface_string("test-server")

        assert "Server not found: test-server (has no interfaces)" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_server_by_name_api_error() -> None:
    """Test handling of API errors during server lookup."""
    with respx.mock:
        # Mock login
        respx.post("https://bam.example.com/api/v2/sessions").mock(
            return_value=httpx.Response(201, json={"id": 123, "username": "admin"})
        )

        # Mock API error
        respx.get("https://bam.example.com/api/v2/servers").mock(
            return_value=httpx.Response(500, json={"error": "Internal Server Error"})
        )

        config = BAMConfig(
            base_url="https://bam.example.com",
            username="admin",
            password="password",
            api_version="v2",
            timeout=30,
            verify_ssl=True,
            max_connections=50,
            max_keepalive=20,
        )
        client = BAMClient(config=config)

        with pytest.raises(BAMAPIError):
            await client.get_server_by_name("test-server")
