"""Tests for BAM API response validation models.

Tests validate that response models correctly handle:
- Valid API responses
- Invalid/malformed responses
- Missing required fields
- Unknown fields (graceful degradation)
- Helper methods for extracting data
"""

import pytest
from pydantic import ValidationError

from src.importer.bam.response_models import (
    AuthenticationResponse,
    BAMResourceResponse,
    ErrorResponse,
    HALLinks,
    PaginatedResponse,
)


class TestAuthenticationResponse:
    """Test AuthenticationResponse model validation."""

    def test_valid_auth_response(self):
        """Valid authentication response passes validation."""
        data = {
            "apiToken": "test-token-123",
            "basicAuthenticationCredentials": "dGVzdDp0ZXN0",
        }
        response = AuthenticationResponse.model_validate(data)
        assert response.apiToken == "test-token-123"
        assert response.basicAuthenticationCredentials == "dGVzdDp0ZXN0"

    def test_auth_response_with_extra_fields(self):
        """Extra fields are allowed for forward compatibility."""
        data = {
            "apiToken": "test-token-123",
            "basicAuthenticationCredentials": "dGVzdDp0ZXN0",
            "expiresIn": 3600,
            "newField": "future-value",
        }
        response = AuthenticationResponse.model_validate(data)
        assert response.apiToken == "test-token-123"

    def test_auth_response_missing_api_token(self):
        """Missing apiToken raises ValidationError."""
        data = {
            "basicAuthenticationCredentials": "dGVzdDp0ZXN0",
        }
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationResponse.model_validate(data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("apiToken",) for error in errors)

    def test_auth_response_missing_credentials(self):
        """Missing basicAuthenticationCredentials raises ValidationError."""
        data = {
            "apiToken": "test-token-123",
        }
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationResponse.model_validate(data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("basicAuthenticationCredentials",) for error in errors)


class TestBAMResourceResponse:
    """Test BAMResourceResponse model validation."""

    def test_valid_resource_response(self):
        """Valid resource response passes validation."""
        data = {
            "id": 12345,
            "name": "Test Block",
            "type": "IPv4Block",
            "properties": {"description": "Test description"},
        }
        response = BAMResourceResponse.model_validate(data)
        assert response.id == 12345
        assert response.name == "Test Block"
        assert response.type == "IPv4Block"

    def test_resource_response_minimal(self):
        """Minimal valid response with only id."""
        data = {"id": 999}
        response = BAMResourceResponse.model_validate(data)
        assert response.id == 999
        assert response.name is None
        assert response.type is None
        assert response.properties == {}

    def test_resource_response_with_extra_fields(self):
        """Extra fields like range, address are allowed."""
        data = {
            "id": 12345,
            "name": "Test Block",
            "type": "IPv4Block",
            "range": "10.0.0.0/8",
            "customField": "custom-value",
        }
        response = BAMResourceResponse.model_validate(data)
        assert response.id == 12345

    def test_resource_response_missing_id(self):
        """Missing id field raises ValidationError."""
        data = {
            "name": "Test Block",
            "type": "IPv4Block",
        }
        with pytest.raises(ValidationError) as exc_info:
            BAMResourceResponse.model_validate(data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("id",) for error in errors)

    def test_resource_response_negative_id(self):
        """Negative id raises ValidationError."""
        data = {"id": -1}
        with pytest.raises(ValidationError) as exc_info:
            BAMResourceResponse.model_validate(data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("id",) for error in errors)

    def test_resource_response_zero_id(self):
        """Zero id raises ValidationError."""
        data = {"id": 0}
        with pytest.raises(ValidationError) as exc_info:
            BAMResourceResponse.model_validate(data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("id",) for error in errors)


class TestPaginatedResponse:
    """Test PaginatedResponse model validation."""

    def test_valid_paginated_response_data_format(self):
        """Valid paginated response with data field."""
        data = {
            "data": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"},
            ],
            "_links": {"next": {"href": "/api/v2/blocks?start=2"}},
            "count": 2,
            "total": 10,
        }
        response = PaginatedResponse.model_validate(data)
        assert len(response.data) == 2
        assert response.count == 2
        assert response.total == 10

    def test_valid_paginated_response_embedded_format(self):
        """Valid paginated response with _embedded field."""
        data = {
            "_embedded": {
                "blocks": [
                    {"id": 1, "name": "Block 1"},
                    {"id": 2, "name": "Block 2"},
                ]
            },
            "_links": {"next": "/api/v2/blocks?start=2"},
        }
        response = PaginatedResponse.model_validate(data)
        assert response.data == []  # data field empty
        assert response.embedded is not None

    def test_paginated_response_empty(self):
        """Empty paginated response is valid."""
        data = {"data": []}
        response = PaginatedResponse.model_validate(data)
        assert response.data == []
        assert response.links is None

    def test_paginated_response_get_items_from_data(self):
        """get_items() extracts items from data field."""
        data = {
            "data": [{"id": 1}, {"id": 2}],
        }
        response = PaginatedResponse.model_validate(data)
        items = response.get_items()
        assert len(items) == 2
        assert items[0]["id"] == 1

    def test_paginated_response_get_items_from_embedded(self):
        """get_items() extracts items from _embedded field."""
        data = {
            "_embedded": {
                "blocks": [{"id": 1}, {"id": 2}],
            }
        }
        response = PaginatedResponse.model_validate(data)
        items = response.get_items("blocks")
        assert len(items) == 2

    def test_paginated_response_get_next_url(self):
        """get_next_url() extracts next page URL."""
        data = {
            "data": [],
            "_links": {"next": {"href": "/api/v2/blocks?start=10"}},
        }
        response = PaginatedResponse.model_validate(data)
        next_url = response.get_next_url()
        assert next_url == "/api/v2/blocks?start=10"

    def test_paginated_response_get_next_url_none(self):
        """get_next_url() returns None when no next link."""
        data = {"data": []}
        response = PaginatedResponse.model_validate(data)
        assert response.get_next_url() is None


class TestHALLinks:
    """Test HALLinks model validation."""

    def test_hal_links_dict_format(self):
        """Links in dict format with href."""
        data = {
            "self": {"href": "/api/v2/blocks/123"},
            "next": {"href": "/api/v2/blocks?start=10"},
        }
        links = HALLinks.model_validate(data)
        assert links.get_next_href() == "/api/v2/blocks?start=10"

    def test_hal_links_string_format(self):
        """Links in string format (direct URL)."""
        data = {
            "next": "/api/v2/blocks?start=10",
        }
        links = HALLinks.model_validate(data)
        assert links.get_next_href() == "/api/v2/blocks?start=10"

    def test_hal_links_no_next(self):
        """No next link returns None."""
        data = {"self": {"href": "/api/v2/blocks/123"}}
        links = HALLinks.model_validate(data)
        assert links.get_next_href() is None


class TestErrorResponse:
    """Test ErrorResponse model validation."""

    def test_error_response_full(self):
        """Error response with all fields."""
        data = {
            "message": "Resource not found",
            "error": "NOT_FOUND",
            "detail": "Block with CIDR 10.0.0.0/8 does not exist",
            "code": 404,
        }
        response = ErrorResponse.model_validate(data)
        assert response.get_message() == "Resource not found"
        assert "404" in response.get_full_message()

    def test_error_response_message_priority(self):
        """get_message() prioritizes message > error > detail."""
        data = {
            "message": "Primary message",
            "error": "Error type",
            "detail": "Detail info",
        }
        response = ErrorResponse.model_validate(data)
        assert response.get_message() == "Primary message"

    def test_error_response_only_error(self):
        """get_message() uses error if message missing."""
        data = {"error": "VALIDATION_ERROR"}
        response = ErrorResponse.model_validate(data)
        assert response.get_message() == "VALIDATION_ERROR"

    def test_error_response_only_detail(self):
        """get_message() uses detail if message and error missing."""
        data = {"detail": "Detailed error information"}
        response = ErrorResponse.model_validate(data)
        assert response.get_message() == "Detailed error information"

    def test_error_response_empty(self):
        """Empty error response returns default message."""
        data = {}
        response = ErrorResponse.model_validate(data)
        assert response.get_message() == "Unknown error"

    def test_error_response_full_message_with_code(self):
        """get_full_message() includes code and detail."""
        data = {
            "message": "Bad request",
            "code": "BAD_REQUEST",
            "detail": "Field 'name' is required",
        }
        response = ErrorResponse.model_validate(data)
        full_msg = response.get_full_message()
        assert "Bad request" in full_msg
        assert "BAD_REQUEST" in full_msg
        assert "Field 'name' is required" in full_msg

    def test_error_response_truncate_long_detail(self):
        """get_full_message() truncates very long details."""
        data = {
            "message": "Error",
            "detail": "x" * 300,  # Very long detail
        }
        response = ErrorResponse.model_validate(data)
        full_msg = response.get_full_message()
        assert len(full_msg) < 250  # Should be truncated
        assert "..." in full_msg
