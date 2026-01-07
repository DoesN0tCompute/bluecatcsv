from unittest.mock import AsyncMock, MagicMock

import pytest
from importer.bam.client import BAMClient
from importer.config import BAMConfig


@pytest.fixture
def mock_client():
    config = BAMConfig(
        base_url="https://bam.example.com", username="test", password="password", verify_ssl=False
    )
    client = BAMClient(config)
    client._client = AsyncMock()
    client.authenticate = AsyncMock()  # Skip authentication
    return client


class TestBAMClientFiltering:

    def test_build_filter_string_equality(self, mock_client):
        filters = {"name": "test-network"}
        filter_str = mock_client.build_filter_string(filters)
        assert filter_str == "name:'test-network'"

    def test_build_filter_string_integers(self, mock_client):
        filters = {"id": 12345}
        filter_str = mock_client.build_filter_string(filters)
        assert filter_str == "id:12345"

    def test_build_filter_string_operators(self, mock_client):
        filters = {"name__like": "test*", "size__gt": 100, "status__ne": "active"}
        filter_str = mock_client.build_filter_string(filters)
        # Order is not guaranteed in dict, so check parts
        assert "name:like('test*')" in filter_str
        assert "size:gt(100)" in filter_str
        assert "status:ne('active')" in filter_str

    def test_build_filter_string_escaping(self, mock_client):
        filters = {"name": "test's network"}
        filter_str = mock_client.build_filter_string(filters)
        assert filter_str == "name:'test\\'s network'"

    def test_build_fields_string(self, mock_client):
        fields = ["id", "name", "properties.udf"]
        fields_str = mock_client.build_fields_string(fields)
        assert fields_str == "id,name,properties.udf"

    def test_build_fields_string_validation(self, mock_client):
        fields = ["id", "name", "invalid;drop tables"]
        fields_str = mock_client.build_fields_string(fields)
        assert fields_str == "id,name"

    @pytest.mark.asyncio
    async def test_get_all_pages_with_filter(self, mock_client):
        # Mock response setup
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_error = False
        mock_response.json.return_value = {"data": [{"id": 1, "name": "net1"}], "_links": {}}
        mock_response.get.side_effect = lambda k, d=None: mock_response.json.return_value.get(k, d)
        mock_client._client.request = AsyncMock(return_value=mock_response)

        # Call method
        await mock_client.get_all_pages(
            "test/endpoint", filter={"name": "net1"}, fields=["id", "name"], limit=10
        )

        # Verify call arguments
        call_args = mock_client._client.request.call_args
        assert call_args is not None
        params = call_args[1]["params"]

        assert params["filter"] == "name:'net1'"
        assert params["fields"] == "id,name"
        assert params["limit"] == 10

    @pytest.mark.asyncio
    async def test_get_ip4_blocks_filtering(self, mock_client):
        # Mocking get_all_pages to simply return what it was called with for verification
        mock_client.get_all_pages = AsyncMock(return_value=[])

        await mock_client.get_ip4_blocks(
            config_id=1, filter={"name__like": "block*"}, fields=["id", "range"], order_by="range"
        )

        mock_client.get_all_pages.assert_called_once()
        args, kwargs = mock_client.get_all_pages.call_args

        assert args[0] == "configurations/1/blocks"
        assert kwargs["filter"] == {"name__like": "block*"}
        assert kwargs["fields"] == ["id", "range"]
        assert kwargs["order_by"] == "range"

    @pytest.mark.asyncio
    async def test_single_page_filtering(self, mock_client):
        # Mocking raw get method
        mock_response = {"data": []}
        mock_client.get = AsyncMock(return_value=mock_response)

        await mock_client.get_ip4_blocks(
            config_id=1, paginate=False, filter={"name": "test"}, fields=["id"]
        )

        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args[1]
        params = call_kwargs["params"]

        assert params["filter"] == "name:'test'"
        assert params["fields"] == "id"
