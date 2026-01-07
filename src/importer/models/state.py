"""Resource state models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StateLoadStrategy(str, Enum):
    """Strategy for loading resource state."""

    SHALLOW = "shallow"  # Object only, no relationships
    CHILDREN = "children"  # Include immediate children
    DEEP = "deep"  # Full subtree (use sparingly)


@dataclass
class ResourceState:
    """
    Current state of a BAM resource.

    Attributes:
        id: BAM resource ID
        type: Resource type (IP4Network, IP4Address, etc.)
        properties: Resource properties from BAM
        etag: ETag for optimistic locking
        version: Resource version for conflict detection
        children: Child resources (if loaded)
    """

    id: int
    type: str
    properties: dict[str, Any]
    etag: str | None = None
    version: int | None = None
    children: list["ResourceState"] | None = field(default_factory=list)

    def get_property(self, key: str, default: Any = None) -> Any:
        """
        Get a property value with optional default.

        Args:
            key: The property key to retrieve.
            default: The value to return if the key is not found (default: None).

        Returns:
            Any: The property value or the default.
        """
        return self.properties.get(key, default)

    def has_property(self, key: str) -> bool:
        """
        Check if a property exists.

        Args:
            key: The property key to check.

        Returns:
            bool: True if the property exists, False otherwise.
        """
        return key in self.properties


@dataclass
class ResourceIdentifier:
    """
    Identifier for looking up a resource.

    Can identify by ID, name, address, or other unique keys.

    Attributes:
        resource_type: The type of the resource.
        id: Optional BAM resource ID.
        name: Optional resource name.
        address: Optional IP address.
        path: Optional hierarchical path.
        parent_id: Optional parent resource ID.
        config_id: Optional configuration ID.
    """

    resource_type: str
    id: int | None = None
    name: str | None = None
    address: str | None = None
    path: str | None = None
    parent_id: int | None = None
    config_id: int | None = None

    @property
    def key(self) -> str:
        """
        Generate a unique key for this identifier.

        Returns:
            str: A string key representing the resource (e.g., "type:id", "type:address").
        """
        if self.id:
            return f"{self.resource_type}:{self.id}"
        elif self.address:
            return f"{self.resource_type}:{self.address}"
        elif self.name and self.parent_id:
            return f"{self.resource_type}:{self.parent_id}/{self.name}"
        elif self.path:
            return f"{self.resource_type}:{self.path}"
        else:
            return f"{self.resource_type}:unknown"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for API calls.

        Returns:
            dict[str, Any]: A dictionary containing non-None attributes.
        """
        return {
            k: v
            for k, v in {
                "id": self.id,
                "name": self.name,
                "address": self.address,
                "path": self.path,
                "parent_id": self.parent_id,
                "config_id": self.config_id,
            }.items()
            if v is not None
        }
