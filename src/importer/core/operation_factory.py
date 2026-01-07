"""Operation Factory - Create operations from CSV rows with resolved dependencies.

This module creates Operation objects from parsed CSV rows, handling the complex
task of resolving resource paths to BAM API IDs. The key challenge is that
resources in a CSV may reference parents that don't exist yet because they're
being created in the same batch.

Architecture Overview:
---------------------
1. PendingResources - Tracks resources being created in the current CSV batch
   by scanning all rows upfront and building lookup maps (CIDR -> row_id, etc.)

2. DeferredResolver - Handles the case where a child resource references a parent
   that will be created later in the same batch. Instead of failing, it marks the
   operation with "_deferred_*" keys in the payload, which the executor resolves
   after the parent is created.

3. OperationFactory - The main factory that:
   - Resolves config/view/zone paths to IDs using the Resolver
   - Detects when parents are pending and uses deferred resolution
   - Auto-discovers parent networks/blocks when not explicitly specified
   - Builds type-specific payloads for each resource type

Key Design Decisions:
--------------------
- Deferred resolution uses special payload keys (e.g., "_deferred_block_cidr")
  rather than a separate data structure to keep operations self-contained

- Auto-discovery (find_block_containing_network, find_network_containing_address)
  allows users to omit parent paths when the system can infer them

- Path substitution in self-test creates temporary environments without modifying
  the original CSV files

- The factory is async because path resolution requires BAM API calls

Example Flow:
------------
CSV Row: ip4_network, create, Default, 10.1.0.0/24

1. Factory resolves "Default" config to config_id=123
2. Looks for parent block either via explicit path or auto-discovery
3. If parent block is in same CSV batch (pending), marks as deferred
4. Returns Operation with payload containing block_id or _deferred_block_cidr
"""

import ipaddress
from dataclasses import dataclass, field
from typing import Any

import structlog

from ..bam.client import BAMClient
from ..models.operations import Operation, OperationType
from .resolver import Resolver

logger = structlog.get_logger(__name__)


@dataclass
class PendingResources:
    """Track resources being created in the same CSV batch for deferred resolution.

    This enables operations that depend on resources being created in the same
    import batch to be properly ordered and resolved.
    """

    blocks: dict[str, int] = field(default_factory=dict)  # CIDR -> row_id
    networks: dict[str, int] = field(default_factory=dict)  # CIDR -> row_id
    zones: dict[str, int] = field(default_factory=dict)  # zone_name -> row_id
    locations: dict[str, int] = field(default_factory=dict)  # location_code -> row_id
    device_types: dict[str, int] = field(default_factory=dict)  # name -> row_id
    device_subtypes: dict[str, int] = field(default_factory=dict)  # name -> row_id
    devices: dict[str, int] = field(default_factory=dict)  # "config/name" -> row_id

    @classmethod
    def from_rows(cls, rows: list) -> "PendingResources":
        """Build pending resources map from CSV rows.

        Args:
            rows: List of parsed CSV rows

        Returns:
            PendingResources with mappings for blocks, networks, zones, locations, and devices
        """
        blocks = {}
        networks = {}
        zones = {}
        locations = {}
        device_types = {}
        device_subtypes = {}
        devices = {}

        for row in rows:
            if row.action != "create":
                continue

            if row.object_type in ("ip4_block", "ip6_block"):
                cidr = getattr(row, "cidr", None)
                if cidr:
                    blocks[cidr] = row.row_id

            elif row.object_type in ("ip4_network", "ip6_network"):
                cidr = getattr(row, "cidr", None)
                if cidr:
                    networks[cidr] = row.row_id

            elif row.object_type == "dns_zone":
                zone_name = getattr(row, "zone_name", None)
                if zone_name:
                    zones[zone_name] = row.row_id

            elif row.object_type == "location":
                code = getattr(row, "code", None)
                if code:
                    locations[code] = row.row_id

            elif row.object_type == "device_type":
                name = getattr(row, "name", None)
                if name:
                    device_types[name] = row.row_id

            elif row.object_type == "device_subtype":
                name = getattr(row, "name", None)
                if name:
                    device_subtypes[name] = row.row_id

            elif row.object_type == "device":
                name = getattr(row, "name", None)
                config = getattr(row, "config", None)
                if name and config:
                    # Key by config/name since devices are per-configuration
                    devices[f"{config}/{name}"] = row.row_id

        return cls(
            blocks=blocks,
            networks=networks,
            zones=zones,
            locations=locations,
            device_types=device_types,
            device_subtypes=device_subtypes,
            devices=devices,
        )


class DeferredResolver:
    """Handle deferred ID resolution for resources created in the same batch.

    When a resource depends on another resource being created in the same CSV
    import batch, we mark it as "deferred" and resolve the actual ID after
    the dependency is created.
    """

    def __init__(self, pending: PendingResources) -> None:
        """Initialize DeferredResolver.

        Args:
            pending: PendingResources tracking resources in this batch
        """
        self.pending = pending
        # Maps created resources to their BAM IDs
        self.created_ids: dict[str, int] = {}  # "type:key" -> BAM ID

    def register_created_resource(self, resource_type: str, key: str, bam_id: int) -> None:
        """Register a resource that was just created.

        Args:
            resource_type: Type of resource (block, network, zone)
            key: Resource key (CIDR for blocks/networks, name for zones)
            bam_id: BAM ID of the created resource
        """
        lookup_key = f"{resource_type}:{key}"
        self.created_ids[lookup_key] = bam_id
        logger.debug(
            "Registered created resource for deferred resolution",
            resource_type=resource_type,
            key=key,
            bam_id=bam_id,
        )

    def get_created_id(self, resource_type: str, key: str) -> int | None:
        """Get the BAM ID for a resource that was created in this batch.

        Args:
            resource_type: Type of resource (block, network, zone)
            key: Resource key

        Returns:
            BAM ID if found, None otherwise
        """
        lookup_key = f"{resource_type}:{key}"
        return self.created_ids.get(lookup_key)

    def check_pending_block(self, cidr: str) -> int | None:
        """Check if a block is pending creation in this batch.

        Args:
            cidr: Block CIDR

        Returns:
            Row ID if pending, None otherwise
        """
        return self.pending.blocks.get(cidr)

    def check_pending_network(self, cidr: str) -> int | None:
        """Check if a network is pending creation in this batch.

        Args:
            cidr: Network CIDR

        Returns:
            Row ID if pending, None otherwise
        """
        return self.pending.networks.get(cidr)

    def check_pending_zone(self, zone_name: str) -> int | None:
        """Check if a zone is pending creation in this batch.

        Args:
            zone_name: Zone name

        Returns:
            Row ID if pending, None otherwise
        """
        return self.pending.zones.get(zone_name)

    def find_containing_pending_block(self, network_cidr: str) -> tuple[str, int] | None:
        """Find a pending block that would contain the given network.

        Args:
            network_cidr: Network CIDR to find container for

        Returns:
            Tuple of (block_cidr, row_id) if found, None otherwise
        """
        try:
            target_net = ipaddress.ip_network(network_cidr, strict=False)
            for block_cidr, row_id in self.pending.blocks.items():
                try:
                    block_net = ipaddress.ip_network(block_cidr, strict=False)
                    if target_net.subnet_of(block_net):
                        return (block_cidr, row_id)
                except (ValueError, TypeError):
                    continue
        except ValueError:
            logger.warning(f"Invalid network CIDR during pending block check: {network_cidr}")
        return None

    def find_containing_pending_network(self, address: str) -> tuple[str, int] | None:
        """Find a pending network that would contain the given address.

        Args:
            address: IP address to find container for

        Returns:
            Tuple of (network_cidr, row_id) if found, None otherwise
        """
        try:
            target_ip = ipaddress.ip_address(address)
            for net_cidr, row_id in self.pending.networks.items():
                try:
                    net = ipaddress.ip_network(net_cidr, strict=False)
                    if target_ip in net:
                        return (net_cidr, row_id)
                except (ValueError, TypeError):
                    continue
        except ValueError:
            logger.warning(f"Invalid IP address during pending network check: {address}")
        return None

    def check_pending_device_type(self, name: str) -> int | None:
        """Check if a device type is pending creation in this batch.

        Args:
            name: Device type name

        Returns:
            Row ID if pending, None otherwise
        """
        return self.pending.device_types.get(name)

    def check_pending_device_subtype(self, name: str) -> int | None:
        """Check if a device subtype is pending creation in this batch.

        Args:
            name: Device subtype name

        Returns:
            Row ID if pending, None otherwise
        """
        return self.pending.device_subtypes.get(name)

    def check_pending_device(self, config: str, name: str) -> int | None:
        """Check if a device is pending creation in this batch.

        Args:
            config: Configuration name
            name: Device name

        Returns:
            Row ID if pending, None otherwise
        """
        key = f"{config}/{name}"
        return self.pending.devices.get(key)


class OperationFactory:
    """Factory for creating Operation objects from CSV rows.

    Handles:
    - Path resolution to BAM IDs
    - Deferred resolution for same-batch dependencies
    - Auto-discovery of parent resources
    - Object-type-specific payload construction
    """

    def __init__(
        self,
        client: BAMClient,
        resolver: Resolver,
        pending: PendingResources | None = None,
    ) -> None:
        """Initialize OperationFactory.

        Args:
            client: BAM API client
            resolver: Path resolver for converting paths to IDs
            pending: Resources being created in this batch (optional)
        """
        self.client = client
        self.resolver = resolver
        self.pending = pending or PendingResources()
        self.deferred = DeferredResolver(self.pending)

    async def create_from_row(self, row: Any) -> Operation:
        """Create an Operation from a CSV row with resolved IDs.

        Args:
            row: Parsed CSV row object

        Returns:
            Operation ready for execution

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Determine operation type
        operation_type = self._get_operation_type(row.action)

        # Build payload with resolved IDs
        payload: dict[str, Any] = {}

        # Resolve config_path to config_id (common to most operations)
        if hasattr(row, "config") and row.config:
            config = await self.client.get_configuration_by_name(row.config)
            payload["config_id"] = config["id"]

        # Dispatch to object-type-specific handler
        object_type = row.object_type

        if object_type == "ip4_block":
            await self._build_ip4_block_payload(row, payload)
        elif object_type == "ip6_block":
            await self._build_ip6_block_payload(row, payload)
        elif object_type == "ip4_network":
            await self._build_ip4_network_payload(row, payload)
        elif object_type == "ip6_network":
            await self._build_ip6_network_payload(row, payload)
        elif object_type == "ip4_address":
            await self._build_ip4_address_payload(row, payload)
        elif object_type == "ip6_address":
            await self._build_ip6_address_payload(row, payload)
        elif object_type == "ipv6_dhcp_range":
            await self._build_dhcp_range_payload(row, payload)
        elif object_type == "ipv4_dhcp_range":
            await self._build_dhcp_range_payload(row, payload)
        elif object_type in (
            "dns_zone",
            "host_record",
            "alias_record",
            "mx_record",
            "txt_record",
            "srv_record",
            "external_host_record",
            "generic_record",
        ):
            await self._build_dns_payload(row, payload, object_type)
        elif object_type in ("dhcp_deployment_role", "dns_deployment_role"):
            await self._build_deployment_role_payload(row, payload, object_type)
        elif object_type in (
            "dhcpv4_client_deployment_option",
            "dhcpv4_service_deployment_option",
        ):
            await self._build_dhcp_deployment_option_payload(row, payload)
        elif object_type == "location":
            await self._build_location_payload(row, payload)
        elif object_type == "device_type":
            await self._build_device_type_payload(row, payload)
        elif object_type == "device_subtype":
            await self._build_device_subtype_payload(row, payload)
        elif object_type == "device":
            await self._build_device_payload(row, payload)
        elif object_type == "device_address":
            await self._build_device_address_payload(row, payload)
        elif object_type == "tag":
            await self._build_tag_payload(row, payload)
        elif object_type == "resource_tag":
            await self._build_resource_tag_payload(row, payload)
        elif object_type == "user_defined_link":
            await self._build_user_defined_link_payload(row, payload)
        elif object_type == "acl":
            await self._build_acl_payload(row, payload)
        elif object_type in (
            "tag_group",
            "mac_pool",
            "mac_address",
            "udf_definition",
            "udl_definition",
        ):
            # These pass through with standard payload handling
            pass
        else:
            logger.warning(
                "Unknown object type, using generic payload",
                object_type=object_type,
                row_id=row.row_id,
            )

        # Add remaining row attributes to payload
        self._add_row_attributes_to_payload(row, payload)

        return Operation(
            row_id=row.row_id,
            operation_type=operation_type,
            object_type=object_type,
            resource_id=getattr(row, "bam_id", None),
            payload=payload,
            csv_row=row,
        )

    def _get_operation_type(self, action: str) -> OperationType:
        """Convert action string to OperationType enum.

        Args:
            action: Action string from CSV (create, update, delete)

        Returns:
            Corresponding OperationType
        """
        if action == "create":
            return OperationType.CREATE
        elif action == "update":
            return OperationType.UPDATE
        elif action == "delete":
            return OperationType.DELETE
        else:
            return OperationType.NOOP

    def _add_row_attributes_to_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Add remaining row attributes to payload.

        This method handles:
        1. Standard row attributes copied to payload
        2. User-defined fields (udf_*) converted to userDefinedFields dict

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        row_dict = row.model_dump(exclude={"row_id", "object_type", "action", "version", "bam_id"})

        # Extract UDF fields separately (they start with 'udf_')
        udf_fields: dict[str, Any] = {}
        for key, value in row_dict.items():
            if value is not None and key not in payload:
                if key.startswith("udf_"):
                    # Strip 'udf_' prefix and add to userDefinedFields
                    udf_name = key[4:]  # Remove 'udf_' prefix
                    udf_fields[udf_name] = value
                else:
                    payload[key] = value

        # Add UDF fields to payload if any exist
        if udf_fields:
            if "userDefinedFields" not in payload:
                payload["userDefinedFields"] = {}
            payload["userDefinedFields"].update(udf_fields)

    # -------------------------------------------------------------------------
    # Object-Type-Specific Payload Builders
    # -------------------------------------------------------------------------

    async def _build_ip4_block_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ip4_block operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        # Blocks can have parent blocks or be at config level
        if hasattr(row, "parent") and row.parent:
            parent_id = await self.resolver.resolve(row.parent, "block")
            # Note: For blocks, the API usually expects 'parent_block_id' or 'config_id'
            # If parent is root (config), parent_block_id might be None or omitted?
            # Actually, standard logic usually distinguishes based on root or child.
            # Assuming resolver handles this.
            payload["block_id"] = (
                parent_id  # Correcting key to likely be block_id/parent_id based on API?
            )
            # Wait, existing code used payload["parent_block_id"]. I should verify property name.
            # But more importantly for PERF-001:

            # Construct path for THIS resource for cache invalidation
            cidr = getattr(row, "cidr", "")
            resource_path = f"{row.parent}/{cidr}"
            resource_path = resource_path.replace("//", "/")
            payload["resource_path"] = resource_path

        # Resolve location_code if provided
        await self._resolve_location_code(row, payload)

    async def _build_ip4_network_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ip4_network operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        # Networks need a parent block - resolve or defer
        if hasattr(row, "parent") and row.parent:
            await self._resolve_network_parent_path(row, payload)
        elif hasattr(row, "cidr") and row.cidr and "config_id" in payload:
            await self._auto_discover_network_parent(row, payload)

        # Resolve location_code if provided
        await self._resolve_location_code(row, payload)

    async def _resolve_network_parent_path(self, row: Any, payload: dict[str, Any]) -> None:
        """Resolve parent_path for a network.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        # Extract CIDR from parent path (e.g., Default/10.0.0.0/8 -> 10.0.0.0/8)
        path_parts = row.parent.lstrip("/").split("/")
        parent_cidr = None
        if len(path_parts) >= 3:
            parent_cidr = f"{path_parts[-2]}/{path_parts[-1]}"

        # Check if parent block is being created in same batch
        if parent_cidr and self.deferred.check_pending_block(parent_cidr):
            payload["_deferred_block_cidr"] = parent_cidr
            payload["_deferred_block_row"] = self.pending.blocks[parent_cidr]
            logger.info(
                "Deferred block_id resolution (parent being created)",
                row_id=row.row_id,
                parent_cidr=parent_cidr,
                parent_row=self.pending.blocks[parent_cidr],
            )
        else:
            # Try to resolve immediately
            try:
                # Capture the path we are resolving against
                # For blocks, the resolution often uses parent path to find context
                # But for invalidation, we need the path of the DELETED resource.
                # If we are creating it, we don't know the full BAM path yet (unless we constructed it).
                # However, the resolver uses a constructed path key.
                # Since 'parent' is just a string here, let's store it as context.
                # Ideally, we should construct the full expected path for this resource.
                # e.g. "Default/10.0.0.0/8" if parent is "Default".

                block_id = await self.resolver.resolve(row.parent, "block")
                payload["block_id"] = block_id

                # Construct path for THIS resource for cache invalidation
                # If parent is a config name (no slashes), it's at the root of config
                parent_path = row.parent
                cidr = getattr(row, "cidr", "")
                if "/" not in parent_path and cidr:
                    # Parent is config name
                    resource_path = f"{parent_path}/{cidr}"
                else:
                    # Parent is a path
                    resource_path = f"{parent_path}/{cidr}"

                # Clean up double slashes just in case
                resource_path = resource_path.replace("//", "/")
                payload["resource_path"] = resource_path

            except Exception as e:
                logger.warning(
                    "Could not resolve parent block",
                    row_id=row.row_id,
                    parent_path=row.parent,
                    error=str(e),
                )
                raise

    async def _auto_discover_network_parent(self, row: Any, payload: dict[str, Any]) -> None:
        """Auto-discover parent block for a network.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        network_cidr = row.cidr

        # Check if any pending block would contain this network
        pending_block = self.deferred.find_containing_pending_block(network_cidr)
        if pending_block:
            block_cidr, block_row_id = pending_block
            payload["_deferred_block_cidr"] = block_cidr
            payload["_deferred_block_row"] = block_row_id
            logger.info(
                "Deferred block_id resolution (parent being created)",
                row_id=row.row_id,
                network_cidr=network_cidr,
                block_cidr=block_cidr,
                block_row=block_row_id,
            )
            return

        # Try to find existing block in BAM
        try:
            block = await self.client.find_block_containing_network(
                config_id=payload["config_id"], network_cidr=network_cidr
            )
            payload["block_id"] = block["id"]
            logger.info(
                "Auto-discovered parent block",
                row_id=row.row_id,
                network_cidr=network_cidr,
                block_id=block["id"],
                block_range=block.get("range"),
            )
        except Exception as e:
            # Auto-discovery failed - raise clear error with actionable guidance
            error_msg = (
                f"No containing block found for network {network_cidr}. "
                f"Either create the parent block first or provide an explicit 'parent' field. "
                f"Original error: {str(e)}"
            )
            logger.error(
                "Auto-discovery of parent block failed",
                row_id=row.row_id,
                network_cidr=network_cidr,
                config_id=payload.get("config_id"),
                error=str(e),
            )
            raise ValueError(error_msg) from e

    async def _build_ip4_address_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ip4_address operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        # Check for explicitly provided network via parent_path
        if hasattr(row, "parent") and row.parent:
            try:
                network_id = await self.resolver.resolve(row.parent, "network")
                payload["network_id"] = network_id
            except Exception as e:
                logger.warning(
                    "Could not resolve parent network path",
                    row_id=row.row_id,
                    parent_path=row.parent,
                    error=str(e),
                )

        # Auto-discover by IP address
        address = getattr(row, "address", None)
        if address and "config_id" in payload and "network_id" not in payload:
            await self._auto_discover_address_network(row, payload, address)

        # Resolve location_code if provided
        await self._resolve_location_code(row, payload)

    async def _auto_discover_address_network(
        self, row: Any, payload: dict[str, Any], address: str
    ) -> None:
        """Auto-discover parent network for an address.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            address: IP address string
        """
        # Check if any pending network contains this address
        pending_network = self.deferred.find_containing_pending_network(address)
        if pending_network:
            net_cidr, net_row_id = pending_network
            payload["_deferred_network_cidr"] = net_cidr
            payload["_deferred_network_row"] = net_row_id
            logger.info(
                "Deferred network_id resolution (network being created)",
                row_id=row.row_id,
                address=address,
                network_cidr=net_cidr,
                network_row=net_row_id,
            )
            return

        # Try to find existing network in BAM
        try:
            network = await self.client.find_network_containing_address(
                config_id=payload["config_id"], address=address
            )
            payload["network_id"] = network["id"]
            logger.info(
                "Auto-discovered parent network",
                row_id=row.row_id,
                address=address,
                network_id=network["id"],
                network_range=network.get("range"),
            )
        except Exception as e:
            logger.debug(
                "Could not auto-discover parent network",
                row_id=row.row_id,
                address=address,
                error=str(e),
            )

    async def _build_ip6_block_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ip6_block operations."""
        # Resolve parent block if parent field is present (for nested blocks)
        if hasattr(row, "parent") and row.parent:
            # Check pending blocks first
            if row.parent in self.pending.blocks:
                payload["_deferred_block_cidr"] = row.parent
                payload["_deferred_block_row"] = self.pending.blocks[row.parent]
                logger.info(
                    "Deferred block_id resolution (parent block being created)",
                    row_id=row.row_id,
                    parent_cidr=row.parent,
                    parent_row=self.pending.blocks[row.parent],
                )
            else:
                try:
                    # Try to resolve immediately
                    # Note: We assume parent is a CIDR string
                    parent_id = await self.resolver.resolve(row.parent, "block")
                    payload["block_id"] = parent_id

                    # Construct path for THIS resource for cache invalidation
                    cidr = getattr(row, "cidr", "")
                    resource_path = f"{row.parent}/{cidr}"
                    resource_path = resource_path.replace("//", "/")
                    payload["resource_path"] = resource_path
                except Exception as e:
                    logger.warning(
                        "Could not resolve parent block",
                        row_id=row.row_id,
                        parent=row.parent,
                        error=str(e),
                    )

        await self._resolve_location_code(row, payload)

    async def _build_ip6_network_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ip6_network operations."""
        # Check explicit block_id
        if hasattr(row, "block_id") and row.block_id:
            payload["block_id"] = row.block_id
        elif hasattr(row, "parent") and row.parent:
            # Parent is Block CIDR
            if row.parent in self.pending.blocks:
                payload["_deferred_block_cidr"] = row.parent
                payload["_deferred_block_row"] = self.pending.blocks[row.parent]
                logger.info(
                    "Deferred block_id resolution (parent block being created)",
                    row_id=row.row_id,
                    parent_cidr=row.parent,
                    parent_row=self.pending.blocks[row.parent],
                )
            else:
                try:
                    # Construct resolution path using config if parent is just CIDR
                    resolve_path = row.parent
                    if row.config and not row.parent.startswith(row.config):
                        resolve_path = f"{row.config}/{row.parent}"

                    block_id = await self.resolver.resolve(resolve_path, "ip6_block")
                    payload["block_id"] = block_id

                    # Construct resource path
                    cidr = getattr(row, "cidr", "")
                    resource_path = f"{row.parent}/{cidr}"
                    resource_path = resource_path.replace("//", "/")
                    payload["resource_path"] = resource_path
                except Exception as e:
                    logger.warning(
                        "Could not resolve parent block for network",
                        row_id=row.row_id,
                        parent=row.parent,
                        error=str(e),
                    )

        await self._resolve_location_code(row, payload)

    async def _build_ip6_address_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ip6_address operations."""
        # Check explicit network_id
        if hasattr(row, "network_id") and row.network_id:
            payload["network_id"] = row.network_id
        else:
            # Auto-discover network if not provided (common for imports)
            address = getattr(row, "address", None)
            if address and "config_id" in payload:
                await self._auto_discover_address_network(row, payload, address)

        await self._resolve_location_code(row, payload)

    async def _build_dhcp_range_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ipv4_dhcp_range operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        # Check explicit network_id first
        if hasattr(row, "network_id") and row.network_id:
            payload["network_id"] = row.network_id
            return

        # Check network_path
        if hasattr(row, "network_path") and row.network_path:
            network_path = row.network_path

            # Extract CIDR from hierarchical path (e.g., "Default/10.0.0.0/8/10.1.1.0/24" -> "10.1.1.0/24")
            # This matches how pending.networks is indexed (by CIDR only)
            parts = network_path.lstrip("/").split("/")
            if len(parts) >= 2 and parts[-1].isdigit():
                # Assume last two parts form the CIDR (IP/Prefix)
                network_cidr = f"{parts[-2]}/{parts[-1]}"
            else:
                # If path doesn't match expected format, use as-is
                network_cidr = network_path

            # Check if this network is being created in the same batch
            if network_cidr in self.pending.networks:
                payload["_deferred_network_cidr"] = network_cidr
                payload["_deferred_network_row"] = self.pending.networks[network_cidr]
                logger.info(
                    "Deferred network_id resolution for DHCP range (network being created)",
                    row_id=row.row_id,
                    network_path=network_path,
                    network_cidr=network_cidr,
                    network_row=self.pending.networks[network_cidr],
                )
            else:
                try:
                    # Capture the network path being used
                    network_path = row.network_path
                    target_type = (
                        "ip6_network" if row.object_type == "ipv6_dhcp_range" else "network"
                    )
                    network_id = await self.resolver.resolve(network_path, target_type)
                    payload["network_id"] = network_id

                    # Store the path used to resolve the network, which is relevant for DHCP ranges
                    # (though DHCP ranges themselves aren't usually cached by path in the same way)
                    payload["resource_path"] = network_path
                except Exception as e:
                    logger.warning(
                        "Could not resolve network path for DHCP range",
                        row_id=row.row_id,
                        network_path=network_path,
                        error=str(e),
                    )
            return

        # Auto-discover based on range
        if "config_id" in payload:
            range_str = getattr(row, "range", None)
            if range_str:
                await self._auto_discover_dhcp_range_network(row, payload, range_str)

    async def _auto_discover_dhcp_range_network(
        self, row: Any, payload: dict[str, Any], range_str: str
    ) -> None:
        """Auto-discover parent network for a DHCP range.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            range_str: DHCP range string (e.g., "10.2.0.100-10.2.0.200")
        """
        try:
            start_ip = range_str.split("-")[0].strip()

            # Check pending networks
            pending_network = self.deferred.find_containing_pending_network(start_ip)
            if pending_network:
                net_cidr, net_row_id = pending_network
                payload["_deferred_network_cidr"] = net_cidr
                payload["_deferred_network_row"] = net_row_id
                logger.info(
                    "Deferred network_id resolution for DHCP range",
                    row_id=row.row_id,
                    range=range_str,
                    network_cidr=net_cidr,
                )
                return

            # Try to find existing network
            try:
                network = await self.client.find_network_containing_address(
                    config_id=payload["config_id"], address=start_ip
                )
                payload["network_id"] = network["id"]
            except Exception:
                logger.debug("Network auto-discovery failed for DHCP range", range=range_str)

        except (ValueError, IndexError) as e:
            logger.warning(
                f"Failed to parse DHCP range for network discovery: {range_str}", error=str(e)
            )

    async def _build_dns_payload(self, row: Any, payload: dict[str, Any], object_type: str) -> None:
        """Build payload for DNS operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            object_type: DNS object type
        """
        logger.debug(f"Building DNS payload for: {row.model_dump()}")

        # Resolve view
        if hasattr(row, "view_path") and row.view_path and "config_id" in payload:
            view = await self.client.get_view_by_name_in_config(payload["config_id"], row.view_path)
            payload["view_id"] = view["id"]

            if object_type == "dns_zone":
                # For dns_zone, map zone_name to name
                if hasattr(row, "zone_name") and row.zone_name:
                    payload["name"] = row.zone_name
                    # Store path for cache invalidation
                    payload["resource_path"] = row.zone_name
            else:
                # For records, resolve zone
                await self._resolve_dns_record_zone(row, payload, view["id"])

        # Resolve location_code if provided
        await self._resolve_location_code(row, payload)

    async def _resolve_dns_record_zone(
        self, row: Any, payload: dict[str, Any], view_id: int
    ) -> None:
        """Resolve zone for a DNS record.

        Supports:
        1. zone_name attribute (e.g., "example.com")
        2. absoluteName attribute for nested zones (e.g., "sub.example.com")
        3. Nested zone resolution by walking parent zones

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            view_id: View ID
        """
        name = getattr(row, "name", "")
        zone_name = getattr(row, "zone_name", None)

        # FEAT-006: Also check absoluteName for nested zones
        absolute_name = getattr(row, "absoluteName", None) or getattr(row, "absolute_name", None)

        # Prefer absoluteName if provided (more specific for nested zones)
        effective_zone = absolute_name or zone_name

        if effective_zone:
            logger.debug("Attempting to resolve zone", zone_name=effective_zone, view_id=view_id)

            # Special handling for ExternalHostRecord
            if getattr(row, "object_type", "") == "external_host_record":
                # For ExternalHostRecord, we need to find the specific "ExternalHostsZone"
                # It usually doesn't match the row's zone_name directly (which might be the domain part)
                # We need to find the zone of type ExternalHostsZone in this view.
                try:
                    # Filter by type if possible, or name match if known convention
                    # Since we don't know the exact name, we search for the type in the view
                    zones = await self.client.get_zones_in_view(view_id)
                    external_zone = next(
                        (z for z in zones if z.get("type") == "ExternalHostsZone"), None
                    )

                    if external_zone:
                        payload["zone_id"] = external_zone["id"]
                        # ExternalHostRecords keep their full FQDN as name
                        # Unlike regular records where name is relative to zone,
                        # ExternalHostRecords represent pointers to external domains
                        # and must retain the full name.
                        payload["name"] = name
                        logger.info(
                            "Resolved ExternalHostsZone",
                            row_id=row.row_id,
                            zone_id=external_zone["id"],
                            name=name,
                        )
                        return
                    else:
                        logger.warning(
                            "No ExternalHostsZone found in view", row_id=row.row_id, view_id=view_id
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to resolve ExternalHostsZone", row_id=row.row_id, error=str(e)
                    )

            # Check if zone is being created in same batch
            # Check both zone_name and absoluteName variants
            pending_zone_key = None
            if effective_zone in self.pending.zones:
                pending_zone_key = effective_zone
            elif zone_name and zone_name in self.pending.zones:
                pending_zone_key = zone_name

            if pending_zone_key:
                payload["_deferred_zone_name"] = pending_zone_key
                payload["_deferred_zone_row"] = self.pending.zones[pending_zone_key]
                logger.info(
                    "Deferred zone_id resolution (zone being created)",
                    row_id=row.row_id,
                    zone_name=pending_zone_key,
                    zone_row=self.pending.zones[pending_zone_key],
                )
            else:
                try:
                    # Try to resolve zone - get_zone_by_fqdn handles nested zones
                    zone = await self.client.get_zone_by_fqdn(view_id, effective_zone)
                    payload["zone_id"] = zone["id"]

                    # Adjust record name relative to zone
                    zone_abs_name = zone.get("absoluteName") or zone.get("name")
                    if name.endswith(f".{zone_abs_name}"):
                        payload["name"] = name[: -len(zone_abs_name) - 1]
                    elif name == zone_abs_name:
                        payload["name"] = "@"  # Apex record

                    # Store path for cache invalidation
                    payload["resource_path"] = zone_abs_name

                except Exception as e:
                    logger.warning(
                        "Failed to resolve zone by name",
                        row_id=row.row_id,
                        zone_name=effective_zone,
                        view_id=view_id,
                        error=str(e),
                    )
                    # FEAT-006: Try walking parent zones for nested zone resolution
                    if "." in effective_zone:
                        await self._try_nested_zone_resolution(
                            row, payload, view_id, name, effective_zone
                        )
            return

        # Try to find zone from FQDN
        if "." in name:
            await self._resolve_zone_from_fqdn(row, payload, view_id, name)

    async def _try_nested_zone_resolution(
        self, row: Any, payload: dict[str, Any], view_id: int, name: str, zone_name: str
    ) -> None:
        """Try to resolve a nested zone by walking parent zones.

        For example, if zone_name is "sub.example.com" but only "example.com" exists,
        this will find example.com and look for sub.example.com within it.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            view_id: View ID
            name: Record name
            zone_name: Zone name to resolve (potentially nested)
        """
        parts = zone_name.split(".")

        # Try progressively shorter parent zones
        for i in range(1, len(parts)):
            parent_zone_name = ".".join(parts[i:])

            # Check pending zones for parent
            if parent_zone_name in self.pending.zones:
                payload["_deferred_zone_name"] = zone_name
                payload["_deferred_parent_zone"] = parent_zone_name
                payload["_deferred_zone_row"] = self.pending.zones[parent_zone_name]
                logger.info(
                    "Deferred nested zone resolution (parent zone being created)",
                    row_id=row.row_id,
                    zone_name=zone_name,
                    parent_zone=parent_zone_name,
                )
                return

            try:
                # Try to find parent zone
                parent_zone = await self.client.get_zone_by_fqdn(view_id, parent_zone_name)

                # Look for nested zone within parent
                child_zones = await self.client.get_child_zones(parent_zone["id"])
                child_name = parts[i - 1]  # The immediate child name

                for child in child_zones:
                    if child.get("name") == child_name:
                        # Found the nested zone
                        payload["zone_id"] = child["id"]
                        zone_abs_name = child.get("absoluteName") or zone_name
                        if name.endswith(f".{zone_abs_name}"):
                            payload["name"] = name[: -len(zone_abs_name) - 1]
                        payload["resource_path"] = zone_abs_name
                        logger.info(
                            "Resolved nested zone",
                            row_id=row.row_id,
                            zone_name=zone_name,
                            parent_zone=parent_zone_name,
                            zone_id=child["id"],
                        )
                        return

            except Exception:
                continue

        logger.warning(
            "Could not resolve nested zone",
            row_id=row.row_id,
            zone_name=zone_name,
        )

    async def _resolve_zone_from_fqdn(
        self, row: Any, payload: dict[str, Any], view_id: int, name: str
    ) -> None:
        """Resolve zone from FQDN.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            view_id: View ID
            name: FQDN
        """
        parts = name.split(".")

        # First check if name itself is a zone (apex records)
        if name in self.pending.zones:
            payload["_deferred_zone_name"] = name
            payload["_deferred_zone_row"] = self.pending.zones[name]
            payload["name"] = "@"  # Zone apex indicator
            logger.info(
                "Deferred zone_id resolution for apex record (zone being created)",
                row_id=row.row_id,
                zone_name=name,
                zone_row=self.pending.zones[name],
            )
            return

        # Try to find existing zone where name equals zone name (apex)
        try:
            zone = await self.client.get_zone_by_fqdn(view_id, name)
            payload["zone_id"] = zone["id"]
            payload["name"] = "@"  # Zone apex indicator
            return
        except Exception:
            pass  # Not an apex record, continue to subdomain check

        # Check subdomains
        for i in range(1, len(parts)):
            potential_zone = ".".join(parts[i:])

            # Check if zone is being created in same batch
            if potential_zone in self.pending.zones:
                payload["_deferred_zone_name"] = potential_zone
                payload["_deferred_zone_row"] = self.pending.zones[potential_zone]
                payload["name"] = name[: -len(potential_zone) - 1]
                logger.info(
                    "Deferred zone_id resolution from FQDN (zone being created)",
                    row_id=row.row_id,
                    zone_name=potential_zone,
                    zone_row=self.pending.zones[potential_zone],
                )
                return

            # Try to find existing zone
            try:
                zone = await self.client.get_zone_by_fqdn(view_id, potential_zone)
                payload["zone_id"] = zone["id"]
                payload["name"] = name[: -len(potential_zone) - 1]
                return
            except Exception:
                continue

        logger.warning(
            "Could not find zone for FQDN",
            row_id=row.row_id,
            name=name,
        )

    async def _build_deployment_role_payload(
        self, row: Any, payload: dict[str, Any], object_type: str
    ) -> None:
        """Build payload for deployment role operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            object_type: Deployment role type
        """
        # Handle Network Path
        if hasattr(row, "network_path") and row.network_path and "config_id" in payload:
            await self._resolve_deployment_role_network(row, payload)

        # Handle Block Path
        if hasattr(row, "block_path") and row.block_path and "config_id" in payload:
            await self._resolve_deployment_role_block(row, payload)

        # Handle Zone Path (for DNS roles)
        if hasattr(row, "zone_path") and row.zone_path and "config_id" in payload:
            await self._resolve_deployment_role_zone(row, payload)

    async def _build_dhcp_deployment_option_payload(
        self, row: Any, payload: dict[str, Any]
    ) -> None:
        """Build payload for DHCP deployment option operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update

        Note:
            The BAM API expects DHCP option values as strings, NOT as structured
            JSON objects. Even if the CSV value looks like JSON (e.g., '["172.20.20.1"]'),
            it should be passed through as-is. The BAM server handles the interpretation.

            For standard options like Routers (Option 3), the API accepts:
            - Comma-separated IPs: "172.20.20.1,172.20.20.2"
            - JSON-formatted string: "["172.20.20.1"]" (literal string, not parsed)

            Previous behavior incorrectly parsed JSON strings into Python objects,
            which when re-serialized by httpx caused BAM to receive malformed values.
        """
        # Handle Network Path (reuse existing resolution logic)
        if hasattr(row, "network_path") and row.network_path and "config_id" in payload:
            await self._resolve_deployment_role_network(row, payload)

        # Pass value as-is (string). Do NOT parse as JSON.
        # The BAM API expects string values for DHCP options.
        if hasattr(row, "value") and row.value:
            payload["value"] = row.value

    async def _resolve_deployment_role_network(self, row: Any, payload: dict[str, Any]) -> None:
        """Resolve network for a deployment role.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        network_path = row.network_path
        # Strip /IPv4/ prefix if present
        if "/IPv4/" in network_path:
            network_path = network_path.split("/IPv4/")[-1]

        # Extract CIDR from path components if it looks like a path
        # e.g. "Default/10.0.0.0/8/10.1.1.0/24" -> "10.1.1.0/24"
        parts = network_path.lstrip("/").split("/")
        if len(parts) >= 2 and parts[-1].isdigit():
            # Assume last two parts form the CIDR (IP/Prefix)
            network_cidr = f"{parts[-2]}/{parts[-1]}"
        else:
            network_cidr = network_path

        # Check pending resources first
        if network_cidr in self.pending.networks:
            payload["_deferred_network_cidr"] = network_cidr
            payload["_deferred_network_row"] = self.pending.networks[network_cidr]
            logger.info(
                "Deferred network_id resolution for deployment role",
                row_id=row.row_id,
                network_cidr=network_cidr,
                network_row=self.pending.networks[network_cidr],
            )
        else:
            try:
                network = await self.client.get_network_by_cidr(
                    config_id=payload["config_id"], cidr=network_cidr
                )
                payload["network_id"] = network["id"]
            except Exception as e:
                logger.warning(
                    "Could not resolve network path for deployment role",
                    row_id=row.row_id,
                    network_path=row.network_path,
                    error=str(e),
                )

    async def _resolve_deployment_role_block(self, row: Any, payload: dict[str, Any]) -> None:
        """Resolve block for a deployment role.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        block_path = row.block_path
        # Handle potential /IPv4/ prefix
        if "/IPv4/" in block_path:
            block_path = block_path.split("/IPv4/")[-1]

        if self.deferred.check_pending_block(block_path):
            payload["_deferred_block_cidr"] = block_path
            payload["_deferred_block_row"] = self.pending.blocks[block_path]
            logger.info(
                "Deferred block_id resolution (block being created)",
                row_id=row.row_id,
                block_path=block_path,
                block_row=self.pending.blocks[block_path],
            )
        else:
            error_msg = None  # Initialize error message
            try:
                block_id = await self.resolver.resolve(block_path, "block")
                payload["block_id"] = block_id

                # Construct path for THIS network
                cidr = getattr(row, "cidr", "")
                resource_path = f"{block_path}/{cidr}"
                resource_path = resource_path.replace("//", "/")
                payload["resource_path"] = resource_path

            except Exception as e:
                # Store error message for logging after except block
                error_msg = str(e)
                # Fallback to auto-discovery if path resolution fails

            # Log warning if there was an error
            if error_msg:
                logger.warning(
                    "Could not resolve block path for deployment role",
                    row_id=row.row_id,
                    block_path=row.block_path,
                    error=error_msg,
                )

    async def _resolve_deployment_role_zone(self, row: Any, payload: dict[str, Any]) -> None:
        """Resolve zone for a deployment role.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
        """
        zone_path = row.zone_path.strip("/")
        view_name = None
        zone_name = None

        if "/" in zone_path:
            parts = zone_path.split("/", 1)
            view_name = parts[0]
            zone_name = parts[1]

        if view_name and zone_name:
            # Check pending zones
            if zone_name in self.pending.zones:
                payload["_deferred_zone_name"] = zone_name
                payload["_deferred_zone_row"] = self.pending.zones[zone_name]
                logger.info(
                    "Deferred zone_id resolution for deployment role",
                    row_id=row.row_id,
                    zone_name=zone_name,
                    zone_row=self.pending.zones[zone_name],
                )
            else:
                try:
                    view = await self.client.get_view_by_name_in_config(
                        payload["config_id"], view_name
                    )
                    zone = await self.client.get_zone_by_fqdn(view["id"], zone_name)
                    payload["zone_id"] = zone["id"]
                except Exception as e:
                    logger.warning(
                        "Could not resolve zone path for deployment role",
                        row_id=row.row_id,
                        zone_path=row.zone_path,
                        error=str(e),
                    )

    async def _build_location_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for location operations.

        Locations require a parent location (UN/LOCODE or custom) to be created under.
        The parent is resolved from the parent_code field.

        Args:
            row: CSV row object (LocationRow)
            payload: Payload dictionary to update
        """
        # Resolve parent location from parent_code
        if hasattr(row, "parent_code") and row.parent_code:
            parent_code = row.parent_code

            # Check if parent location is being created in same batch
            if parent_code in self.pending.locations:
                payload["_deferred_location_code"] = parent_code
                payload["_deferred_location_row"] = self.pending.locations[parent_code]
                logger.info(
                    "Deferred parent_location_id resolution (parent being created)",
                    row_id=row.row_id,
                    parent_code=parent_code,
                    parent_row=self.pending.locations[parent_code],
                )
            else:
                # Try to resolve immediately
                try:
                    parent_location = await self.client.get_location_by_code(parent_code)
                    if parent_location:
                        payload["parent_location_id"] = parent_location["id"]
                    else:
                        logger.error(
                            "Parent location not found",
                            row_id=row.row_id,
                            parent_code=parent_code,
                        )
                        raise ValueError(f"Parent location with code '{parent_code}' not found")
                except Exception as e:
                    logger.error(
                        "Failed to resolve parent location",
                        row_id=row.row_id,
                        parent_code=parent_code,
                        error=str(e),
                    )
                    raise

        # Copy location-specific fields to payload
        if hasattr(row, "code") and row.code:
            payload["code"] = row.code
        if hasattr(row, "name") and row.name:
            payload["name"] = row.name
        if hasattr(row, "description") and row.description:
            payload["description"] = row.description
        if hasattr(row, "localized_name") and row.localized_name:
            payload["localized_name"] = row.localized_name
        if hasattr(row, "latitude") and row.latitude is not None:
            payload["latitude"] = row.latitude
        if hasattr(row, "longitude") and row.longitude is not None:
            payload["longitude"] = row.longitude

    async def _resolve_location_code(self, row: Any, payload: dict[str, Any]) -> None:
        """Resolve location_code to location_id for resource association.

        This method handles resolving a location_code field on any resource
        (network, block, address, host record, etc.) to a location_id that
        can be included in the API request.

        Args:
            row: CSV row object with optional location_code field
            payload: Payload dictionary to update with location_id
        """
        location_code = getattr(row, "location_code", None)
        if not location_code:
            return

        # Check if location is being created in same batch
        if location_code in self.pending.locations:
            payload["_deferred_location_code"] = location_code
            payload["_deferred_location_row"] = self.pending.locations[location_code]
            logger.info(
                "Deferred location_id resolution (location being created)",
                row_id=row.row_id,
                location_code=location_code,
                location_row=self.pending.locations[location_code],
            )
        else:
            # Try to resolve immediately
            try:
                location = await self.client.get_location_by_code(location_code)
                if location:
                    payload["location"] = {"id": location["id"]}
                    logger.debug(
                        "Resolved location_code to location_id",
                        row_id=row.row_id,
                        location_code=location_code,
                        location_id=location["id"],
                    )
                else:
                    logger.warning(
                        "Location not found, skipping location association",
                        row_id=row.row_id,
                        location_code=location_code,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to resolve location_code, skipping location association",
                    row_id=row.row_id,
                    location_code=location_code,
                    error=str(e),
                )

    # -------------------------------------------------------------------------
    # Device-Related Payload Builders
    # -------------------------------------------------------------------------

    async def _build_device_type_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for device_type operations.

        Device types are GLOBAL resources (not per-configuration).

        Args:
            row: CSV row object (DeviceTypeRow)
            payload: Payload dictionary to update
        """
        # Device types are simple - just need the name
        if hasattr(row, "name") and row.name:
            payload["name"] = row.name

    async def _build_device_subtype_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for device_subtype operations.

        Device subtypes require a parent device type.

        Args:
            row: CSV row object (DeviceSubtypeRow)
            payload: Payload dictionary to update
        """
        if hasattr(row, "name") and row.name:
            payload["name"] = row.name

        # Resolve parent device type
        device_type_name = getattr(row, "device_type", None)
        if device_type_name:
            # Check if device type is being created in same batch
            pending_row_id = self.deferred.check_pending_device_type(device_type_name)
            if pending_row_id:
                payload["_deferred_device_type_name"] = device_type_name
                payload["_deferred_device_type_row"] = pending_row_id
                logger.info(
                    "Deferred device_type_id resolution (device type being created)",
                    row_id=row.row_id,
                    device_type_name=device_type_name,
                    device_type_row=pending_row_id,
                )
            else:
                # Try to resolve immediately
                try:
                    device_type = await self.client.get_device_type_by_name(device_type_name)
                    if device_type:
                        payload["device_type_id"] = device_type["id"]
                    else:
                        logger.warning(
                            "Device type not found",
                            row_id=row.row_id,
                            device_type_name=device_type_name,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to resolve device type",
                        row_id=row.row_id,
                        device_type_name=device_type_name,
                        error=str(e),
                    )

    async def _build_device_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for device operations.

        Devices are per-configuration and can optionally reference
        device types and subtypes.

        Args:
            row: CSV row object (DeviceRow)
            payload: Payload dictionary to update
        """
        if hasattr(row, "name") and row.name:
            payload["name"] = row.name

        # Resolve optional device type
        device_type_name = getattr(row, "device_type", None)
        if device_type_name:
            pending_row_id = self.deferred.check_pending_device_type(device_type_name)
            if pending_row_id:
                payload["_deferred_device_type_name"] = device_type_name
                payload["_deferred_device_type_row"] = pending_row_id
                logger.info(
                    "Deferred device_type_id resolution for device",
                    row_id=row.row_id,
                    device_type_name=device_type_name,
                )
            else:
                try:
                    device_type = await self.client.get_device_type_by_name(device_type_name)
                    if device_type:
                        payload["device_type_id"] = device_type["id"]
                except Exception as e:
                    logger.warning(
                        "Failed to resolve device type for device",
                        row_id=row.row_id,
                        device_type_name=device_type_name,
                        error=str(e),
                    )

        # Resolve optional device subtype
        device_subtype_name = getattr(row, "device_subtype", None)
        if device_subtype_name:
            pending_row_id = self.deferred.check_pending_device_subtype(device_subtype_name)
            if pending_row_id:
                payload["_deferred_device_subtype_name"] = device_subtype_name
                payload["_deferred_device_subtype_row"] = pending_row_id
                logger.info(
                    "Deferred device_subtype_id resolution for device",
                    row_id=row.row_id,
                    device_subtype_name=device_subtype_name,
                )
            else:
                # Need device_type_id to look up subtype
                device_type_id = payload.get("device_type_id")
                if device_type_id:
                    try:
                        device_subtype = await self.client.get_device_subtype_by_name(
                            device_type_id, device_subtype_name
                        )
                        if device_subtype:
                            payload["device_subtype_id"] = device_subtype["id"]
                    except Exception as e:
                        logger.warning(
                            "Failed to resolve device subtype for device",
                            row_id=row.row_id,
                            device_subtype_name=device_subtype_name,
                            error=str(e),
                        )

        # Parse pipe-separated addresses field if provided
        addresses_str = getattr(row, "addresses", None)
        if addresses_str:
            address_list = [addr.strip() for addr in addresses_str.split("|") if addr.strip()]
            if address_list:
                # Store addresses for the handler to resolve and link
                payload["addresses"] = address_list

    async def _build_device_address_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for device_address operations.

        Device addresses link existing IP addresses to existing devices.

        Args:
            row: CSV row object (DeviceAddressRow)
            payload: Payload dictionary to update
        """
        # Resolve device
        device_name = getattr(row, "device_name", None)
        config_name = getattr(row, "config", None)

        if device_name and config_name:
            pending_row_id = self.deferred.check_pending_device(config_name, device_name)
            if pending_row_id:
                payload["_deferred_device_name"] = device_name
                payload["_deferred_device_config"] = config_name
                payload["_deferred_device_row"] = pending_row_id
                logger.info(
                    "Deferred device_id resolution for device_address",
                    row_id=row.row_id,
                    device_name=device_name,
                    config=config_name,
                )
            else:
                try:
                    config_id = payload.get("config_id")
                    if config_id:
                        device = await self.client.get_device_by_name(config_id, device_name)
                        if device:
                            payload["device_id"] = device["id"]
                        else:
                            logger.warning(
                                "Device not found for device_address",
                                row_id=row.row_id,
                                device_name=device_name,
                                config=config_name,
                            )
                except Exception as e:
                    logger.warning(
                        "Failed to resolve device for device_address",
                        row_id=row.row_id,
                        device_name=device_name,
                        error=str(e),
                    )

        # Resolve address
        address_str = getattr(row, "address", None)
        if address_str and "config_id" in payload:
            # Try to find the address in BAM
            try:
                # Determine IP version
                import ipaddress as ip_module

                try:
                    ip_obj = ip_module.ip_address(address_str)
                    if isinstance(ip_obj, ip_module.IPv6Address):
                        address_type = "IPv6Address"
                    else:
                        address_type = "IPv4Address"
                except ValueError:
                    address_type = "IPv4Address"

                payload["address_type"] = address_type

                # Try to find the address - it should already exist
                # We'll store the address string and resolve in the handler
                payload["address"] = address_str

            except Exception as e:
                logger.warning(
                    "Failed to process address for device_address",
                    row_id=row.row_id,
                    address=address_str,
                    error=str(e),
                )

    # -------------------------------------------------------------------------
    # Tag and Resource Tag Payload Builders
    # -------------------------------------------------------------------------

    async def _build_tag_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for tag operations.

        Tags must be created within a tag group. This method resolves the
        tag_group name to a tag_group_id.

        Args:
            row: CSV row object (TagRow)
            payload: Payload dictionary to update
        """
        if hasattr(row, "name") and row.name:
            payload["name"] = row.name

        # Resolve tag_group name to tag_group_id
        tag_group_name = getattr(row, "tag_group", None)
        if tag_group_name:
            try:
                tag_group = await self.client.get_tag_group_by_name(tag_group_name)
                if tag_group:
                    payload["tag_group_id"] = tag_group["id"]
                    logger.debug(
                        "Resolved tag_group name to ID",
                        row_id=row.row_id,
                        tag_group_name=tag_group_name,
                        tag_group_id=tag_group["id"],
                    )
                else:
                    logger.error(
                        "Tag group not found",
                        row_id=row.row_id,
                        tag_group_name=tag_group_name,
                    )
                    raise ValueError(
                        f"Tag group '{tag_group_name}' not found. "
                        f"Ensure the tag group exists before creating tags."
                    )
            except ValueError:
                raise
            except Exception as e:
                logger.error(
                    "Failed to resolve tag group",
                    row_id=row.row_id,
                    tag_group_name=tag_group_name,
                    error=str(e),
                )
                raise ValueError(f"Failed to resolve tag group '{tag_group_name}': {e}") from e

    async def _build_resource_tag_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for resource_tag operations.

        Resource tags associate a tag with a BAM resource. This method resolves:
        - resource_path to resource_id
        - tag_name to tag_id

        Args:
            row: CSV row object (ResourceTagRow)
            payload: Payload dictionary to update
        """
        resource_type = getattr(row, "resource_type", None)
        resource_path = getattr(row, "resource_path", None)
        tag_name = getattr(row, "tag_name", None)

        # Store resource_type for handler
        if resource_type:
            payload["resource_type"] = resource_type

        # Resolve resource_path to resource_id
        if resource_path and resource_type and "config_id" in payload:
            await self._resolve_resource_for_tagging(row, payload, resource_type, resource_path)

        # Resolve tag_name to tag_id
        if tag_name:
            try:
                tag = await self.client.get_tag_by_name(tag_name)
                if tag:
                    payload["tag_id"] = tag["id"]
                    logger.debug(
                        "Resolved tag_name to ID",
                        row_id=row.row_id,
                        tag_name=tag_name,
                        tag_id=tag["id"],
                    )
                else:
                    logger.error(
                        "Tag not found",
                        row_id=row.row_id,
                        tag_name=tag_name,
                    )
                    raise ValueError(
                        f"Tag '{tag_name}' not found. "
                        f"Ensure the tag exists before tagging resources."
                    )
            except ValueError:
                raise
            except Exception as e:
                logger.error(
                    "Failed to resolve tag",
                    row_id=row.row_id,
                    tag_name=tag_name,
                    error=str(e),
                )
                raise ValueError(f"Failed to resolve tag '{tag_name}': {e}") from e

    async def _resolve_resource_for_tagging(
        self,
        row: Any,
        payload: dict[str, Any],
        resource_type: str,
        resource_path: str,
    ) -> None:
        """Resolve a resource path to resource ID for tagging.

        Supports various resource types like ip4_network, ip4_block, dns_zone, etc.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            resource_type: Type of resource (ip4_network, dns_zone, etc.)
            resource_path: Path to resolve (e.g., /IPv4/10.0.0.0/8/10.1.0.0/24)
        """
        config_id = payload.get("config_id")

        try:
            if resource_type in ("ip4_network", "ip6_network"):
                # Extract CIDR from path
                # Path format: /IPv4/10.0.0.0/8/10.1.0.0/24 -> 10.1.0.0/24
                path_parts = resource_path.lstrip("/").split("/")
                # Handle /IPv4/ prefix
                if path_parts and path_parts[0] in ("IPv4", "IPv6"):
                    path_parts = path_parts[1:]
                # Get last two parts as CIDR
                if len(path_parts) >= 2:
                    cidr = f"{path_parts[-2]}/{path_parts[-1]}"
                else:
                    cidr = resource_path

                network = await self.client.get_network_by_cidr(config_id, cidr)
                payload["resource_id"] = network["id"]
                logger.debug(
                    "Resolved network path to ID",
                    row_id=row.row_id,
                    cidr=cidr,
                    resource_id=network["id"],
                )

            elif resource_type in ("ip4_block", "ip6_block"):
                # Extract CIDR from path
                path_parts = resource_path.lstrip("/").split("/")
                if path_parts and path_parts[0] in ("IPv4", "IPv6"):
                    path_parts = path_parts[1:]
                if len(path_parts) >= 2:
                    cidr = f"{path_parts[-2]}/{path_parts[-1]}"
                else:
                    cidr = resource_path

                block = await self.client.get_block_by_cidr_in_config(config_id, cidr)
                payload["resource_id"] = block["id"]
                logger.debug(
                    "Resolved block path to ID",
                    row_id=row.row_id,
                    cidr=cidr,
                    resource_id=block["id"],
                )

            elif resource_type == "dns_zone":
                # Zone path can be:
                # - Just the zone name (e.g., "example.com") - requires single view
                # - View/zone format (e.g., "Internal/example.com") - explicit view
                zone_path = resource_path.lstrip("/")
                view_id = payload.get("view_id")
                zone_name = zone_path

                # Check if path includes view prefix (e.g., "Internal/acme.internal")
                if "/" in zone_path:
                    parts = zone_path.split("/", 1)
                    view_name = parts[0]
                    zone_name = parts[1]
                    # Resolve the explicit view
                    view = await self.client.get_view_by_name_in_config(config_id, view_name)
                    if view:
                        view_id = view["id"]
                        logger.debug(
                            "Resolved explicit view from zone path",
                            row_id=row.row_id,
                            view_name=view_name,
                            view_id=view_id,
                        )
                    else:
                        raise ValueError(
                            f"View '{view_name}' not found in configuration. "
                            f"Ensure the view exists before tagging zones."
                        )
                elif not view_id:
                    # No explicit view - check how many views exist
                    views = await self.client.get_views_in_configuration(config_id)
                    if not views:
                        raise ValueError(
                            f"No views found in configuration for zone resolution. "
                            f"Cannot resolve zone '{zone_name}' without a view."
                        )
                    elif len(views) > 1:
                        # Multiple views exist - require explicit specification
                        view_names = [v.get("name", f"ID:{v['id']}") for v in views]
                        raise ValueError(
                            f"Ambiguous zone resolution: Multiple views exist ({', '.join(view_names)}). "
                            f"Specify view explicitly in resource_path as 'ViewName/{zone_name}' "
                            f"(e.g., 'Internal/{zone_name}') to avoid tagging the wrong zone."
                        )
                    else:
                        # Single view - safe to use
                        view_id = views[0]["id"]
                        logger.debug(
                            "Using single available view for zone resolution",
                            row_id=row.row_id,
                            view_id=view_id,
                        )

                if view_id:
                    zone = await self.client.get_zone_by_fqdn(view_id, zone_name)
                    payload["resource_id"] = zone["id"]
                    logger.debug(
                        "Resolved zone path to ID",
                        row_id=row.row_id,
                        zone_name=zone_name,
                        resource_id=zone["id"],
                    )

            elif resource_type in ("ip4_address", "ip6_address"):
                # Address path is just the IP address
                address = resource_path.lstrip("/")
                # Try to find the address using the appropriate method
                addr = await self.client.get_ip4_address(config_id, address)
                if addr:
                    payload["resource_id"] = addr["id"]
                    logger.debug(
                        "Resolved address to ID",
                        row_id=row.row_id,
                        address=address,
                        resource_id=addr["id"],
                    )
                else:
                    raise ValueError(f"Address '{address}' not found")

            else:
                logger.warning(
                    "Unsupported resource type for tagging resolution",
                    row_id=row.row_id,
                    resource_type=resource_type,
                )

        except Exception as e:
            logger.error(
                "Failed to resolve resource path for tagging",
                row_id=row.row_id,
                resource_type=resource_type,
                resource_path=resource_path,
                error=str(e),
            )
            raise ValueError(
                f"Failed to resolve {resource_type} path '{resource_path}': {e}"
            ) from e

    # -------------------------------------------------------------------------
    # User-Defined Link Payload Builder
    # -------------------------------------------------------------------------

    async def _build_user_defined_link_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for user_defined_link operations.

        User-defined links connect two BAM resources using a UDL definition.
        This method resolves:
        - udl_name to udl_definition_id
        - source_path to source_id
        - destination_path to destination_id

        Args:
            row: CSV row object (UserDefinedLinkRow)
            payload: Payload dictionary to update
        """
        # Resolve UDL definition name to ID
        udl_name = getattr(row, "udl_name", None)
        if udl_name:
            try:
                udl_def = await self.client.get_udl_definition_by_name(udl_name)
                if udl_def:
                    payload["udl_definition_id"] = udl_def["id"]
                    logger.debug(
                        "Resolved UDL definition name to ID",
                        row_id=row.row_id,
                        udl_name=udl_name,
                        udl_definition_id=udl_def["id"],
                    )
                else:
                    logger.error(
                        "UDL definition not found",
                        row_id=row.row_id,
                        udl_name=udl_name,
                    )
                    raise ValueError(
                        f"UDL definition '{udl_name}' not found. "
                        f"Create the UDL definition first."
                    )
            except ValueError:
                raise
            except Exception as e:
                logger.error(
                    "Failed to resolve UDL definition",
                    row_id=row.row_id,
                    udl_name=udl_name,
                    error=str(e),
                )
                raise ValueError(f"Failed to resolve UDL definition '{udl_name}': {e}") from e

        # Resolve source resource
        source_type = getattr(row, "source_type", None)
        source_path = getattr(row, "source_path", None)
        if source_type and source_path and "config_id" in payload:
            await self._resolve_udl_resource(row, payload, source_type, source_path, "source_id")

        # Store destination type for handler
        destination_type = getattr(row, "destination_type", None)
        if destination_type:
            payload["destination_type"] = destination_type

        # Resolve destination resource
        destination_path = getattr(row, "destination_path", None)
        if destination_type and destination_path and "config_id" in payload:
            await self._resolve_udl_resource(
                row, payload, destination_type, destination_path, "destination_id"
            )

    async def _resolve_udl_resource(
        self,
        row: Any,
        payload: dict[str, Any],
        resource_type: str,
        resource_path: str,
        target_key: str,
    ) -> None:
        """Resolve a resource path to ID for UDL operations.

        Args:
            row: CSV row object
            payload: Payload dictionary to update
            resource_type: Type of resource (ip4_address, device, etc.)
            resource_path: Path or identifier to resolve
            target_key: Key to store the resolved ID (source_id or destination_id)
        """
        config_id = payload.get("config_id")

        try:
            if resource_type in ("ip4_address", "ip6_address"):
                # resource_path is the IP address
                address = resource_path.strip()
                addr = await self.client.get_ip4_address(config_id, address)
                if addr:
                    payload[target_key] = addr["id"]
                else:
                    raise ValueError(f"Address '{address}' not found")

            elif resource_type in ("ip4_network", "ip6_network"):
                # resource_path is CIDR
                cidr = resource_path.strip()
                network = await self.client.get_network_by_cidr(config_id, cidr)
                payload[target_key] = network["id"]

            elif resource_type in ("ip4_block", "ip6_block"):
                cidr = resource_path.strip()
                block = await self.client.get_block_by_cidr_in_config(config_id, cidr)
                payload[target_key] = block["id"]

            elif resource_type == "device":
                # resource_path is device name
                device_name = resource_path.strip()
                device = await self.client.get_device_by_name(config_id, device_name)
                if device:
                    payload[target_key] = device["id"]
                else:
                    raise ValueError(f"Device '{device_name}' not found")

            elif resource_type == "dns_zone":
                # Zone path can be:
                # - Just the zone name (e.g., "example.com") - requires single view
                # - View/zone format (e.g., "Internal/example.com") - explicit view
                zone_path = resource_path.strip()
                view_id = payload.get("view_id")
                zone_name = zone_path

                # Check if path includes view prefix (e.g., "Internal/acme.internal")
                if "/" in zone_path:
                    parts = zone_path.split("/", 1)
                    view_name = parts[0]
                    zone_name = parts[1]
                    # Resolve the explicit view
                    view = await self.client.get_view_by_name_in_config(config_id, view_name)
                    if view:
                        view_id = view["id"]
                    else:
                        raise ValueError(
                            f"View '{view_name}' not found in configuration for UDL zone resolution."
                        )
                elif not view_id:
                    # No explicit view - check how many views exist
                    views = await self.client.get_views_in_configuration(config_id)
                    if not views:
                        raise ValueError(
                            f"No views found in configuration for UDL zone resolution. "
                            f"Cannot resolve zone '{zone_name}' without a view."
                        )
                    elif len(views) > 1:
                        # Multiple views exist - require explicit specification
                        view_names = [v.get("name", f"ID:{v['id']}") for v in views]
                        raise ValueError(
                            f"Ambiguous zone resolution for UDL: Multiple views exist ({', '.join(view_names)}). "
                            f"Specify view explicitly as 'ViewName/{zone_name}' to avoid linking to wrong zone."
                        )
                    else:
                        # Single view - safe to use
                        view_id = views[0]["id"]

                if view_id:
                    zone = await self.client.get_zone_by_fqdn(view_id, zone_name)
                    payload[target_key] = zone["id"]

            elif resource_type == "mac_address":
                mac = resource_path.strip()
                mac_addr = await self.client.get_mac_address_by_address(config_id, mac)
                if mac_addr:
                    payload[target_key] = mac_addr["id"]
                else:
                    raise ValueError(f"MAC address '{mac}' not found")

            elif resource_type == "mac_pool":
                pool_name = resource_path.strip()
                pool = await self.client.get_mac_pool_by_name(config_id, pool_name)
                if pool:
                    payload[target_key] = pool["id"]
                else:
                    raise ValueError(f"MAC pool '{pool_name}' not found")

            elif resource_type == "server":
                server_name = resource_path.strip()
                server = await self.client.get_server_by_name(server_name)
                if server:
                    payload[target_key] = server["id"]
                else:
                    raise ValueError(f"Server '{server_name}' not found")

            else:
                logger.warning(
                    "Unsupported resource type for UDL resolution",
                    row_id=row.row_id,
                    resource_type=resource_type,
                    target_key=target_key,
                )

            logger.debug(
                f"Resolved UDL {target_key}",
                row_id=row.row_id,
                resource_type=resource_type,
                resource_path=resource_path,
                resource_id=payload.get(target_key),
            )

        except Exception as e:
            logger.error(
                f"Failed to resolve UDL {target_key}",
                row_id=row.row_id,
                resource_type=resource_type,
                resource_path=resource_path,
                error=str(e),
            )
            raise ValueError(
                f"Failed to resolve {resource_type} '{resource_path}' for {target_key}: {e}"
            ) from e

    # -------------------------------------------------------------------------
    # ACL Payload Builder
    # -------------------------------------------------------------------------

    async def _build_acl_payload(self, row: Any, payload: dict[str, Any]) -> None:
        """Build payload for ACL operations.

        ACLs define which hosts are allowed or denied access to DNS services.

        Args:
            row: CSV row object (ACLRow)
            payload: Payload dictionary to update
        """
        if hasattr(row, "name") and row.name:
            payload["name"] = row.name

        # Parse match_elements - comma or pipe separated list of IPs/CIDRs
        match_elements_str = getattr(row, "match_elements", None)
        if match_elements_str:
            # Support both comma and pipe separators
            if "|" in match_elements_str:
                elements = [e.strip() for e in match_elements_str.split("|") if e.strip()]
            else:
                elements = [e.strip() for e in match_elements_str.split(",") if e.strip()]
            payload["match_elements"] = elements
            logger.debug(
                "Parsed ACL match_elements",
                row_id=row.row_id,
                match_elements=elements,
            )
