"""Operation handlers for different BAM resource types.

This module implements a strategy pattern for handling different resource types,
eliminating the large if/elif chains in the executor.

Each handler is responsible for:
1. CREATE operations
2. UPDATE operations
3. DELETE operations

Handlers are registered in HANDLER_REGISTRY for efficient dispatch.
"""

from typing import Any, Protocol

import structlog

from ..bam.client import BAMClient
from ..constants import CSV_TO_BAM_TYPE_MAP
from ..models.operations import Operation
from ..models.results import OperationResult
from ..utils.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError

logger = structlog.get_logger(__name__)


class OperationHandler(Protocol):
    """Protocol for operation handlers.

    All handlers must implement these three methods for the three
    basic CRUD operations.

    Note on Return Types:
        The create() method may return either:
        - dict[str, Any]: API response containing 'id' key (most handlers)
        - OperationResult: For handlers needing rich error handling (DNS records)

        The executor handles both return types transparently. See
        OperationExecutor._execute_create() for details.
    """

    async def create(
        self, client: BAMClient, operation: Operation
    ) -> dict[str, Any] | OperationResult:
        """Handle CREATE operation.

        Args:
            client: BAM client instance
            operation: Operation to execute

        Returns:
            Either:
            - Dictionary containing created resource data (must include 'id')
            - OperationResult with success=True and resource_id set

        Raises:
            ValueError: For validation errors
            BAMAPIError: For API errors
        """
        ...

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Handle UPDATE operation.

        Handlers implement updates using one of three approaches:

        1. **Raise NotImplementedError**: For immutable resources where updates
           are not supported by the BAM API (e.g., TagHandler, ResourceTagHandler,
           DeviceAddressHandler). Users must delete and recreate.

        2. **Call _update_generic_entity()**: For resources using the standard
           PATCH /resource/{id} endpoint with properties payload (e.g., DNSZoneHandler,
           HostRecordHandler, AliasRecordHandler).

        3. **Explicit entity update**: For resources requiring custom update logic
           (e.g., IPv4BlockHandler, IPv4NetworkHandler calling update_entity_by_id
           with type-specific handling).

        Args:
            client: BAM client instance
            operation: Operation to execute

        Returns:
            Dictionary containing updated resource data

        Raises:
            NotImplementedError: If updates are not supported for this resource type
            ValueError: For validation errors
            BAMAPIError: For API errors
        """
        ...

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Handle DELETE operation.

        Args:
            client: BAM client instance
            operation: Operation to execute
            allow_dangerous_operations: Allow deletion of protected resources

        Raises:
            ValueError: For validation errors
            BAMAPIError: For API errors
        """
        ...


class BaseHandler:
    """Base class with common functionality for all handlers."""

    # Use centralized type mapping from constants module
    # Maps CSV object types (snake_case) to BAM API types (PascalCase)
    _TYPE_MAPPING = CSV_TO_BAM_TYPE_MAP

    def _get_bam_type(self, object_type: str) -> str:
        """
        Convert CSV object type to BAM API type name.

        Returns the mapped type if found, otherwise returns the input unchanged.
        This allows for future object types without requiring explicit mapping.
        """
        return self._TYPE_MAPPING.get(object_type, object_type)

    async def _update_generic_entity(
        self, client: BAMClient, operation: Operation
    ) -> dict[str, Any]:
        """Update generic entity using mapped resource type."""
        bam_type = self._get_bam_type(operation.object_type)
        properties = operation.payload.get("properties", {})

        # Add name if present in payload but not in properties
        if "name" in operation.payload and "name" not in properties:
            properties["name"] = operation.payload["name"]

        return await client.update_entity_by_id(operation.resource_id, bam_type, properties)

    def _get_required_payload_id(self, operation: Operation, key: str) -> int:
        """Get required ID from operation payload.

        Args:
            operation: Operation containing payload
            key: Key to look up in payload

        Returns:
            Required ID value

        Raises:
            ValueError: If ID is missing or invalid
        """
        value = operation.payload.get(key)
        if not value:
            raise ValueError(
                f"Missing required {key} for {operation.object_type} in row {operation.row_id}"
            )

        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Invalid {key} '{value}' for {operation.object_type} in row {operation.row_id}"
            ) from e

    def _get_optional_attr(self, operation: Operation, attr_name: str, default: Any = None) -> Any:
        """Get optional attribute from CSV row.

        Args:
            operation: Operation containing CSV row
            attr_name: Attribute name to get
            default: Default value if attribute is missing

        Returns:
            Attribute value or default
        """
        return getattr(operation.csv_row, attr_name, default)


class IPv4BlockHandler(BaseHandler):
    """Handler for IPv4 blocks - top-level IP containers in configurations."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """
        Create IPv4 block within a configuration.

        Key Details:
        - Blocks are top-level containers that cannot overlap in IP space
        - CIDR must be unique within the configuration
        - Parent configuration must exist and be accessible
        """
        config_id = self._get_required_payload_id(operation, "config_id")

        cidr = self._get_optional_attr(operation, "cidr")
        name = self._get_optional_attr(operation, "name", "")
        properties = operation.payload.get("properties", {})
        location = operation.payload.get("location")
        parent_id = operation.payload.get("block_id")

        return await client.create_ip4_block(
            config_id=config_id,
            cidr=cidr,
            name=name,
            properties=properties,
            location=location,
            parent_id=parent_id,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv4 block properties (name and custom fields only)."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv4Block", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """
        Delete IPv4 block.

        Safety Note:
        - Deleting a block also deletes all networks, addresses, and records within it
        - This is a destructive operation that requires explicit permission
        - By default, this operation is blocked for safety
        """
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv4Block",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class IPv4NetworkHandler(BaseHandler):
    """Handler for IPv4 networks - subnets contained within blocks."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """
        Create IPv4 network within a block.

        Key Details:
        - Networks must be fully contained within their parent block
        - Networks within a block cannot overlap each other
        - Parent block must exist and be large enough to contain the network
        """
        block_id = self._get_required_payload_id(operation, "block_id")

        cidr = self._get_optional_attr(operation, "cidr")
        name = self._get_optional_attr(operation, "name", "")
        properties = operation.payload.get("properties", {})
        location = operation.payload.get("location")

        return await client.create_ip4_network(
            block_id=block_id,
            cidr=cidr,
            name=name,
            properties=properties,
            location=location,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv4 network."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv4Network", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv4 network."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv4Network",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class IPv4GroupHandler(BaseHandler):
    """Handler for IPv4 groups - logical groupings of IP addresses within networks."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """
        Create IPv4 group within a network.

        Key Details:
        - IP groups define a range of addresses within a network
        - Range can be specified as IP addresses, offset/size, or offset/percentage
        - Parent network must exist and contain the specified range
        """
        network_id = self._get_required_payload_id(operation, "network_id")

        name = self._get_optional_attr(operation, "name")
        range_spec = self._get_optional_attr(operation, "range")
        properties = operation.payload.get("properties", {})

        if not name:
            raise ValueError(f"Missing required name for IP group in row {operation.row_id}")
        if not range_spec:
            raise ValueError(f"Missing required range for IP group in row {operation.row_id}")

        return await client.create_ip4_group(
            network_id=network_id,
            name=name,
            range=range_spec,
            user_defined_fields=properties if properties else None,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv4 group."""
        name = self._get_optional_attr(operation, "name")
        range_spec = self._get_optional_attr(operation, "range")
        properties = operation.payload.get("properties")

        return await client.update_ip4_group(
            ip_group_id=operation.resource_id,
            name=name,
            range=range_spec,
            user_defined_fields=properties,
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv4 group."""
        await client.delete_ip4_group(operation.resource_id)


class IPv4AddressHandler(BaseHandler):
    """Handler for IPv4 addresses."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create IPv4 address."""
        network_id = self._get_required_payload_id(operation, "network_id")

        address = self._get_optional_attr(operation, "address")
        name = self._get_optional_attr(operation, "name")
        mac = self._get_optional_attr(operation, "mac")
        state = self._get_optional_attr(operation, "state")
        properties = operation.payload.get("properties", {})

        # Add DHCP reservation state to properties if specified

        return await client.create_ip4_address(
            network_id=network_id,
            address=address,
            name=name,
            mac=mac,
            state=state or "STATIC",
            properties=properties,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv4 address."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv4Address", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv4 address."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv4Address",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class IPv6BlockHandler(BaseHandler):
    """Handler for IPv6 blocks - top-level IPv6 containers in configurations."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """
        Create IPv6 block within a configuration.

        IPv6 blocks follow same pattern as IPv4 blocks.
        CIDR must be unique within the configuration.
        Typical prefix lengths: /32, /48.
        """
        config_id = self._get_required_payload_id(operation, "config_id")

        cidr = self._get_optional_attr(operation, "cidr")
        name = self._get_optional_attr(operation, "name", "")
        properties = operation.payload.get("properties", {})
        location = operation.payload.get("location")
        parent_id = operation.payload.get("block_id")

        if parent_id is None:
            # Default to "Global Unicast Address Space" (2000::/3) if no parent specified
            try:
                parent_block = await client.get_ip6_block_by_cidr_in_config(config_id, "2000::/3")
                parent_id = parent_block["id"]
                logger.info(
                    "No parent specified for IPv6 Block, defaulting to Global Unicast parent",
                    parent_id=parent_id,
                    config_id=config_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to lookup default IPv6 parent (2000::/3)",
                    config_id=config_id,
                    error=str(e),
                )

        return await client.create_ip6_block(
            config_id=config_id,
            cidr=cidr,
            name=name,
            properties=properties,
            location=location,
            parent_id=parent_id,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv6 block properties (name and custom fields only)."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv6Block", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv6 block (destructive operation requiring explicit permission)."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv6Block",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class IPv6NetworkHandler(BaseHandler):
    """Handler for IPv6 networks - subnets contained within blocks."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """
        Create IPv6 network within a block.

        Networks must be fully contained within their parent block.
        Typical prefix length: /64 (standard IPv6 subnet size).
        """
        block_id = self._get_required_payload_id(operation, "block_id")

        cidr = self._get_optional_attr(operation, "cidr")
        name = self._get_optional_attr(operation, "name", "")
        properties = operation.payload.get("properties", {})
        location = operation.payload.get("location")

        return await client.create_ip6_network(
            block_id=block_id,
            cidr=cidr,
            name=name,
            properties=properties,
            location=location,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv6 network."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv6Network", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv6 network."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv6Network",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class IPv6AddressHandler(BaseHandler):
    """Handler for IPv6 addresses."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """
        Create IPv6 address.

        MAC addresses supported (SLAAC-derived EUI-64 format).
        Valid states: STATIC, DHCP_RESERVED (no RESERVED/GATEWAY for IPv6).
        """
        network_id = self._get_required_payload_id(operation, "network_id")

        address = self._get_optional_attr(operation, "address")
        name = self._get_optional_attr(operation, "name")
        mac = self._get_optional_attr(operation, "mac")
        state = self._get_optional_attr(operation, "state")
        properties = operation.payload.get("properties", {})

        return await client.create_ip6_address(
            network_id=network_id,
            address=address,
            name=name,
            mac=mac,
            state=state or "STATIC",
            properties=properties,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv6 address."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv6Address", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv6 address."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv6Address",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class IPv6DHCPRangeHandler(BaseHandler):
    """Handler for IPv6 DHCP ranges."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """
        Create IPv6 DHCP range.

        DHCPv6 uses different mechanism than DHCPv4 (stateful vs stateless).
        Range format: 2001:db8::100-2001:db8::200.
        """
        network_id = self._get_required_payload_id(operation, "network_id")

        name = self._get_optional_attr(operation, "name")
        dhcp_range = self._get_optional_attr(operation, "range")
        split_around_static_addresses = self._get_optional_attr(
            operation, "split_around_static_addresses", False
        )
        low_water_mark = self._get_optional_attr(operation, "low_water_mark")
        high_water_mark = self._get_optional_attr(operation, "high_water_mark")

        return await client.create_ipv6_dhcp_range(
            config_id=operation.payload.get("config_id"),
            network_id=network_id,
            name=name,
            dhcp_range=dhcp_range,
            split_around_static_addresses=split_around_static_addresses,
            low_water_mark=low_water_mark,
            high_water_mark=high_water_mark,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv6 DHCP range."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv6DHCPRange", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv6 DHCP range."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv6DHCPRange",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class IPv4DHCPRangeHandler(BaseHandler):
    """Handler for IPv4 DHCP ranges."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create IPv4 DHCP range."""
        network_id = self._get_required_payload_id(operation, "network_id")

        name = self._get_optional_attr(operation, "name")
        dhcp_range = self._get_optional_attr(operation, "range")
        split_around_static_addresses = self._get_optional_attr(
            operation, "split_around_static_addresses", False
        )
        low_water_mark = self._get_optional_attr(operation, "low_water_mark")
        high_water_mark = self._get_optional_attr(operation, "high_water_mark")

        return await client.create_ipv4_dhcp_range(
            config_id=operation.payload.get("config_id"),
            network_id=network_id,
            name=name,
            dhcp_range=dhcp_range,
            split_around_static_addresses=split_around_static_addresses,
            low_water_mark=low_water_mark,
            high_water_mark=high_water_mark,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update IPv4 DHCP range."""
        return await client.update_entity_by_id(
            operation.resource_id, "IPv4DHCPRange", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete IPv4 DHCP range."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "IPv4DHCPRange",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class DHCPDeploymentRoleHandler(BaseHandler):
    """Handler for DHCP deployment roles."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create DHCP deployment role.

        This handler supports flexible parent assignment (Network or Block) and
        Resolves interface names to IDs and assigns `PRIMARY` type to the first
        interface and `SECONDARY` type to all subsequent interfaces for failover.

        The `interfaces` payload field can be a pipe-separated string of interface
        names (e.g., "server1:eth0|server2:eth0") which will be parsed and
        converted to the API-compatible list format with appropriate role types.
        """
        # Determine parent type and ID
        network_id = operation.payload.get("network_id")
        block_id = operation.payload.get("block_id")

        if network_id:
            parent_id = network_id
            parent_type = "networks"
        elif block_id:
            parent_id = block_id
            parent_type = "blocks"
        else:
            raise ValueError(
                f"Missing parent ID (network_id or block_id) in payload for DHCP deployment role in row {operation.row_id}"
            )

        name = self._get_optional_attr(operation, "name")
        role_type = self._get_optional_attr(operation, "role_type")
        server_group = self._get_optional_attr(operation, "server_group")
        server_group_id = self._get_optional_attr(operation, "server_group_id")
        interfaces = self._get_optional_attr(operation, "interfaces")

        # Parse interfaces from CSV format to API format using server name resolution
        api_interfaces = []
        if interfaces:
            interface_list = operation.csv_row.get_interface_list()
            for idx, interface_str in enumerate(interface_list):
                try:
                    # Use the client method to resolve interface string to ID
                    interface_id = await client.resolve_interface_string(interface_str)

                    # First interface is PRIMARY, subsequent are SECONDARY
                    role_interface_type = "PRIMARY" if idx == 0 else "SECONDARY"

                    api_interfaces.append(
                        {
                            "id": interface_id,
                            "type": "NetworkInterface",
                            "deploymentRoleInterfaceType": role_interface_type,
                        }
                    )
                except (ValueError, ResourceNotFoundError) as e:
                    raise ValueError(
                        f"Failed to resolve interface '{interface_str}' for DHCP deployment role in row {operation.row_id}: {str(e)}"
                    ) from e

        # Build kwargs dict to only include non-None values
        # The 'interfaces' argument is optional in the client method and should
        # only be passed if we have resolved interfaces to avoid API errors.
        kwargs = {
            "parent_id": parent_id,
            "parent_type": parent_type,
            "name": name,
            "role_type": role_type,
        }
        if api_interfaces:
            kwargs["interfaces"] = api_interfaces
        if server_group is not None:
            kwargs["server_group"] = server_group
        if server_group_id is not None:
            kwargs["server_group_id"] = server_group_id

        return await client.create_dhcp_deployment_role(**kwargs)

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update DHCP deployment role."""
        return await client.update_entity_by_id(
            operation.resource_id, "DHCPDeploymentRole", operation.payload
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete DHCP deployment role."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "DHCPDeploymentRole",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class DNSDeploymentRoleHandler(BaseHandler):
    """Handler for DNS deployment roles."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create DNS deployment role."""
        # Get parent information from payload
        zone_id = operation.payload.get("zone_id")
        network_id = operation.payload.get("network_id")
        block_id = operation.payload.get("block_id")

        # Determine parent type and ID
        if zone_id:
            parent_id = zone_id
            parent_type = "zones"
        elif network_id:
            parent_id = network_id
            parent_type = "networks"
        elif block_id:
            parent_id = block_id
            parent_type = "blocks"
        else:
            raise ValueError(
                f"Missing parent ID (zone_id, network_id, or block_id) in payload for DNS deployment role in row {operation.row_id}"
            )

        name = self._get_optional_attr(operation, "name")
        role_type = self._get_optional_attr(operation, "role_type")
        interfaces = self._get_optional_attr(operation, "interfaces")
        ns_record_ttl = self._get_optional_attr(operation, "ns_record_ttl")

        # Parse interfaces from CSV format to API format using server name resolution
        api_interfaces = []
        if interfaces:
            interface_list = operation.csv_row.get_interface_list()
            for interface_str in interface_list:
                try:
                    # Use the client method to resolve interface string to ID
                    interface_id = await client.resolve_interface_string(interface_str)
                    api_interfaces.append({"id": interface_id, "type": "NetworkInterface"})
                except (ValueError, ResourceNotFoundError) as e:
                    raise ValueError(
                        f"Failed to resolve interface '{interface_str}' for DNS deployment role in row {operation.row_id}: {str(e)}"
                    ) from e

        if not api_interfaces:
            raise ValueError(
                f"At least one valid interface must be provided for DNS deployment role in row {operation.row_id}"
            )

        # Build kwargs dict to only include non-None values
        kwargs = {
            "parent_id": parent_id,
            "parent_type": parent_type,
            "name": name,
            "role_type": role_type,
            "interfaces": api_interfaces,
        }
        if ns_record_ttl is not None:
            kwargs["ns_record_ttl"] = ns_record_ttl

        return await client.create_dns_deployment_role(**kwargs)

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update DNS deployment role."""
        return await client.update_entity_by_id(
            operation.resource_id,
            "DNSDeploymentRole",
            {
                "name": self._get_optional_attr(operation, "name"),
                "properties": operation.payload.get("properties", {}),
            },
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete DNS deployment role."""
        await client.delete_dns_deployment_role(deployment_role_id=operation.resource_id)


class DHCPv4ClientDeploymentOptionHandler(BaseHandler):
    """Handler for DHCPv4 client deployment options."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create DHCPv4 client deployment option."""
        network_id = self._get_required_payload_id(operation, "network_id")

        name = self._get_optional_attr(operation, "name")
        code = self._get_optional_attr(operation, "code")
        # Get value from payload (JSON-parsed) instead of csv_row (string)
        value = operation.payload.get("value")
        server_scope = self._get_optional_attr(operation, "server_scope")

        if not name:
            raise ValueError(
                f"Missing required name for DHCP client deployment option in row {operation.row_id}"
            )
        if not code:
            raise ValueError(
                f"Missing required code for DHCP client deployment option in row {operation.row_id}"
            )
        if value is None:
            raise ValueError(
                f"Missing required value for DHCP client deployment option in row {operation.row_id}"
            )

        # Build kwargs, only include server_scope if explicitly provided
        kwargs: dict[str, Any] = {
            "network_id": network_id,
            "name": name,
            "code": code,
            "value": value,
        }
        if server_scope is not None:
            kwargs["server_scope"] = server_scope

        return await client.create_dhcpv4_client_deployment_option(**kwargs)

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update DHCPv4 client deployment option."""
        name = self._get_optional_attr(operation, "name")
        # Get value from payload (JSON-parsed) instead of csv_row (string)
        value = operation.payload.get("value")
        server_scope = self._get_optional_attr(operation, "server_scope")

        # Build kwargs, only include server_scope if explicitly provided
        kwargs: dict[str, Any] = {"option_id": operation.resource_id}
        if name is not None:
            kwargs["name"] = name
        if value is not None:
            kwargs["value"] = value
        if server_scope is not None:
            kwargs["server_scope"] = server_scope

        return await client.update_dhcp_deployment_option(**kwargs)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete DHCPv4 client deployment option."""
        await client.delete_dhcp_deployment_option(option_id=operation.resource_id)


class DHCPv4ServiceDeploymentOptionHandler(BaseHandler):
    """Handler for DHCPv4 service deployment options."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create DHCPv4 service deployment option."""
        network_id = self._get_required_payload_id(operation, "network_id")

        name = self._get_optional_attr(operation, "name")
        code = self._get_optional_attr(operation, "code")
        # Get value from payload (JSON-parsed) instead of csv_row (string)
        value = operation.payload.get("value")
        server_scope = self._get_optional_attr(operation, "server_scope")

        if not name:
            raise ValueError(
                f"Missing required name for DHCP service deployment option in row {operation.row_id}"
            )
        if not code:
            raise ValueError(
                f"Missing required code for DHCP service deployment option in row {operation.row_id}"
            )
        if value is None:
            raise ValueError(
                f"Missing required value for DHCP service deployment option in row {operation.row_id}"
            )

        # Build kwargs, only include server_scope if explicitly provided
        kwargs: dict[str, Any] = {
            "network_id": network_id,
            "name": name,
            "code": code,
            "value": value,
        }
        if server_scope is not None:
            kwargs["server_scope"] = server_scope

        return await client.create_dhcpv4_service_deployment_option(**kwargs)

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update DHCPv4 service deployment option."""
        name = self._get_optional_attr(operation, "name")
        # Get value from payload (JSON-parsed) instead of csv_row (string)
        value = operation.payload.get("value")
        server_scope = self._get_optional_attr(operation, "server_scope")

        # Build kwargs, only include server_scope if explicitly provided
        kwargs: dict[str, Any] = {"option_id": operation.resource_id}
        if name is not None:
            kwargs["name"] = name
        if value is not None:
            kwargs["value"] = value
        if server_scope is not None:
            kwargs["server_scope"] = server_scope

        return await client.update_dhcp_deployment_option(**kwargs)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete DHCPv4 service deployment option."""
        await client.delete_dhcp_deployment_option(option_id=operation.resource_id)


class DNSZoneHandler(BaseHandler):
    """Handler for DNS zone operations."""

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create DNS zone."""
        payload = operation.payload
        view_id = payload.get("view_id")
        name = payload.get("name")
        properties = payload.get("properties", {})

        # Let ResourceAlreadyExistsError propagate to executor for handling
        return await client.create_dns_zone(view_id=view_id, name=name, properties=properties)

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update DNS zone."""
        # Zone updates are handled via generic entity update
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete DNS zone."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "DNSZone",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class HostRecordHandler(BaseHandler):
    """Handler for DNS host (A) record operations."""

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create host record."""
        payload = operation.payload
        zone_id = payload.get("zone_id")
        name = payload.get("name")

        # Convert pipe-separated addresses string to list
        raw_addresses = payload.get("addresses", "")
        if isinstance(raw_addresses, str):
            addresses = [addr.strip() for addr in raw_addresses.split("|") if addr.strip()]
        else:
            addresses = raw_addresses or []

        properties = payload.get("properties", {})

        # Get ptr option (create reverse PTR record)
        reverse_record = payload.get("ptr", False)
        if reverse_record is None:
            reverse_record = False

        try:
            result = await client.create_host_record(
                zone_id=zone_id,
                name=name,
                addresses=addresses,
                properties=properties,
                reverse_record=reverse_record,
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update host record."""
        # Host record updates are handled via generic entity update
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete host record."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "HostRecord",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class AliasRecordHandler(BaseHandler):
    """Handler for DNS alias (CNAME) record operations."""

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create alias record."""
        payload = operation.payload
        zone_id = payload.get("zone_id")
        name = payload.get("name")
        linked_record_name = payload.get("linked_record_name")
        properties = payload.get("properties", {})

        try:
            result = await client.create_alias_record(
                zone_id=zone_id,
                name=name,
                linked_record_name=linked_record_name,
                properties=properties,
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update alias record."""
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete alias record."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "AliasRecord",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class MXRecordHandler(BaseHandler):
    """Handler for DNS MX record operations."""

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create MX record."""
        payload = operation.payload
        zone_id = payload.get("zone_id")
        name = payload.get("name")
        exchange = payload.get("exchange")
        preference = payload.get("preference")
        properties = payload.get("properties", {})

        try:
            result = await client.create_mx_record(
                zone_id=zone_id,
                name=name,
                exchange=exchange,
                priority=preference,
                properties=properties,
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update MX record."""
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete MX record."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "MXRecord",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class TXTRecordHandler(BaseHandler):
    """Handler for DNS TXT record operations."""

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create TXT record."""
        payload = operation.payload
        zone_id = payload.get("zone_id")
        name = payload.get("name")
        text = payload.get("text")
        properties = payload.get("properties", {})

        try:
            result = await client.create_txt_record(
                zone_id=zone_id, name=name, text=text, properties=properties
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update TXT record."""
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete TXT record."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "TXTRecord",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class SRVRecordHandler(BaseHandler):
    """Handler for DNS SRV record operations."""

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create SRV record."""
        payload = operation.payload
        zone_id = payload.get("zone_id")
        name = payload.get("name")
        target = payload.get("target")
        port = payload.get("port")
        priority = payload.get("priority")
        weight = payload.get("weight")
        properties = payload.get("properties", {})

        try:
            result = await client.create_srv_record(
                zone_id=zone_id,
                name=name,
                target=target,
                port=port,
                priority=priority,
                weight=weight,
                properties=properties,
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update SRV record."""
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete SRV record."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "SRVRecord",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class ExternalHostRecordHandler(BaseHandler):
    """Handler for DNS external host record operations."""

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create external host record."""
        payload = operation.payload
        zone_id = payload.get("zone_id")
        view_id = payload.get("view_id")
        name = payload.get("name")
        properties = payload.get("properties", {})

        if not view_id:
            raise ValueError(
                f"Missing required view_id for external host record in row {operation.row_id}"
            )

        # Extract optional fields
        ttl = payload.get("ttl")
        comment = payload.get("comment") or payload.get("description")

        try:
            result = await client.create_external_host_record(
                zone_id=zone_id,
                view_id=view_id,
                name=name,
                ttl=ttl,
                comment=comment,
                properties=properties,
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update external host record."""
        # External host record updates are handled via generic entity update
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete external host record."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "ExternalHostRecord",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class GenericRecordHandler(BaseHandler):
    """Handler for DNS Generic record operations.

    Generic records allow creating DNS record types not natively supported,
    such as SSHFP, TLSA, CAA, DS, DNAME, etc.
    """

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create generic DNS record."""
        payload = operation.payload
        zone_id = payload.get("zone_id")
        name = payload.get("name")
        record_type = payload.get("record_type")
        rdata = payload.get("rdata")
        properties = payload.get("properties", {})

        if not record_type:
            raise ValueError(
                f"Missing required record_type for generic record in row {operation.row_id}"
            )
        if not rdata:
            raise ValueError(f"Missing required rdata for generic record in row {operation.row_id}")

        # Extract optional fields
        ttl = payload.get("ttl")
        comment = payload.get("comment") or payload.get("description")

        try:
            result = await client.create_generic_record(
                zone_id=zone_id,
                name=name,
                record_type=record_type,
                rdata=rdata,
                ttl=ttl,
                comment=comment,
                properties=properties,
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update generic record."""
        return await self._update_generic_entity(client, operation)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete generic record."""
        await client.delete_entity_by_id(
            operation.resource_id,
            "GenericRecord",
            allow_dangerous_operations=allow_dangerous_operations,
        )


class LocationHandler(BaseHandler):
    """Handler for Location operations.

    Locations in BlueCat are hierarchical and based on UN/LOCODE codes.
    Custom locations can be created under existing city-level locations.
    """

    async def create(self, client: BAMClient, operation: Operation) -> OperationResult:
        """Create a custom location under a parent location."""
        payload = operation.payload
        parent_location_id = payload.get("parent_location_id")
        code = payload.get("code")
        name = payload.get("name")

        if parent_location_id is None:
            # Root-level location creation is NOT supported by BAM API
            # Custom locations MUST be created under an existing UN/LOCODE location
            raise ValueError(
                f"Cannot create location in row {operation.row_id}: parent_code is required. "
                f"Root-level location creation is not supported by the BAM API. "
                f"Custom locations must be created under an existing UN/LOCODE location "
                f"(e.g., 'US NYC', 'GB LON', 'JP TYO')."
            )

        if not code:
            raise ValueError(f"Missing required code for location in row {operation.row_id}")

        # Auto-prepend parent code if required (BAM convention)
        if parent_location_id:
            parent_loc = await client.get_entity_by_id(parent_location_id, "Location")
            parent_code = parent_loc.get("code")
            if parent_code and not code.startswith(parent_code):
                # Check for explicit separator preference or just use space
                # User "US NYC" implies space separator.
                new_code = f"{parent_code} {code}"
                code = new_code

        if not name:
            raise ValueError(f"Missing required name for location in row {operation.row_id}")

        # Extract optional fields
        description = payload.get("description")
        localized_name = payload.get("localized_name")
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")

        try:
            result = await client.create_location(
                parent_location_id=parent_location_id,
                code=code,
                name=name,
                description=description,
                localized_name=localized_name,
                latitude=latitude,
                longitude=longitude,
            )
            return OperationResult(
                success=True,
                row_id=operation.row_id,
                resource_id=result["id"],
                operation=operation.operation_type,
            )
        except ResourceAlreadyExistsError:
            # Let 409 errors propagate to executor for lookup
            raise
        except Exception as e:
            return OperationResult(
                success=False,
                row_id=operation.row_id,
                resource_id=None,
                operation=operation.operation_type,
                error_message=str(e),
            )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a custom location."""
        payload = operation.payload
        location_id = operation.resource_id

        if not location_id:
            raise ValueError(f"Missing resource_id for location update in row {operation.row_id}")

        # Extract fields to update
        name = payload.get("name")
        description = payload.get("description")
        localized_name = payload.get("localized_name")
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")

        return await client.update_location(
            location_id=location_id,
            name=name,
            description=description,
            localized_name=localized_name,
            latitude=latitude,
            longitude=longitude,
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a custom location."""
        await client.delete_location(operation.resource_id)


class UDFDefinitionHandler(BaseHandler):
    """Handler for User-Defined Field (UDF) definition operations.

    UDF definitions describe custom metadata fields that can be attached
    to various BAM resource types.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a UDF definition."""
        payload = operation.payload

        name = payload.get("name")
        if not name:
            raise ValueError(
                f"Missing required 'name' for UDF definition in row {operation.row_id}"
            )

        field_type = payload.get("field_type")
        if not field_type:
            raise ValueError(
                f"Missing required 'field_type' for UDF definition in row {operation.row_id}"
            )

        # Parse pipe-separated resource types
        resource_types_str = payload.get("resource_types")
        resource_types: list[str] | None = None
        if resource_types_str:
            if resource_types_str == "*":
                resource_types = ["*"]
            else:
                resource_types = [rt.strip() for rt in resource_types_str.split("|") if rt.strip()]

        # Parse pipe-separated predefined values
        predefined_values_str = payload.get("predefined_values")
        predefined_values: list[str] | None = None
        if predefined_values_str:
            predefined_values = [v.strip() for v in predefined_values_str.split("|") if v.strip()]

        return await client.create_udf_definition(
            name=name,
            field_type=field_type,
            display_name=payload.get("display_name"),
            default_value=payload.get("default_value"),
            required=payload.get("required", False),
            resource_types=resource_types,
            predefined_values=predefined_values,
            hide_from_search=payload.get("hide_from_search", False),
            render_as_link=payload.get("render_as_link", False),
            validators=payload.get("validators"),
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a UDF definition."""
        udf_id = operation.resource_id
        if not udf_id:
            raise ValueError(f"Missing resource_id for UDF update in row {operation.row_id}")

        payload = operation.payload

        # Parse pipe-separated resource types if provided
        resource_types_str = payload.get("resource_types")
        resource_types: list[str] | None = None
        if resource_types_str:
            if resource_types_str == "*":
                resource_types = ["*"]
            else:
                resource_types = [rt.strip() for rt in resource_types_str.split("|") if rt.strip()]

        # Parse pipe-separated predefined values if provided
        predefined_values_str = payload.get("predefined_values")
        predefined_values: list[str] | None = None
        if predefined_values_str:
            predefined_values = [v.strip() for v in predefined_values_str.split("|") if v.strip()]

        return await client.update_udf_definition(
            udf_id=udf_id,
            display_name=payload.get("display_name"),
            default_value=payload.get("default_value"),
            required=payload.get("required"),
            resource_types=resource_types,
            predefined_values=predefined_values,
            hide_from_search=payload.get("hide_from_search"),
            render_as_link=payload.get("render_as_link"),
            validators=payload.get("validators"),
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a UDF definition."""
        await client.delete_udf_definition(operation.resource_id)


class UDLDefinitionHandler(BaseHandler):
    """Handler for User-Defined Link (UDL) definition operations.

    UDL definitions describe custom links that can be created between
    BAM resource types.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a UDL definition."""
        payload = operation.payload

        name = payload.get("name")
        if not name:
            raise ValueError(
                f"Missing required 'name' for UDL definition in row {operation.row_id}"
            )

        source_types_str = payload.get("source_types")
        if not source_types_str:
            raise ValueError(
                f"Missing required 'source_types' for UDL definition in row {operation.row_id}"
            )
        source_types = [t.strip() for t in source_types_str.split("|") if t.strip()]

        dest_types_str = payload.get("destination_types")
        if not dest_types_str:
            raise ValueError(
                f"Missing required 'destination_types' for UDL definition in row {operation.row_id}"
            )
        destination_types = [t.strip() for t in dest_types_str.split("|") if t.strip()]

        return await client.create_udl_definition(
            name=name,
            source_types=source_types,
            destination_types=destination_types,
            display_name=payload.get("display_name"),
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a UDL definition."""
        udl_id = operation.resource_id
        if not udl_id:
            raise ValueError(f"Missing resource_id for UDL update in row {operation.row_id}")

        payload = operation.payload

        # Parse source types if provided
        source_types_str = payload.get("source_types")
        source_types: list[str] | None = None
        if source_types_str:
            source_types = [t.strip() for t in source_types_str.split("|") if t.strip()]

        # Parse destination types if provided
        dest_types_str = payload.get("destination_types")
        destination_types: list[str] | None = None
        if dest_types_str:
            destination_types = [t.strip() for t in dest_types_str.split("|") if t.strip()]

        return await client.update_udl_definition(
            udl_id=udl_id,
            display_name=payload.get("display_name"),
            source_types=source_types,
            destination_types=destination_types,
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a UDL definition."""
        await client.delete_udl_definition(operation.resource_id)


class UserDefinedLinkHandler(BaseHandler):
    """Handler for User-Defined Link (UDL) instance operations.

    UDL instances are actual links between BAM resources that have been
    created using a UDL definition.
    """

    # Mapping from CSV object types to BAM API collection names
    RESOURCE_TYPE_TO_COLLECTION: dict[str, str] = {
        "ip4_address": "addresses",
        "ip6_address": "addresses",
        "ip4_block": "blocks",
        "ip6_block": "blocks",
        "ip4_network": "networks",
        "ip6_network": "networks",
        "device": "devices",
        "mac_address": "macAddresses",
        "mac_pool": "macPools",
        "dns_zone": "zones",
        "view": "views",
        "server": "servers",
        "server_group": "serverGroups",
        "ipv4_dhcp_range": "ranges",
        "ipv6_dhcp_range": "ranges",
    }

    def _get_collection_for_type(self, resource_type: str) -> str:
        """Map resource type to BAM API collection name."""
        collection = self.RESOURCE_TYPE_TO_COLLECTION.get(resource_type)
        if not collection:
            raise ValueError(f"Unsupported resource type for UDL: {resource_type}")
        return collection

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a user-defined link between two resources."""
        payload = operation.payload

        # Get UDL definition ID from resolved path
        udl_definition_id = payload.get("udl_definition_id")
        if not udl_definition_id:
            raise ValueError(f"Missing udl_definition_id for UDL in row {operation.row_id}")

        # Get source resource ID
        source_id = payload.get("source_id")
        if not source_id:
            raise ValueError(f"Missing source_id for UDL in row {operation.row_id}")

        # Get destination resource ID and type
        destination_id = payload.get("destination_id")
        if not destination_id:
            raise ValueError(f"Missing destination_id for UDL in row {operation.row_id}")

        destination_type = payload.get("destination_type")
        if not destination_type:
            raise ValueError(f"Missing destination_type for UDL in row {operation.row_id}")

        # Get collection name for destination resource
        collection = self._get_collection_for_type(destination_type)

        return await client.create_user_defined_link(
            collection=collection,
            destination_id=destination_id,
            source_id=source_id,
            udl_definition_id=udl_definition_id,
            description=payload.get("description"),
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a UDL - not supported, links are immutable."""
        raise ValueError("User-defined links cannot be updated. Delete and recreate instead.")

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a user-defined link."""
        payload = operation.payload

        link_id = operation.resource_id
        if not link_id:
            raise ValueError(f"Missing resource_id for UDL delete in row {operation.row_id}")

        # We need to know which resource the link is on to delete it
        destination_id = payload.get("destination_id")
        destination_type = payload.get("destination_type")

        if not destination_id or not destination_type:
            raise ValueError(
                f"Missing destination_id or destination_type for UDL delete "
                f"in row {operation.row_id}"
            )

        collection = self._get_collection_for_type(destination_type)
        await client.delete_user_defined_link(
            collection=collection,
            resource_id=destination_id,
            link_id=link_id,
        )


# -----------------------------------------------------------------------------
# MAC Pool Management Handlers
# -----------------------------------------------------------------------------


class MACPoolHandler(BaseHandler):
    """Handler for MAC Pool operations.

    MAC pools are used to group MAC addresses for DHCP allocation control.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a MAC pool."""
        payload = operation.payload

        config_id = payload.get("config_id")
        if not config_id:
            raise ValueError(f"Missing config_id for MAC pool in row {operation.row_id}")

        name = payload.get("name")
        if not name:
            raise ValueError(f"Missing name for MAC pool in row {operation.row_id}")

        pool_type = payload.get("pool_type", "MACPool")

        return await client.create_mac_pool(
            config_id=config_id,
            name=name,
            pool_type=pool_type,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a MAC pool."""
        pool_id = operation.resource_id
        if not pool_id:
            raise ValueError(f"Missing resource_id for MAC pool update in row {operation.row_id}")

        payload = operation.payload

        return await client.update_mac_pool(
            pool_id=pool_id,
            name=payload.get("name"),
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a MAC pool."""
        await client.delete_mac_pool(operation.resource_id)


class MACAddressHandler(BaseHandler):
    """Handler for MAC Address operations.

    MAC addresses can be registered globally or associated with a MAC pool.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a MAC address."""
        payload = operation.payload

        config_id = payload.get("config_id")
        if not config_id:
            raise ValueError(f"Missing config_id for MAC address in row {operation.row_id}")

        address = payload.get("mac_address")
        if not address:
            raise ValueError(f"Missing mac_address for MAC address in row {operation.row_id}")

        # Get optional MAC pool association
        pool_id = payload.get("pool_id")
        pool_type = payload.get("pool_type")

        return await client.create_mac_address(
            config_id=config_id,
            address=address,
            name=payload.get("name"),
            mac_pool_id=pool_id,
            mac_pool_type=pool_type,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a MAC address."""
        mac_id = operation.resource_id
        if not mac_id:
            raise ValueError(
                f"Missing resource_id for MAC address update in row {operation.row_id}"
            )

        payload = operation.payload

        # Get optional MAC pool association
        pool_id = payload.get("pool_id")
        pool_type = payload.get("pool_type")

        return await client.update_mac_address(
            mac_id=mac_id,
            name=payload.get("name"),
            mac_pool_id=pool_id,
            mac_pool_type=pool_type,
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a MAC address."""
        await client.delete_mac_address(operation.resource_id)


class TagGroupHandler(BaseHandler):
    """Handler for Tag Group operations.

    Tag groups organize tags into logical categories.
    Tags must be created within a tag group.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a tag group."""
        payload = operation.payload
        name = payload.get("name")

        if not name:
            raise ValueError(f"Missing required 'name' for tag group in row {operation.row_id}")

        return await client.create_tag_group(name=name)

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a tag group."""
        tag_group_id = operation.resource_id
        if not tag_group_id:
            raise ValueError(f"Missing resource_id for tag group update in row {operation.row_id}")

        payload = operation.payload
        name = payload.get("name")

        return await client.update_tag_group(tag_group_id=tag_group_id, name=name)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a tag group."""
        await client.delete_tag_group(operation.resource_id)


class TagHandler(BaseHandler):
    """Handler for Tag operations.

    Tags must be created within a tag group.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a tag within a tag group."""
        payload = operation.payload
        name = payload.get("name")
        tag_group_id = payload.get("tag_group_id")

        if not name:
            raise ValueError(f"Missing required 'name' for tag in row {operation.row_id}")

        if not tag_group_id:
            raise ValueError(
                f"Missing required 'tag_group_id' for tag in row {operation.row_id}. "
                "Tags must be created within a tag group."
            )

        return await client.create_tag(tag_group_id=tag_group_id, name=name)

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a tag - not supported, tags are immutable except deletion."""
        raise NotImplementedError(
            f"Tag update is not supported in row {operation.row_id}. "
            "Delete and recreate the tag instead."
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a tag."""
        await client.delete_tag(operation.resource_id)


class ResourceTagHandler(BaseHandler):
    """Handler for resource tagging operations.

    Associates or disassociates tags with resources like networks, blocks, zones.
    """

    # Mapping from object types to API resource paths
    _RESOURCE_TYPE_MAPPING = {
        "ip4_network": "networks",
        "ip4_block": "blocks",
        "ip6_network": "networks",
        "ip6_block": "blocks",
        "dns_zone": "zones",
        "ip4_address": "addresses",
        "ip6_address": "addresses",
    }

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Add a tag to a resource."""
        payload = operation.payload
        resource_id = payload.get("resource_id")
        resource_type = payload.get("resource_type")
        tag_id = payload.get("tag_id")

        if not resource_id:
            raise ValueError(
                f"Missing required 'resource_id' for resource tagging in row {operation.row_id}"
            )

        if not tag_id:
            raise ValueError(
                f"Missing required 'tag_id' for resource tagging in row {operation.row_id}"
            )

        api_resource_type = self._RESOURCE_TYPE_MAPPING.get(resource_type)
        if not api_resource_type:
            raise ValueError(
                f"Unsupported resource type '{resource_type}' for tagging in row {operation.row_id}. "
                f"Supported types: {', '.join(self._RESOURCE_TYPE_MAPPING.keys())}"
            )

        return await client.add_tag_to_resource(
            resource_type=api_resource_type, resource_id=resource_id, tag_id=tag_id
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a resource tag - not supported, use delete + create."""
        raise NotImplementedError(
            f"Resource tag update is not supported in row {operation.row_id}. "
            "Use delete + create instead."
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Remove a tag from a resource."""
        payload = operation.payload
        resource_id = payload.get("resource_id")
        resource_type = payload.get("resource_type")
        tag_id = payload.get("tag_id")

        if not resource_id or not tag_id:
            raise ValueError(
                f"Missing resource_id or tag_id for resource tag deletion in row {operation.row_id}"
            )

        api_resource_type = self._RESOURCE_TYPE_MAPPING.get(resource_type)
        if not api_resource_type:
            raise ValueError(
                f"Unsupported resource type '{resource_type}' for tagging in row {operation.row_id}"
            )

        await client.remove_tag_from_resource(
            resource_type=api_resource_type, resource_id=resource_id, tag_id=tag_id
        )


# -------------------------------------------------------------------------
# Device Management Handlers
# -------------------------------------------------------------------------


class DeviceTypeHandler(BaseHandler):
    """Handler for device type operations (GLOBAL resource).

    Device types are global resources (not per-configuration) that categorize
    devices, such as Cisco, Fortinet, F5, etc.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a device type."""
        name = self._get_optional_attr(operation, "name")
        udfs = operation.payload.get("user_defined_fields")

        return await client.create_device_type(
            name=name,
            user_defined_fields=udfs,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a device type."""
        type_id = operation.resource_id
        properties = operation.payload.get("properties", {})

        # Add name if present
        name = self._get_optional_attr(operation, "name")
        if name:
            properties["name"] = name

        return await client.update_entity_by_id(type_id, "DeviceType", properties)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a device type."""
        type_id = self._get_required_payload_id(operation, "device_type_id")
        await client.delete_device_type(type_id)


class DeviceSubtypeHandler(BaseHandler):
    """Handler for device subtype operations.

    Device subtypes are specific models within a device type,
    such as FortiGate-600E under Fortinet or Catalyst-9300 under Cisco.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a device subtype."""
        type_id = self._get_required_payload_id(operation, "device_type_id")
        name = self._get_optional_attr(operation, "name")
        udfs = operation.payload.get("user_defined_fields")

        return await client.create_device_subtype(
            type_id=type_id,
            name=name,
            user_defined_fields=udfs,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a device subtype."""
        subtype_id = operation.resource_id
        properties = operation.payload.get("properties", {})

        # Add name if present
        name = self._get_optional_attr(operation, "name")
        if name:
            properties["name"] = name

        return await client.update_entity_by_id(subtype_id, "DeviceSubtype", properties)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a device subtype."""
        subtype_id = self._get_required_payload_id(operation, "device_subtype_id")
        await client.delete_device_subtype(subtype_id)


class DeviceHandler(BaseHandler):
    """Handler for device operations.

    Devices represent physical or virtual network appliances such as
    firewalls, switches, routers, and servers.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a device."""
        config_id = self._get_required_payload_id(operation, "config_id")
        name = self._get_optional_attr(operation, "name")
        device_type_id = operation.payload.get("device_type_id")
        device_subtype_id = operation.payload.get("device_subtype_id")
        addresses = operation.payload.get("addresses")  # List of address dicts
        udfs = operation.payload.get("user_defined_fields")

        return await client.create_device(
            config_id=config_id,
            name=name,
            device_type_id=device_type_id,
            device_subtype_id=device_subtype_id,
            addresses=addresses,
            user_defined_fields=udfs,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update a device."""
        device_id = operation.resource_id
        payload: dict[str, Any] = {"type": "Device"}

        # Add name if present
        name = self._get_optional_attr(operation, "name")
        if name:
            payload["name"] = name

        # Add device type/subtype if present
        device_type_id = operation.payload.get("device_type_id")
        if device_type_id:
            payload["deviceType"] = {"type": "DeviceType", "id": device_type_id}

        device_subtype_id = operation.payload.get("device_subtype_id")
        if device_subtype_id:
            payload["deviceSubtype"] = {"type": "DeviceSubtype", "id": device_subtype_id}

        # Add addresses if present
        addresses = operation.payload.get("addresses")
        if addresses:
            payload["addresses"] = addresses

        # Add UDFs if present
        udfs = operation.payload.get("user_defined_fields")
        if udfs:
            payload["userDefinedFields"] = udfs

        return await client.update_device(device_id, payload)

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete a device."""
        device_id = self._get_required_payload_id(operation, "device_id")
        await client.delete_device(device_id)


class DeviceAddressHandler(BaseHandler):
    """Handler for device-address association operations.

    Links existing IP addresses to devices.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Link an address to a device."""
        device_id = self._get_required_payload_id(operation, "device_id")
        address_id = self._get_required_payload_id(operation, "address_id")
        address_type = operation.payload.get("address_type", "IPv4Address")

        return await client.link_address_to_device(
            device_id=device_id,
            address_id=address_id,
            address_type=address_type,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update not supported for device-address links.

        To change a link, delete the old one and create a new one.
        """
        raise NotImplementedError(
            "Device address update not supported. Use delete + create to change links."
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Unlink an address from a device."""
        device_id = self._get_required_payload_id(operation, "device_id")
        address_id = self._get_required_payload_id(operation, "address_id")

        await client.unlink_address_from_device(device_id, address_id)


class ACLHandler(BaseHandler):
    """Handler for ACL (Access Control List) operations.

    ACLs define which hosts are allowed or denied access to DNS services.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a new ACL."""
        config_id = self._get_required_payload_id(operation, "config_id")
        name = operation.payload.get("name")
        if not name:
            raise ValueError("ACL name is required")

        # Parse match elements from CSV row
        csv_row = operation.csv_row
        match_elements = []
        if hasattr(csv_row, "get_match_elements_list"):
            match_elements = csv_row.get_match_elements_list()
        elif "match_elements" in operation.payload:
            raw = operation.payload["match_elements"]
            if isinstance(raw, list):
                match_elements = raw
            elif raw:
                # Use pipe delimiter consistent with CSV model (ACLRow.get_match_elements_list)
                match_elements = [e.strip() for e in raw.split("|") if e.strip()]

        # Get UDFs
        udfs = self._get_optional_attr(operation, "user_defined_fields")

        return await client.create_acl(
            config_id=config_id,
            name=name,
            match_elements=match_elements,
            user_defined_fields=udfs,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update an existing ACL."""
        acl_id = self._get_required_payload_id(operation, "acl_id")
        name = operation.payload.get("name")
        if not name:
            raise ValueError("ACL name is required for update")

        # Parse match elements
        csv_row = operation.csv_row
        match_elements = []
        if hasattr(csv_row, "get_match_elements_list"):
            match_elements = csv_row.get_match_elements_list()
        elif "match_elements" in operation.payload:
            raw = operation.payload["match_elements"]
            if isinstance(raw, list):
                match_elements = raw
            elif raw:
                # Use pipe delimiter consistent with CSV model (ACLRow.get_match_elements_list)
                match_elements = [e.strip() for e in raw.split("|") if e.strip()]

        udfs = self._get_optional_attr(operation, "user_defined_fields")

        return await client.update_acl(
            acl_id=acl_id,
            name=name,
            match_elements=match_elements,
            user_defined_fields=udfs,
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete an ACL."""
        acl_id = self._get_required_payload_id(operation, "acl_id")
        await client.delete_acl(acl_id)


class AccessRightHandler(BaseHandler):
    """Handler for Access Right operations.

    Access rights control what actions users and groups can perform on
    specific resources or resource types within BlueCat Address Manager.
    """

    async def create(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Create a new access right.

        Resolves user/group by name and optionally the target resource,
        then creates the access right with the specified permissions.
        """
        csv_row = operation.csv_row

        # Get user scope info
        user_type = self._get_optional_attr(operation, "user_type")
        user_name = self._get_optional_attr(operation, "user_name")

        if not user_type or not user_name:
            raise ValueError(
                f"user_type and user_name are required for access_right in row {operation.row_id}"
            )

        # Resolve user or group ID
        if user_type == "user":
            user_scope_type = "User"
            user_data = await client.get_user_by_name(user_name)
            if not user_data:
                raise ValueError(f"User '{user_name}' not found in row {operation.row_id}")
            user_scope_id = user_data["id"]
        elif user_type == "group":
            user_scope_type = "UserGroup"
            group_data = await client.get_group_by_name(user_name)
            if not group_data:
                raise ValueError(f"Group '{user_name}' not found in row {operation.row_id}")
            user_scope_id = group_data["id"]
        else:
            raise ValueError(
                f"Invalid user_type '{user_type}' in row {operation.row_id}. "
                "Must be 'user' or 'group'"
            )

        # Get resource info (optional)
        resource_type = operation.payload.get("resource_type")
        resource_id = operation.payload.get("resource_id")

        # Get access settings
        default_access_level = self._get_optional_attr(operation, "default_access_level", "VIEW")
        deployments_allowed = self._get_optional_attr(operation, "deployments_allowed", False)
        quick_deployments_allowed = self._get_optional_attr(
            operation, "quick_deployments_allowed", False
        )
        selective_deployments_allowed = self._get_optional_attr(
            operation, "selective_deployments_allowed", False
        )
        workflow_level = self._get_optional_attr(operation, "workflow_level", "NONE")

        # Parse access overrides
        access_overrides = []
        if hasattr(csv_row, "get_access_overrides_list"):
            access_overrides = csv_row.get_access_overrides_list()

        return await client.create_access_right(
            user_scope_type=user_scope_type,
            user_scope_id=user_scope_id,
            default_access_level=default_access_level,
            resource_type=resource_type,
            resource_id=resource_id,
            deployments_allowed=bool(deployments_allowed),
            quick_deployments_allowed=bool(quick_deployments_allowed),
            selective_deployments_allowed=bool(selective_deployments_allowed),
            workflow_level=workflow_level,
            access_overrides=access_overrides,
        )

    async def update(self, client: BAMClient, operation: Operation) -> dict[str, Any]:
        """Update an existing access right.

        Note: The user scope and resource cannot be changed - only the
        access level and deployment settings can be updated.
        """
        access_right_id = self._get_required_payload_id(operation, "access_right_id")
        csv_row = operation.csv_row

        # Get access settings
        default_access_level = self._get_optional_attr(operation, "default_access_level", "VIEW")
        deployments_allowed = self._get_optional_attr(operation, "deployments_allowed", False)
        quick_deployments_allowed = self._get_optional_attr(
            operation, "quick_deployments_allowed", False
        )
        selective_deployments_allowed = self._get_optional_attr(
            operation, "selective_deployments_allowed", False
        )
        workflow_level = self._get_optional_attr(operation, "workflow_level", "NONE")

        # Parse access overrides
        access_overrides = []
        if hasattr(csv_row, "get_access_overrides_list"):
            access_overrides = csv_row.get_access_overrides_list()

        return await client.update_access_right(
            access_right_id=access_right_id,
            default_access_level=default_access_level,
            deployments_allowed=bool(deployments_allowed),
            quick_deployments_allowed=bool(quick_deployments_allowed),
            selective_deployments_allowed=bool(selective_deployments_allowed),
            workflow_level=workflow_level,
            access_overrides=access_overrides,
        )

    async def delete(
        self,
        client: BAMClient,
        operation: Operation,
        allow_dangerous_operations: bool = False,
    ) -> None:
        """Delete an access right."""
        access_right_id = self._get_required_payload_id(operation, "access_right_id")
        await client.delete_access_right(access_right_id)


# Registry of handlers for efficient dispatch
HANDLER_REGISTRY: dict[str, OperationHandler] = {
    "ip4_block": IPv4BlockHandler(),
    "ip4_group": IPv4GroupHandler(),
    "ip4_network": IPv4NetworkHandler(),
    "ip4_address": IPv4AddressHandler(),
    "ip6_block": IPv6BlockHandler(),
    "ip6_network": IPv6NetworkHandler(),
    "ip6_address": IPv6AddressHandler(),
    "ipv4_dhcp_range": IPv4DHCPRangeHandler(),
    "ipv6_dhcp_range": IPv6DHCPRangeHandler(),
    "dhcp_deployment_role": DHCPDeploymentRoleHandler(),
    "dns_deployment_role": DNSDeploymentRoleHandler(),
    "dhcpv4_client_deployment_option": DHCPv4ClientDeploymentOptionHandler(),
    "dhcpv4_service_deployment_option": DHCPv4ServiceDeploymentOptionHandler(),
    # DNS Record handlers
    "dns_zone": DNSZoneHandler(),
    "host_record": HostRecordHandler(),
    "alias_record": AliasRecordHandler(),
    "mx_record": MXRecordHandler(),
    "txt_record": TXTRecordHandler(),
    "srv_record": SRVRecordHandler(),
    "external_host_record": ExternalHostRecordHandler(),
    "generic_record": GenericRecordHandler(),
    # Location handler
    "location": LocationHandler(),
    # UDF/UDL handlers
    "udf_definition": UDFDefinitionHandler(),
    "udl_definition": UDLDefinitionHandler(),
    "user_defined_link": UserDefinedLinkHandler(),
    # MAC Pool/Address handlers
    "mac_pool": MACPoolHandler(),
    "mac_address": MACAddressHandler(),
    # Tag handlers
    "tag_group": TagGroupHandler(),
    "tag": TagHandler(),
    "resource_tag": ResourceTagHandler(),
    # Device handlers
    "device_type": DeviceTypeHandler(),
    "device_subtype": DeviceSubtypeHandler(),
    "device": DeviceHandler(),
    "device_address": DeviceAddressHandler(),
    # ACL handlers
    "acl": ACLHandler(),
    # Access Right handlers
    "access_right": AccessRightHandler(),
    # Aliases for compatibility
    "block": IPv4BlockHandler(),
    "network": IPv4NetworkHandler(),
    "address": IPv4AddressHandler(),
}


def get_handler(object_type: str) -> OperationHandler:
    """Get handler for object type.

    Args:
        object_type: BAM object type (e.g., "ip4_block", "ip4_network")

    Returns:
        Handler instance for the object type

    Raises:
        ValueError: If no handler is registered for the object type
    """
    handler = HANDLER_REGISTRY.get(object_type)
    if not handler:
        raise ValueError(f"No handler registered for object type: {object_type}")
    return handler


def register_handler(object_type: str, handler: OperationHandler) -> None:
    """Register a new handler for an object type.

    This allows extending the system with new resource types.

    Args:
        object_type: BAM object type to register handler for
        handler: Handler instance to register
    """
    HANDLER_REGISTRY[object_type] = handler


def get_supported_object_types() -> list[str]:
    """Get list of supported object types.

    Returns:
        List of object type strings that have registered handlers
    """
    return list(HANDLER_REGISTRY.keys())
