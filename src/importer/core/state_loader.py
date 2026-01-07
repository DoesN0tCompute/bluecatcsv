"""State Loader - Fetch current state from BAM with controlled depth.

Per official BlueCat REST API v2 documentation.

Purpose:
-------
The state loader fetches the current state of resources from BAM so the
diff engine can compare desired state (from CSV) against actual state.
This comparison determines which operations (CREATE/UPDATE/DELETE/NOOP)
are needed for each CSV row.

Fetch Strategies:
----------------
StateLoadStrategy controls how much data is fetched:

- SHALLOW: Fetch only the resource itself
  Use case: Simple existence check, basic property comparison
  API calls: 1 per resource

- CHILDREN: Fetch resource + its immediate children
  Use case: Network with addresses, zone with records
  API calls: 1 (with ?embed=children) or 2 (resource + children list)

- DEEP: Fetch resource + entire subtree recursively
  Use case: Full export, complete state snapshot
  API calls: Varies with depth, can be expensive

Optimization Techniques:
-----------------------
1. Caching: Loaded states are cached by ID to avoid redundant fetches
2. Embedded Fetch: Uses BAM's ?embed parameter when available (single request)
3. Batch Loading: Uses id:in() filters to fetch multiple resources at once
4. Concurrency Control: Limits parallel requests to avoid overwhelming BAM

Example Usage:
-------------
```python
loader = StateLoader(bam_client)

# Check if network exists
state = await loader.load_resource_state(
    "ip4_network",
    {"cidr": "10.1.0.0/24", "config_id": 123},
    strategy=StateLoadStrategy.SHALLOW
)

# Get network with all addresses
state = await loader.load_resource_state(
    "ip4_network",
    {"id": 456},
    strategy=StateLoadStrategy.CHILDREN
)
```
"""

import asyncio
from typing import Any

import structlog

from ..bam.client import BAMClient
from ..models.state import ResourceIdentifier, ResourceState, StateLoadStrategy
from ..utils.exceptions import ResourceNotFoundError

logger = structlog.get_logger(__name__)


class StateLoader:
    """
    Fetch current state from BAM with controlled depth.

    Uses official BlueCat REST API v2 endpoints to retrieve resource state
    for comparison against desired CSV state.

    Features:
    - Configurable fetch strategies (shallow, children, deep)
    - Caching to minimize API calls
    - Batch loading with concurrency control
    - Pagination support for large result sets
    """

    def __init__(self, bam_client: BAMClient, cache_enabled: bool = True) -> None:
        """
        Initialize State Loader.

        Args:
            bam_client: Authenticated BAM REST API v2 client
            cache_enabled: Whether to cache loaded states (default: True)
        """
        self.client = bam_client
        self.cache_enabled = cache_enabled
        self.cache: dict[int, ResourceState] = {}

    def clear_cache(self) -> None:
        """Clear the state cache."""
        self.cache.clear()
        logger.debug("State cache cleared")

    async def load_resource_state(
        self,
        resource_type: str,
        identifiers: dict[str, Any],
        strategy: StateLoadStrategy = StateLoadStrategy.SHALLOW,
        page_size: int = 1000,
    ) -> ResourceState | None:
        """
        Load current state for a resource from BAM.

        Uses official API endpoints per resource type:
        - Configurations: GET /api/v2/configurations
        - Entity Details: GET /api/v2/{resource_type}/{id}
        - Networks: GET /api/v2/blocks/{blockId}/networks
        - Addresses: GET /api/v2/networks/{networkId}/addresses

        For CREATE: Check if resource exists by unique keys
        For UPDATE/DELETE: Fetch full object for diffing

        Args:
            resource_type: Type of BAM resource (ip4_network, ip4_address, etc.)
            identifiers: Unique identifiers (id, address, name, etc.)
            strategy: How much related data to fetch
            page_size: For pagination (default: 1000)

        Returns:
            ResourceState if exists, None otherwise
        """
        # Check cache first
        if self.cache_enabled and "id" in identifiers:
            resource_id = identifiers["id"]
            if resource_id in self.cache:
                logger.debug("State cache hit", resource_id=resource_id)
                return self.cache[resource_id]

        logger.debug(
            "Loading resource state",
            resource_type=resource_type,
            identifiers=identifiers,
            strategy=strategy.value,
        )

        # For CHILDREN strategy with ID, try embedded fetch first (single request)
        # Only if the client supports embedded fetches
        if strategy == StateLoadStrategy.CHILDREN and "id" in identifiers:
            try:
                resource = await self.load_resource_with_embedded_children(
                    identifiers["id"], resource_type
                )
                if resource:
                    # Embedded fetch succeeded, cache and return
                    if self.cache_enabled:
                        self.cache[resource.id] = resource
                        logger.debug("Cached resource state", resource_id=resource.id)
                    return resource
            except Exception as e:
                logger.debug(
                    "Embedded children fetch failed, falling back to standard fetch",
                    error=str(e),
                )
            # Fall through to standard fetch if embedding failed or returned None

        # Fetch resource based on type and identifiers
        resource = await self._fetch_resource(resource_type, identifiers, page_size)

        if not resource:
            logger.debug("Resource not found", resource_type=resource_type, identifiers=identifiers)
            return None

        # Fetch related data based on strategy
        if strategy == StateLoadStrategy.CHILDREN:
            resource.children = await self._fetch_children(resource.id, resource_type)
        elif strategy == StateLoadStrategy.DEEP:
            resource.children = await self._fetch_subtree(resource.id, resource_type)

        # Cache result
        if self.cache_enabled:
            self.cache[resource.id] = resource
            logger.debug("Cached resource state", resource_id=resource.id)

        return resource

    async def batch_load(
        self,
        resources: list[ResourceIdentifier],
        strategy: StateLoadStrategy,
        max_concurrency: int = 10,
    ) -> dict[str, ResourceState | None]:
        """
        Load multiple resources using batch queries where possible.

        Attempts to use id:in() batch queries per BlueCat REST API v2 to reduce
        N+1 overhead. Falls back to individual queries if batch fetch fails or
        is not supported.

        Args:
            resources: List of resource identifiers to load
            strategy: Fetch strategy for all resources
            max_concurrency: Maximum concurrent requests (default: 10)

        Returns:
            Dictionary mapping resource keys to their states
        """
        logger.info("Batch loading states", count=len(resources), strategy=strategy.value)

        state_map: dict[str, ResourceState | None] = {}
        resources_to_load_individually: list[ResourceIdentifier] = []

        # Try batch fetch if client has the method
        batch_method = getattr(self.client, "batch_get_entities_by_ids", None)
        if batch_method and callable(batch_method):
            # Separate resources with IDs (can batch) from those without
            resources_with_ids: dict[str, list[tuple[ResourceIdentifier, int]]] = {}

            for res in resources:
                res_dict = res.to_dict()
                if "id" in res_dict and res_dict["id"]:
                    resource_type = res.resource_type
                    if resource_type not in resources_with_ids:
                        resources_with_ids[resource_type] = []
                    resources_with_ids[resource_type].append((res, res_dict["id"]))
                else:
                    resources_to_load_individually.append(res)

            # Batch fetch resources with IDs grouped by type
            for resource_type, res_id_pairs in resources_with_ids.items():
                try:
                    ids = [rid for _, rid in res_id_pairs]
                    id_to_identifier = {rid: res for res, rid in res_id_pairs}

                    # Fetch all entities of this type in one request
                    entities = await batch_method(ids, resource_type)

                    # Validate response is a list of dicts
                    if not isinstance(entities, list):
                        raise TypeError(f"Expected list from batch fetch, got {type(entities)}")

                    # Map results back to identifiers
                    for entity in entities:
                        entity_id = entity.get("id")
                        if entity_id in id_to_identifier:
                            identifier = id_to_identifier[entity_id]
                            state = self._parse_resource_state(entity)

                            # Fetch children if strategy requires
                            if strategy == StateLoadStrategy.CHILDREN:
                                state.children = await self._fetch_children(state.id, state.type)
                            elif strategy == StateLoadStrategy.DEEP:
                                state.children = await self._fetch_subtree(state.id, state.type)

                            # Cache result
                            if self.cache_enabled:
                                self.cache[state.id] = state

                            state_map[identifier.key] = state

                    # Mark missing IDs as None (not found)
                    returned_ids = {e.get("id") for e in entities}
                    for res, rid in res_id_pairs:
                        if rid not in returned_ids:
                            state_map[res.key] = None

                except Exception as e:
                    # Distinguish between not supported (MethodNotAllowed/NotImplemented)
                    # and genuine server errors.
                    error_str = str(e).lower()
                    if (
                        "405" in error_str
                        or "not allowed" in error_str
                        or "not implemented" in error_str
                    ):
                        logger.warning(
                            "Batch fetch not supported, falling back to individual queries",
                            resource_type=resource_type,
                        )
                        # Add all to fallback list
                        resources_to_load_individually.extend([res for res, _ in res_id_pairs])
                    else:
                        logger.error(
                            "Batch fetch failed unexpectedly",
                            resource_type=resource_type,
                            error=str(e),
                        )
                        # On unexpected error, we should probably try individual
                        # just in case it was a payload size issue, but log it as error
                        resources_to_load_individually.extend([res for res, _ in res_id_pairs])
        else:
            # No batch method available, load all individually
            resources_to_load_individually = list(resources)

        # Individual queries for remaining resources
        if resources_to_load_individually:
            logger.debug(
                "Loading resources individually", count=len(resources_to_load_individually)
            )
            semaphore = asyncio.Semaphore(max_concurrency)

            async def load_one(
                identifier: ResourceIdentifier,
            ) -> tuple[str, ResourceState | None]:
                async with semaphore:
                    state = await self.load_resource_state(
                        identifier.resource_type,
                        identifier.to_dict(),
                        strategy,
                    )
                    return (identifier.key, state)

            tasks = [load_one(res) for res in resources_to_load_individually]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(
                        "Failed to load resource",
                        error=str(result),
                        error_type=type(result).__name__,
                    )
                    if not isinstance(result, ResourceNotFoundError):
                        logger.warning(
                            "Non-fatal error during batch load, continuing", error=str(result)
                        )
                    continue
                key, state = result
                state_map[key] = state

        logger.info("Batch load complete", loaded=len(state_map), requested=len(resources))

        logger.info("Batch load complete", loaded=len(state_map), requested=len(resources))

        return state_map

    async def bulk_load_addresses(
        self, network_id: int, address_list: list[str]
    ) -> dict[str, ResourceState]:
        """
        Bulk load addresses within a network using filtering.

        Args:
            network_id: Parent network ID
            address_list: List of IP addresses to fetch

        Returns:
            Dictionary mapping IP address to ResourceState
        """
        if not address_list:
            return {}

        logger.debug("Bulk loading addresses", network_id=network_id, count=len(address_list))

        # BAM v2 filter: address:in(ip1,ip2,...)
        # We process in chunks to avoid URL length limits
        chunk_size = 50
        result_map: dict[str, ResourceState] = {}

        for i in range(0, len(address_list), chunk_size):
            chunk = address_list[i : i + chunk_size]
            # addresses need to be single-quoted in the filter? typically no for IP addresses but let's see.
            # Using bare values for now as they are IPs.
            # Safe to assume simple comma separation.
            filter_val = ",".join(chunk)
            filter_str = f"address:in({filter_val})"

            try:
                # Use client method that supports filtering
                # Note: get_addresses_in_network needs to support 'filter' kwarg
                resources = await self.client.get_addresses_in_network(
                    network_id, filter=filter_str
                )

                for res in resources:
                    state = self._parse_resource_state(res)
                    props = state.properties or {}
                    ip = props.get("address")
                    if ip:
                        result_map[ip] = state
                        if self.cache_enabled:
                            self.cache[state.id] = state

            except Exception as e:
                logger.error(
                    "Bulk address load failed for chunk",
                    network_id=network_id,
                    error=str(e),
                )
                # Fallback to individual loads or partial results?
                # For now, we log and continue to next chunk

        return result_map

    async def bulk_load_networks(
        self, parent_id: int, cidr_list: list[str], parent_type: str = "Block"
    ) -> dict[str, ResourceState]:
        """
        Bulk load networks within a block using filtering.

        Args:
            parent_id: Parent Block ID
            cidr_list: List of CIDRs to fetch
            parent_type: Type of parent (Block usually)

        Returns:
            Dictionary mapping CIDR to ResourceState
        """
        if not cidr_list:
            return {}

        logger.debug("Bulk loading networks", parent_id=parent_id, count=len(cidr_list))

        chunk_size = 50
        result_map: dict[str, ResourceState] = {}

        for i in range(0, len(cidr_list), chunk_size):
            chunk = cidr_list[i : i + chunk_size]
            # range field usually requires quoting if it contains special chars like /
            # BAM v2: range:in('10.0.0.0/24','10.0.1.0/24')
            escaped_chunk = [f"'{c}'" for c in chunk]
            filter_val = ",".join(escaped_chunk)
            filter_str = f"range:in({filter_val})"

            try:
                # Assuming get_child_networks supports filter

                # Client method depends on resource type?
                # Usually get_child_networks(block_id)
                resources = await self.client.get_child_networks(parent_id, filter=filter_str)

                for res in resources:
                    state = self._parse_resource_state(res)
                    props = state.properties or {}
                    cidr = props.get("range") or props.get("CIDR")
                    if cidr:
                        result_map[cidr] = state
                        if self.cache_enabled:
                            self.cache[state.id] = state

            except Exception as e:
                logger.error(
                    "Bulk network load failed for chunk",
                    parent_id=parent_id,
                    error=str(e),
                )

        return result_map

    async def bulk_load_zones(
        self, view_id: int, zone_names: list[str]
    ) -> dict[str, ResourceState]:
        """
        Bulk load zones within a view using filtering.

        Args:
            view_id: View ID
            zone_names: List of zone names

        Returns:
            Dictionary mapping zone name to ResourceState
        """
        if not zone_names:
            return {}

        logger.debug("Bulk loading zones", view_id=view_id, count=len(zone_names))

        chunk_size = 50
        result_map: dict[str, ResourceState] = {}

        for i in range(0, len(zone_names), chunk_size):
            chunk = zone_names[i : i + chunk_size]
            # name:in('example.com','foo.com')
            escaped_chunk = [f"'{n}'" for n in chunk]
            filter_val = ",".join(escaped_chunk)
            filter_str = f"name:in({filter_val})"

            try:
                resources = await self.client.get_zones_in_view(view_id, filter=filter_str)

                for res in resources:
                    state = self._parse_resource_state(res)
                    props = state.properties or {}
                    name = props.get("name")  # or 'absoluteName'? properties usually has 'name'
                    if name:
                        result_map[name] = state
                        if self.cache_enabled:
                            self.cache[state.id] = state

            except Exception as e:
                logger.error(
                    "Bulk zone load failed for chunk",
                    view_id=view_id,
                    error=str(e),
                )

        return result_map

    async def bulk_load_records(
        self,
        zone_id: int,
        record_names: list[str],
        record_type: str | None = None,
    ) -> dict[str, list[ResourceState]]:
        """
        Bulk load records within a zone using filtering.

        Args:
            zone_id: Zone ID
            record_names: List of record names (short names usually)
            record_type: Optional record type to filter by

        Returns:
            Dictionary mapping record name to List of ResourceStates
        """
        if not record_names:
            return {}

        logger.debug(
            "Bulk loading records",
            zone_id=zone_id,
            count=len(record_names),
            type=record_type,
        )

        chunk_size = 50
        # Map: name -> list of states (same name can map to multiple types or records)
        result_map: dict[str, list[ResourceState]] = {}

        for i in range(0, len(record_names), chunk_size):
            chunk = record_names[i : i + chunk_size]
            escaped_chunk = [f"'{n}'" for n in chunk]
            filter_val = ",".join(escaped_chunk)

            # Combine filters: name IN (...) AND type EQ ...
            parts = [f"name:in({filter_val})"]
            if record_type:
                parts.append(f"type:eq:{record_type}")

            filter_str = ",".join(parts)

            try:
                resources = await self.client.get_resource_records_in_zone(
                    zone_id, filter=filter_str
                )

                for res in resources:
                    state = self._parse_resource_state(res)
                    props = state.properties or {}
                    name = props.get("name")
                    if name:
                        if name not in result_map:
                            result_map[name] = []
                        result_map[name].append(state)
                        if self.cache_enabled:
                            self.cache[state.id] = state

            except Exception as e:
                logger.error(
                    "Bulk record load failed for chunk",
                    zone_id=zone_id,
                    error=str(e),
                )

        return result_map

    async def _fetch_resource(
        self,
        resource_type: str,
        identifiers: dict[str, Any],
        page_size: int,
    ) -> ResourceState | None:
        """
        Fetch a single resource using official BAM REST API v2.

        Args:
            resource_type: Type of resource
            identifiers: Identifiers to search by
            page_size: Pagination size

        Returns:
            ResourceState if found, None otherwise
        """
        try:
            # If we have an ID, use direct entity endpoint
            if "id" in identifiers:
                resource_id = identifiers["id"]
                # Map CSV resource types to API resource types
                api_resource_type_map = {
                    "ip4_block": "IP4Block",
                    "ip4_network": "IP4Network",
                    "ip4_address": "IP4Address",
                    "ip6_block": "IP6Block",
                    "ip6_network": "IP6Network",
                    "ip6_address": "IP6Address",
                    "dns_zone": "DNSZone",
                    "host_record": "HostRecord",
                    "configuration": "Configuration",
                    "view": "View",
                    # DHCP object types
                    "ipv4_dhcp_range": "IPv4DHCPRange",
                    "ipv6_dhcp_range": "IPv6DHCPRange",
                    "dhcp_deployment_role": "DHCPDeploymentRole",
                }

                api_resource_type = api_resource_type_map.get(resource_type)
                if not api_resource_type:
                    raise ValueError(
                        f"Unsupported resource type for entity lookup: {resource_type}"
                    )

                # Official API: Use type-specific endpoint
                data = await self.client.get_entity_by_id(resource_id, api_resource_type)
                return self._parse_resource_state(data)

            # Otherwise, search by other identifiers
            # Build filter query based on identifiers
            filters = []
            if "name" in identifiers:
                filters.append(f"name:eq:{identifiers['name']}")
            if "address" in identifiers:
                filters.append(f"address:eq:{identifiers['address']}")
            if "cidr" in identifiers:
                filters.append(f"CIDR:eq:{identifiers['cidr']}")

            if not filters:
                logger.warning("No valid identifiers for search", resource_type=resource_type)
                return None

            # Determine endpoint based on resource type
            endpoint, params = self._build_search_endpoint(
                resource_type, identifiers, filters, page_size
            )

            # Official API: GET with filter parameters
            result = await self.client.get(endpoint, params=params)

            # Parse HAL+JSON response
            items = result.get("data", result.get("_embedded", {}).get("items", []))

            if not items:
                return None

            # Return first match (should be unique based on filters)
            return self._parse_resource_state(items[0])

        except ResourceNotFoundError:
            return None
        except Exception as e:
            logger.error("Failed to fetch resource", resource_type=resource_type, error=str(e))
            raise

    def _build_search_endpoint(
        self,
        resource_type: str,
        identifiers: dict[str, Any],
        filters: list[str],
        page_size: int,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build search endpoint and parameters per official API.

        Args:
            resource_type: Type of resource
            identifiers: Search identifiers
            filters: Filter expressions
            page_size: Page size

        Returns:
            Tuple of (endpoint, params)
        """
        filter_str = ",".join(filters) if filters else None
        params: dict[str, Any] = {"limit": page_size}

        if filter_str:
            params["filter"] = filter_str

        # Map resource types to API endpoints
        if resource_type == "configuration":
            endpoint = "configurations"
        elif resource_type in ("ip4_block", "ip6_block", "block"):
            # Blocks under configuration
            config_id = identifiers.get("config_id", identifiers.get("configuration_id"))
            if config_id:
                endpoint = f"configurations/{config_id}/blocks"
            else:
                endpoint = "blocks"
        elif resource_type in ("ip4_network", "ip6_network", "network"):
            # Networks under block
            block_id = identifiers.get("block_id", identifiers.get("parent_id"))
            if block_id:
                endpoint = f"blocks/{block_id}/networks"
            else:
                endpoint = "networks"
        elif resource_type in ("ip4_address", "ip6_address", "address"):
            # Addresses under network
            network_id = identifiers.get("network_id", identifiers.get("parent_id"))
            if network_id:
                endpoint = f"networks/{network_id}/addresses"
            else:
                endpoint = "addresses"
        elif resource_type == "dns_zone":
            view_id = identifiers.get("view_id")
            if view_id:
                endpoint = f"views/{view_id}/zones"
            else:
                endpoint = "zones"
        elif resource_type == "host_record":
            zone_id = identifiers.get("zone_id")
            if zone_id:
                endpoint = f"zones/{zone_id}/resourceRecords"
                params["filter"] = (
                    f"type:eq:HostRecord,{filter_str}" if filter_str else "type:eq:HostRecord"
                )
            else:
                endpoint = "resourceRecords"
                params["filter"] = (
                    f"type:eq:HostRecord,{filter_str}" if filter_str else "type:eq:HostRecord"
                )
        elif resource_type in ("ipv4_dhcp_range", "ipv6_dhcp_range", "dhcp_range"):
            # DHCP ranges under network
            network_id = identifiers.get("network_id", identifiers.get("parent_id"))
            if network_id:
                endpoint = f"networks/{network_id}/ranges"
            else:
                endpoint = "ranges"

        elif resource_type in ("dhcp_deployment_role", "deployment_role"):
            # Deployment roles can be under various parents (network, block, etc.)
            # For DHCP deployment roles, typically under network
            network_id = identifiers.get("network_id")
            if network_id:
                endpoint = f"networks/{network_id}/deploymentRoles"
            else:
                endpoint = "deploymentRoles"
        else:
            # Use type-specific endpoints instead of generic entity search
            endpoint_map = {
                "ip4_block": "blocks",
                "ip4_network": "networks",
                "ip4_address": "addresses",
                "ip6_block": "blocks",
                "ip6_network": "networks",
                "ip6_address": "addresses",
                "dns_zone": "zones",
                "host_record": "resourceRecords",
                "configuration": "configurations",
                # DHCP object types
                "ipv4_dhcp_range": "ranges",
                "ipv6_dhcp_range": "ranges",
                "dhcp_deployment_role": "deploymentRoles",
            }

            endpoint = endpoint_map.get(resource_type)
            if not endpoint:
                raise ValueError(f"Unsupported resource type for search: {resource_type}")

            if filter_str:
                params["filter"] = filter_str

        return endpoint, params

    def _get_child_collection_name(self, resource_type: str) -> str | None:
        """
        Get the child collection name for embedding.

        Args:
            resource_type: Parent resource type

        Returns:
            Child collection name for embed() operator, or None if not supported
        """
        child_map = {
            "configuration": "blocks",
            "config": "blocks",
            "Configuration": "blocks",
            "ip4_block": "networks",
            "block": "networks",
            "IPv4Block": "networks",
            "ip4_network": "addresses",
            "network": "addresses",
            "IPv4Network": "addresses",
            "dns_zone": "resourceRecords",
            "DNSZone": "resourceRecords",
            "Zone": "resourceRecords",
        }
        return child_map.get(resource_type)

    async def load_resource_with_embedded_children(
        self, resource_id: int, resource_type: str
    ) -> ResourceState | None:
        """
        Fetch a resource with children embedded in a single request.

        Uses fields=embed() per BlueCat REST API v2 to fetch parent and
        children in one request, reducing API call overhead.

        Args:
            resource_id: Resource ID
            resource_type: Resource type

        Returns:
            ResourceState with children populated, or None if not found
        """
        child_collection = self._get_child_collection_name(resource_type)
        if not child_collection:
            # No embedding support, fall back to separate fetch
            return None

        # Map resource types to endpoints
        endpoint_map = {
            "configuration": f"configurations/{resource_id}",
            "config": f"configurations/{resource_id}",
            "Configuration": f"configurations/{resource_id}",
            "ip4_block": f"blocks/{resource_id}",
            "block": f"blocks/{resource_id}",
            "IPv4Block": f"blocks/{resource_id}",
            "ip4_network": f"networks/{resource_id}",
            "network": f"networks/{resource_id}",
            "IPv4Network": f"networks/{resource_id}",
            "dns_zone": f"zones/{resource_id}",
            "DNSZone": f"zones/{resource_id}",
            "Zone": f"zones/{resource_id}",
        }

        endpoint = endpoint_map.get(resource_type)
        if not endpoint:
            return None

        try:
            # Use embed() to fetch children in single request
            result = await self.client.get(
                endpoint, params={"fields": f"embed({child_collection})"}
            )

            state = self._parse_resource_state(result)

            # Extract embedded children from _embedded field
            embedded = result.get("_embedded", {})
            child_data = embedded.get(child_collection, [])

            state.children = [self._parse_resource_state(item) for item in child_data]

            logger.debug(
                "Fetched resource with embedded children",
                resource_id=resource_id,
                children_count=len(state.children),
            )

            return state

        except Exception as e:
            logger.warning(
                "Embedded fetch failed, will fall back to separate requests",
                resource_id=resource_id,
                resource_type=resource_type,
                error=str(e),
            )
            return None

    async def _fetch_children(self, resource_id: int, resource_type: str) -> list[ResourceState]:
        """
        Fetch immediate children of a resource.

        Uses BAMClient methods with pagination support to handle large result sets.

        Args:
            resource_id: Parent resource ID
            resource_type: Type of parent resource

        Returns:
            List of child ResourceState objects
        """
        logger.debug("Fetching children", resource_id=resource_id, resource_type=resource_type)

        children: list[ResourceState] = []

        try:
            # Use BAMClient methods with pagination support
            items: list[dict] = []

            if resource_type in ("configuration", "config", "Configuration"):
                # Fetch blocks under configuration (with pagination)
                items = await self.client.get_ip4_blocks(resource_id)
            elif resource_type in ("ip4_block", "block", "IPv4Block"):
                # Fetch networks under block (with pagination)
                items = await self.client.get_child_networks(resource_id)
            elif resource_type in ("ip4_network", "network", "IPv4Network"):
                # Fetch addresses under network (with pagination)
                items = await self.client.get_addresses_in_network(resource_id)
            elif resource_type in ("dns_zone", "DNSZone", "Zone"):
                # Fetch resource records under zone (with pagination)
                items = await self.client.get_resource_records_in_zone(resource_id)
            else:
                logger.debug("No children endpoint for type", resource_type=resource_type)
                return children

            for item in items:
                child_state = self._parse_resource_state(item)
                children.append(child_state)

            logger.debug("Fetched children", resource_id=resource_id, count=len(children))

        except Exception as e:
            logger.error(
                "Failed to fetch children",
                resource_id=resource_id,
                resource_type=resource_type,
                error=str(e),
            )

        return children

    async def _fetch_subtree(self, resource_id: int, resource_type: str) -> list[ResourceState]:
        """
        Fetch full subtree recursively (use sparingly - expensive).

        Args:
            resource_id: Root resource ID
            resource_type: Type of root resource

        Returns:
            List of all descendant ResourceState objects
        """
        logger.warning(
            "Fetching full subtree - expensive operation",
            resource_id=resource_id,
            resource_type=resource_type,
        )

        all_descendants: list[ResourceState] = []
        children = await self._fetch_children(resource_id, resource_type)

        for child in children:
            all_descendants.append(child)
            # Recursively fetch children's children
            child_descendants = await self._fetch_subtree(child.id, child.type)
            all_descendants.extend(child_descendants)

        return all_descendants

    def _parse_resource_state(self, data: dict[str, Any]) -> ResourceState:
        """
        Parse HAL+JSON resource response into ResourceState.

        Args:
            data: Raw API response data

        Returns:
            ResourceState object
        """
        # Extract core fields from API response
        resource_id = data.get("id")
        resource_type = data.get("type")
        properties = data.get("properties", {})

        # Extract versioning info if available
        etag = data.get("_etag")
        version = data.get("_version")

        # HAL+JSON links for navigation
        data.get("_links", {})

        return ResourceState(
            id=resource_id,
            type=resource_type,
            properties=properties,
            etag=etag,
            version=version,
            children=None,  # Populated separately if needed
        )
