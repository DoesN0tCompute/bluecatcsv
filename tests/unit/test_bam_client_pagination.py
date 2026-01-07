"""Tests for BAM client pagination functionality."""

import pytest

from src.importer.bam.client import MAX_PAGE_SIZE, BAMClient
from src.importer.config import BAMConfig


class TestBAMClientPagination:
    """Test BAMClient pagination methods."""

    @pytest.fixture
    def client(self):
        """Create a BAMClient for testing."""
        config = BAMConfig(
            base_url="https://test.example.com",
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
    async def test_get_all_pages_single_page(self, client, mocker):
        """Test pagination with a single page of results."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {
            "data": [
                {"id": 1, "name": "Network 1"},
                {"id": 2, "name": "Network 2"},
            ],
            "_links": {},  # No next link
        }

        result = await client.get_all_pages("blocks/123/networks")

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_pages_multiple_pages(self, client, mocker):
        """Test pagination across multiple pages."""
        mock_get = mocker.patch.object(client, "get")

        # First page
        page1 = {
            "data": [{"id": 1}, {"id": 2}],
            "_links": {"next": {"href": "/api/v2/blocks/123/networks?offset=2&limit=2"}},
        }
        # Second page
        page2 = {
            "data": [{"id": 3}, {"id": 4}],
            "_links": {"next": {"href": "/api/v2/blocks/123/networks?offset=4&limit=2"}},
        }
        # Third page (last)
        page3 = {"data": [{"id": 5}], "_links": {}}  # No next link

        mock_get.side_effect = [page1, page2, page3]

        result = await client.get_all_pages("blocks/123/networks", page_size=2)

        assert len(result) == 5
        assert [r["id"] for r in result] == [1, 2, 3, 4, 5]
        assert mock_get.call_count == 3

    @pytest.mark.asyncio
    async def test_get_all_pages_embedded_format(self, client, mocker):
        """Test pagination with _embedded HAL+JSON format."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {
            "_embedded": {
                "networks": [
                    {"id": 1, "name": "Network 1"},
                    {"id": 2, "name": "Network 2"},
                ]
            },
            "_links": {},
        }

        result = await client.get_all_pages("blocks/123/networks")

        assert len(result) == 2
        assert result[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_get_all_pages_max_items_limit(self, client, mocker):
        """Test pagination respects max_items limit."""
        mock_get = mocker.patch.object(client, "get")

        # First page with many items
        page1 = {
            "data": [{"id": i} for i in range(1, 51)],  # 50 items
            "_links": {"next": {"href": "/api/v2/blocks/123/networks?offset=50"}},
        }

        mock_get.return_value = page1

        result = await client.get_all_pages("blocks/123/networks", max_items=25)

        assert len(result) == 25
        assert mock_get.call_count == 1  # Should stop after first page

    @pytest.mark.asyncio
    async def test_get_all_pages_respects_max_page_size(self, client, mocker):
        """Test that page_size is capped at MAX_PAGE_SIZE."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {"data": [], "_links": {}}

        await client.get_all_pages("blocks/123/networks", page_size=5000)

        # Should be capped at MAX_PAGE_SIZE
        call_args = mock_get.call_args
        assert call_args[1]["params"]["limit"] == MAX_PAGE_SIZE

    @pytest.mark.asyncio
    async def test_get_all_pages_preserves_filter_params(self, client, mocker):
        """Test that filter parameters are preserved across pages."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {"data": [{"id": 1}], "_links": {}}

        await client.get_all_pages("blocks/123/networks", params={"filter": "type:'IPv4Network'"})

        call_args = mock_get.call_args
        assert call_args[1]["params"]["filter"] == "type:'IPv4Network'"

    @pytest.mark.asyncio
    async def test_extract_items_from_response_data_format(self, client):
        """Test extracting items from data field."""
        response = {"data": [{"id": 1}, {"id": 2}]}
        items = client._extract_items_from_response(response, "networks")
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_extract_items_from_response_embedded_format(self, client):
        """Test extracting items from _embedded field."""
        response = {"_embedded": {"networks": [{"id": 1}, {"id": 2}]}}
        items = client._extract_items_from_response(response, "blocks/123/networks")
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_extract_items_from_response_empty(self, client):
        """Test extracting items from empty response."""
        response = {}
        items = client._extract_items_from_response(response, "networks")
        assert len(items) == 0

    def test_get_collection_name_from_endpoint(self, client):
        """Test collection name extraction from endpoints."""
        assert client._get_collection_name_from_endpoint("networks") == "networks"
        assert client._get_collection_name_from_endpoint("blocks/123/networks") == "networks"
        assert (
            client._get_collection_name_from_endpoint("zones/456/resourceRecords")
            == "resourceRecords"
        )

    def test_get_next_page_url_dict_format(self, client):
        """Test next page URL extraction from dict format."""
        response = {"_links": {"next": {"href": "/api/v2/networks?offset=100"}}}
        url = client._get_next_page_url(response)
        assert url == "/api/v2/networks?offset=100"

    def test_get_next_page_url_string_format(self, client):
        """Test next page URL extraction from string format."""
        response = {"_links": {"next": "/api/v2/networks?offset=100"}}
        url = client._get_next_page_url(response)
        assert url == "/api/v2/networks?offset=100"

    def test_get_next_page_url_no_next(self, client):
        """Test next page URL when there's no next link."""
        response = {"_links": {}}
        url = client._get_next_page_url(response)
        assert url is None

    def test_parse_next_url_relative(self, client):
        """Test parsing relative next URL."""
        endpoint, params = client._parse_next_url("/api/v2/networks?offset=100&limit=50")
        assert endpoint == "networks"
        assert params.get("offset") == "100"
        assert params.get("limit") == "50"

    def test_parse_next_url_simple(self, client):
        """Test parsing simple next URL."""
        endpoint, params = client._parse_next_url("networks?offset=100")
        assert endpoint == "networks"
        assert params.get("offset") == "100"


class TestPaginatedMethods:
    """Test that collection methods use pagination correctly."""

    @pytest.fixture
    def client(self):
        """Create a BAMClient for testing."""
        config = BAMConfig(
            base_url="https://test.example.com",
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
    async def test_get_child_blocks_uses_pagination(self, client, mocker):
        """Test that get_child_blocks uses pagination by default."""
        mock_get_all_pages = mocker.patch.object(client, "get_all_pages")
        mock_get_all_pages.return_value = [{"id": 1}, {"id": 2}]

        result = await client.get_child_blocks(123)

        assert len(result) == 2
        mock_get_all_pages.assert_called_once()
        args = mock_get_all_pages.call_args
        assert args[0][0] == "blocks/123/blocks"

    @pytest.mark.asyncio
    async def test_get_child_blocks_no_pagination(self, client, mocker):
        """Test that get_child_blocks can skip pagination."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {"data": [{"id": 1}]}

        result = await client.get_child_blocks(123, paginate=False)

        assert len(result) == 1
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_child_networks_uses_pagination(self, client, mocker):
        """Test that get_child_networks uses pagination by default."""
        mock_get_all_pages = mocker.patch.object(client, "get_all_pages")
        mock_get_all_pages.return_value = [{"id": 1}, {"id": 2}]

        result = await client.get_child_networks(456)

        assert len(result) == 2
        mock_get_all_pages.assert_called_once()
        args = mock_get_all_pages.call_args
        assert args[0][0] == "blocks/456/networks"

    @pytest.mark.asyncio
    async def test_get_addresses_in_network_uses_pagination(self, client, mocker):
        """Test that get_addresses_in_network uses pagination by default."""
        mock_get_all_pages = mocker.patch.object(client, "get_all_pages")
        mock_get_all_pages.return_value = [{"id": 1}, {"id": 2}]

        result = await client.get_addresses_in_network(789)

        assert len(result) == 2
        mock_get_all_pages.assert_called_once()
        args = mock_get_all_pages.call_args
        assert args[0][0] == "networks/789/addresses"

    @pytest.mark.asyncio
    async def test_get_child_zones_uses_pagination(self, client, mocker):
        """Test that get_child_zones uses pagination by default."""
        mock_get_all_pages = mocker.patch.object(client, "get_all_pages")
        mock_get_all_pages.return_value = [{"id": 1}, {"id": 2}]

        result = await client.get_child_zones(111)

        assert len(result) == 2
        mock_get_all_pages.assert_called_once()
        args = mock_get_all_pages.call_args
        assert args[0][0] == "zones/111/zones"

    @pytest.mark.asyncio
    async def test_get_resource_records_in_zone_uses_pagination(self, client, mocker):
        """Test that get_resource_records_in_zone uses pagination by default."""
        mock_get_all_pages = mocker.patch.object(client, "get_all_pages")
        mock_get_all_pages.return_value = [{"id": 1}, {"id": 2}]

        result = await client.get_resource_records_in_zone(222)

        assert len(result) == 2
        mock_get_all_pages.assert_called_once()
        args = mock_get_all_pages.call_args
        assert args[0][0] == "zones/222/resourceRecords"

    @pytest.mark.asyncio
    async def test_get_ip4_blocks_uses_pagination(self, client, mocker):
        """Test that get_ip4_blocks uses pagination by default."""
        mock_get_all_pages = mocker.patch.object(client, "get_all_pages")
        mock_get_all_pages.return_value = [{"id": 1}, {"id": 2}]

        result = await client.get_ip4_blocks(100)

        assert len(result) == 2
        mock_get_all_pages.assert_called_once()
        args = mock_get_all_pages.call_args
        assert args[0][0] == "configurations/100/blocks"


class TestPaginationLargeDatasets:
    """Test pagination with large datasets (simulating real-world scenarios)."""

    @pytest.fixture
    def client(self):
        """Create a BAMClient for testing."""
        config = BAMConfig(
            base_url="https://test.example.com",
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
    async def test_pagination_500_networks(self, client, mocker):
        """Test fetching 500 networks across multiple pages."""
        mock_get = mocker.patch.object(client, "get")

        # Generate mock pages (100 items per page, 5 full pages for 500 items)
        pages = []
        for page_num in range(5):
            start_id = page_num * 100 + 1
            end_id = start_id + 100  # Each page has exactly 100 items
            page_data = [{"id": i, "name": f"Network {i}"} for i in range(start_id, end_id)]

            page = {"data": page_data}
            if page_num < 4:  # First 4 pages have next links
                page["_links"] = {"next": {"href": f"/api/v2/networks?offset={end_id}"}}
            else:
                page["_links"] = {}  # Last page has no next link

            pages.append(page)

        mock_get.side_effect = pages

        result = await client.get_all_pages("blocks/123/networks", page_size=100)

        assert len(result) == 500
        assert result[0]["id"] == 1
        assert result[499]["id"] == 500
        assert mock_get.call_count == 5

    @pytest.mark.asyncio
    async def test_pagination_empty_result(self, client, mocker):
        """Test pagination with empty result set."""
        mock_get = mocker.patch.object(client, "get")
        mock_get.return_value = {"data": [], "_links": {}}

        result = await client.get_all_pages("blocks/123/networks")

        assert len(result) == 0
        mock_get.assert_called_once()
