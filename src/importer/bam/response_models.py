"""Pydantic models for BAM REST API v2 responses.

This module provides response validation models for critical BAM API paths,
improving error detection and resilience to API changes.

Design Principles:
- Graceful degradation: extra="allow" for unknown fields
- Backward compatibility: Field aliases for renamed fields
- Optional validation: Models can be used selectively for critical paths
- Type safety: Enables IDE autocomplete and static analysis

Usage:
    # Validate authentication response
    auth_data = response.json()
    validated = AuthenticationResponse.model_validate(auth_data)
    token = validated.apiToken

    # Validate resource creation
    resource_data = response.json()
    validated = BAMResourceResponse.model_validate(resource_data)
    resource_id = validated.id

    # Validate paginated responses
    page_data = response.json()
    validated = PaginatedResponse.model_validate(page_data)
    items = validated.data
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class AuthenticationResponse(BaseModel):
    """Response from POST /api/v2/sessions (authentication endpoint).

    Authentication returns a session token and basic auth credentials
    that must be used in subsequent API requests.

    Attributes:
        apiToken: Session token for API access
        basicAuthenticationCredentials: Base64 encoded credentials for Basic auth
    """

    apiToken: str = Field(..., description="Session token for API authentication")
    basicAuthenticationCredentials: str = Field(
        ..., description="Base64 encoded Basic auth credentials"
    )

    # Allow additional fields for forward compatibility
    model_config = {"extra": "allow"}


class HALLinks(BaseModel):
    """HAL+JSON _links structure for navigation.

    BlueCat API v2 uses HAL (Hypertext Application Language) for
    hypermedia responses with navigation links.

    Attributes:
        self: Current resource URL
        next: Next page URL (for pagination)
        prev: Previous page URL (for pagination)
        collection: Collection URL
    """

    self_link: dict[str, str] | str | None = Field(
        None, alias="self", description="Link to current resource"
    )
    next: dict[str, str] | str | None = Field(None, description="Link to next page")
    prev: dict[str, str] | str | None = Field(None, description="Link to previous page")
    collection: dict[str, str] | str | None = Field(None, description="Link to collection")

    model_config = {"extra": "allow", "populate_by_name": True}

    def get_next_href(self) -> str | None:
        """Extract next page URL from link structure.

        Returns:
            URL string or None if no next page
        """
        if self.next is None:
            return None
        if isinstance(self.next, dict):
            return self.next.get("href")
        return self.next


class BAMResourceResponse(BaseModel):
    """Response from resource creation/retrieval endpoints.

    All BAM resources share a common structure with id, name, type,
    and properties fields. This model validates the core fields.

    Attributes:
        id: BAM resource ID (required for all resources)
        name: Resource name (optional, some resources don't have names)
        type: Resource type discriminator (e.g., "IPv4Block", "IPv4Network")
        properties: Additional resource properties and UDFs
    """

    id: int = Field(..., description="BAM resource ID", gt=0)
    name: str | None = Field(None, description="Resource name")
    type: str | None = Field(None, description="Resource type discriminator")
    properties: dict[str, Any] = Field(
        default_factory=dict, description="Resource properties and UDFs"
    )

    # Allow additional fields (e.g., range, address, absoluteName, etc.)
    model_config = {"extra": "allow"}

    @field_validator("id")
    @classmethod
    def validate_id_positive(cls, v: int) -> int:
        """Ensure ID is positive (BAM IDs start at 1)."""
        if v <= 0:
            raise ValueError(f"Resource ID must be positive, got {v}")
        return v


class PaginatedResponse(BaseModel):
    """Response from paginated list endpoints.

    BAM API v2 uses HAL+JSON format for paginated responses with
    data in either 'data' field or '_embedded' structure.

    Attributes:
        data: List of resources (common format)
        links: HAL navigation links (from _links in JSON)
        embedded: Embedded resources (from _embedded in JSON)
        count: Number of items in current page
        start: Starting index for pagination
        total: Total number of items across all pages
    """

    data: list[dict[str, Any]] = Field(default_factory=list, description="List of resources")
    links: HALLinks | None = Field(None, alias="_links", description="HAL navigation links")
    embedded: dict[str, Any] | None = Field(
        None, alias="_embedded", description="HAL embedded resources"
    )

    # Pagination metadata (optional, not all endpoints include these)
    count: int | None = Field(None, description="Items in current page", ge=0)
    start: int | None = Field(None, description="Starting index", ge=0)
    total: int | None = Field(None, description="Total items across all pages", ge=0)

    model_config = {"extra": "allow", "populate_by_name": True}

    def get_items(self, collection_name: str | None = None) -> list[dict[str, Any]]:
        """Extract items from response, handling both data and _embedded formats.

        Args:
            collection_name: Name of embedded collection (e.g., "blocks", "networks")

        Returns:
            List of resource dictionaries
        """
        # Try data field first (most common)
        if self.data:
            return self.data

        # Try _embedded structure
        if self.embedded:
            if collection_name and collection_name in self.embedded:
                result = self.embedded[collection_name]
                return result if isinstance(result, list) else []
            # Try common collection names
            for key in [
                "items",
                "blocks",
                "networks",
                "addresses",
                "zones",
                "resourceRecords",
                "ranges",
                "deploymentRoles",
                "views",
            ]:
                if key in self.embedded:
                    result = self.embedded[key]
                    return result if isinstance(result, list) else []

        return []

    def get_next_url(self) -> str | None:
        """Get next page URL from HAL links.

        Returns:
            Next page URL or None if no more pages
        """
        if self.links:
            return self.links.get_next_href()
        return None


class ErrorResponse(BaseModel):
    """Structured error response from BAM API.

    When API calls fail, BAM returns error information in JSON format.
    This model extracts the most relevant error details.

    Attributes:
        message: Primary error message
        error: Error type or category
        detail: Detailed error description
        code: Error code (if provided)
    """

    message: str | None = Field(None, description="Primary error message")
    error: str | None = Field(None, description="Error type or category")
    detail: str | None = Field(None, description="Detailed error description")
    code: str | int | None = Field(None, description="Error code")

    model_config = {"extra": "allow"}

    def get_message(self) -> str:
        """Get the most relevant error message.

        Returns:
            Error message (priority: message > error > detail)
        """
        return self.message or self.error or self.detail or "Unknown error"

    def get_full_message(self) -> str:
        """Get complete error message with all available details.

        Returns:
            Formatted error message with code and details
        """
        msg = self.get_message()

        if self.code:
            msg += f" (Code: {self.code})"

        # Add detail if distinct from primary message
        if self.detail and self.detail != self.message:
            # Truncate very long details
            detail = str(self.detail)
            if len(detail) > 200:
                detail = detail[:197] + "..."
            msg += f" - {detail}"

        return msg
