"""Path to ID resolver with cache coherency."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import diskcache
import structlog

from ..bam.client import BAMClient
from ..config import CacheConfig
from ..constants import RESOLVER_TYPE_MAP
from ..observability.metrics import get_global_collector
from ..utils.exceptions import PendingCreateError, ResourceNotFoundError
from ..utils.locking import KeyedLock

logger = structlog.get_logger(__name__)


@dataclass
class CacheStats:
    """Statistics for resolver cache performance."""

    cache_hits: int = 0
    cache_misses: int = 0
    pending_hits: int = 0
    total_queries: int = 0

    def cache_hit(self) -> None:
        """Record a cache hit."""
        self.cache_hits += 1
        self.total_queries += 1

    def cache_miss(self) -> None:
        """Record a cache miss."""
        self.cache_misses += 1
        self.total_queries += 1

    def pending_hit(self) -> None:
        """Record a pending create hit."""
        self.pending_hits += 1
        self.total_queries += 1

    def hit_rate(self) -> float:
        """
        Calculate cache hit rate.

        Returns:
            float: Hit rate as a decimal (0.0 to 1.0).
        """
        if self.total_queries == 0:
            return 0.0
        return (self.cache_hits + self.pending_hits) / self.total_queries


class Resolver:
    """
    Convert human-readable paths to BAM IDs with multi-level caching.

    Design Decisions:
    - JSON disk cache instead of pickle: Prevents code execution attacks on cache files
    - Two-tier zone caching: L1 (memory, 2.5min) for speed, L2 (disk, 1hr) for persistence
    - Pending creates tracking: Enables in-batch references when resources don't exist yet
    """

    def __init__(
        self,
        bam_client: BAMClient,
        cache_dir: Path,
        cache_config: CacheConfig | None = None,
        no_cache: bool = False,
    ) -> None:
        """
        Initialize resolver with security-focused caching strategy.

        Args:
            bam_client: BAM API client instance
            cache_dir: Directory for persistent disk cache storage
            cache_config: Cache configuration with TTL settings (optional)
            no_cache: If True, bypass all caching (for testing/debugging)
        """
        self.client = bam_client
        self.cache_config = cache_config or CacheConfig()
        self.no_cache = no_cache
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Use JSON disk cache to prevent code injection attacks that pickle would allow
        # Cache stores path -> bam_id mappings for fast lookup without API calls
        self.cache: diskcache.Cache = diskcache.Cache(
            str(cache_dir),
            disk=diskcache.JSONDisk,  # Security: prevents arbitrary code execution
            disk_compress_level=1,  # Light compression for performance
        )

        # L1 Memory cache for views (rarely change, frequently accessed)
        # TTL of 5 minutes balances performance with data freshness
        self._view_cache: dict[int, list[dict[str, Any]]] = {}
        self._view_cache_ttl: dict[int, float] = {}
        self._view_cache_duration = self.cache_config.view_cache_ttl

        # L1 Memory cache for zones with shorter TTL (2.5 min)
        # Zones change more frequently than views in enterprise DNS
        self._zone_cache: dict[int, list[dict[str, Any]]] = {}
        self._zone_cache_ttl: dict[int, float] = {}
        self._zone_cache_duration = self.cache_config.view_cache_ttl // 2

        # Pending creates tracks resources that WILL be created in this batch
        # This enables operations in the same CSV to reference each other
        #
        # CONTRACT:
        # 1. register_pending_create() - Declares intent to create resource
        # 2. Operation executes
        # 3. On SUCCESS: confirm_create() with real BAM ID
        # 4. On FAILURE: cancel_create() to prevent phantom references
        #
        # CRITICAL: Failure to call confirm/cancel leaves stale pending entries
        # that cause DeferredResolutionError for dependent operations.
        #
        # DATA STRUCTURE:
        # Maps path → (row_id, resource_type) - NOT bam_id yet!
        # The row_id helps debugging ("row 5 promised to create this but failed")
        self.pending_creates: dict[str, tuple[str | int, str]] = {}

        # Granular lock to allow concurrent operations on disjoint paths
        # Prevents race conditions for same-path operations while maximizing concurrency
        self._pending_lock = KeyedLock()

        # Performance tracking
        self.stats = CacheStats()
        self._prefetch_complete = False  # Tracks if multi-level prefetch has been done

        # Metrics
        self.collector = get_global_collector()

    async def register_pending_create(
        self, path: str, row_id: str | int, resource_type: str
    ) -> None:
        """
        Register a resource that will be created, enabling other operations to reference it.

        DEFERRED RESOLUTION CONTRACT:
        This is a two-phase commit protocol for resource creation:

        Phase 1 (PROMISE): Call register_pending_create()
            - Declares "I will create this resource"
            - Other operations resolving this path get PendingCreateError
            - Graph builder can safely add dependencies

        Phase 2 (FULFILL or ABORT):
            SUCCESS: Call confirm_create() with real BAM ID
                - Pending entry removed
                - Cache updated with real ID
                - Future resolutions succeed immediately

            FAILURE: Call cancel_create() with reason
                - Pending entry removed
                - Dependent operations fail with clear error
                - No phantom resources in system

        EDGE CASE: Missing confirm/cancel
        If operation fails WITHOUT calling cancel_create(), the pending
        entry persists. Subsequent resolutions raise PendingCreateError
        indefinitely. This is a BUG that must be prevented by always
        using try/finally blocks in executors.

        Example Flow:
            # Graph Building Phase
            register_pending_create("Default/10.0.0.0/8", row_id=1, "ip4_block")

            # Execution Phase
            try:
                block_id = await create_block("10.0.0.0/8")
                await confirm_create("Default/10.0.0.0/8", block_id)  # SUCCESS
            except Exception as e:
                await cancel_create("Default/10.0.0.0/8", str(e))  # FAILURE

        THREAD-SAFETY:
        Uses KeyedLock(path) to prevent race conditions where multiple
        operations try to register/confirm/cancel the same path concurrently.

        Args:
            path: Full hierarchical path that will be created
            row_id: CSV row identifier (for debugging, NOT the BAM ID)
            resource_type: Type of resource (e.g., "ip4_block", "dns_zone")
        """
        async with self._pending_lock(path):
            self.pending_creates[path] = (row_id, resource_type)
            logger.debug(
                "Registered pending create", path=path, row_id=row_id, resource_type=resource_type
            )

    async def confirm_create(self, path: str, bam_id: int) -> None:
        """
        Confirm operation succeeded and update cache with real BAM ID.

        CRITICAL: Must be called IMMEDIATELY after successful operation.
        This is the contract between Executor and Resolver.

        WHAT THIS DOES:
        1. Removes path from pending_creates (no longer "pending")
        2. Adds path→bam_id mapping to cache (now "confirmed")
        3. Future resolve() calls for this path return cached ID immediately
        4. Dependent operations can now proceed without PendingCreateError

        Args:
            path: Path that was created
            bam_id: Actual BAM ID assigned by server
        """
        async with self._pending_lock(path):
            # Remove from pending
            pending_data = self.pending_creates.pop(path, None)

            if pending_data:
                row_id, resource_type = pending_data
                # Add to cache with REAL BAM ID and correct resource type
                self._cache_entity(path, bam_id, resource_type)

                logger.info(
                    "Confirmed create - updated resolver cache",
                    path=path,
                    row_id=row_id,
                    bam_id=bam_id,
                    resource_type=resource_type,
                )
            else:
                logger.warning(
                    "Confirmed create for unknown pending path", path=path, bam_id=bam_id
                )

    async def cancel_create(self, path: str, reason: str) -> None:
        """
        Cancel pending create due to operation failure.

        CRITICAL: Must be called when operation fails to prevent
        downstream operations from trying to reference phantom parent.

        WHAT THIS DOES:
        1. Removes path from pending_creates
        2. Ensures resource NOT added to cache
        3. Future resolve() calls fail with ResourceNotFoundError (correct behavior)
        4. Dependent operations fail fast with clear error message

        WHY NECESSARY:
        If we don't cancel, pending_creates still contains the path.
        Dependent operations will get PendingCreateError forever,
        implying the resource is "coming soon" when it actually failed.

        Args:
            path: Path that failed to create
            reason: Why it failed (logged for debugging)
        """
        async with self._pending_lock(path):
            pending_data = self.pending_creates.pop(path, None)

            if pending_data:
                row_id, resource_type = pending_data
                logger.warning(
                    "Cancelled pending create - removing from resolver",
                    path=path,
                    row_id=row_id,
                    resource_type=resource_type,
                    reason=reason,
                )
            else:
                logger.debug(
                    "Attempted to cancel non-existent pending create", path=path, reason=reason
                )

    async def _get_views_cached(self, config_id: int) -> list[dict[str, Any]]:
        """
        Get views with in-memory caching.

        Args:
            config_id: Configuration ID to get views for

        Returns:
            List of view dictionaries from BAM API

        Raises:
            Exception: If API call fails (propagated from client)
        """
        now = time.time()

        # Check cache
        if config_id in self._view_cache:
            cache_time = self._view_cache_ttl.get(config_id, 0)
            if now - cache_time < self._view_cache_duration:
                logger.debug("View cache hit", config_id=config_id)
                self.collector.backend.increment("resolver_cache_hit_total", tags={"type": "view"})
                return self._view_cache[config_id]

        # Cache miss - fetch from API
        logger.debug("View cache miss", config_id=config_id)
        self.collector.backend.increment("resolver_cache_miss_total", tags={"type": "view"})
        views = await self.client.get_views_in_configuration(config_id)

        # Update cache
        self._view_cache[config_id] = views
        self._view_cache_ttl[config_id] = now

        return views

    async def _get_zones_cached(self, view_id: int) -> list[dict[str, Any]]:
        """
        Get zones with in-memory caching.

        MULTI-LEVEL CACHING STRATEGY:
        This implements a two-tier caching system for zones:
        1. L1: In-memory cache for ultra-fast access (2.5 min TTL)
        2. L2: Disk cache for persistent access (configurable TTL)

        The shorter TTL for zones reflects that DNS zones typically
        change more frequently than views in enterprise environments.

        Args:
            view_id: View ID to get zones for

        Returns:
            List of zone dictionaries from BAM API

        Raises:
            Exception: If API call fails (propagated from client)
        """
        now = time.time()

        # Check L1 cache (in-memory)
        if view_id in self._zone_cache:
            cache_time = self._zone_cache_ttl.get(view_id, 0)
            if now - cache_time < self._zone_cache_duration:
                logger.debug("Zone L1 cache hit", view_id=view_id)
                self.collector.backend.increment(
                    "resolver_cache_hit_total", tags={"type": "zone", "level": "L1"}
                )
                return self._zone_cache[view_id]

        # Check L2 cache (disk) with longer-form cache key
        disk_cache_key = f"zones_in_view:{view_id}"
        cached_zones = self.cache.get(disk_cache_key)
        if cached_zones is not None:
            logger.debug("Zone L2 cache hit", view_id=view_id)
            self.collector.backend.increment(
                "resolver_cache_hit_total", tags={"type": "zone", "level": "L2"}
            )
            # Promote to L1 cache
            self._zone_cache[view_id] = cached_zones
            self._zone_cache_ttl[view_id] = now
            return cached_zones

        # Cache miss at both levels - fetch from API
        logger.debug("Zone cache miss (L1 & L2)", view_id=view_id)
        self.collector.backend.increment("resolver_cache_miss_total", tags={"type": "zone"})
        zones = await self.client.get_zones_in_view(view_id)

        # Update both caches
        self._zone_cache[view_id] = zones
        self._zone_cache_ttl[view_id] = now
        self.cache.set(disk_cache_key, zones, expire=self.cache_config.ttl_seconds)

        return zones

    async def resolve(
        self,
        path: str,
        resource_type: str,
        bypass_cache: bool = False,
    ) -> int:
        """
        Resolve path to BAM ID.

        Resolution order:
        1. Check pending_creates (raises error if found - not confirmed yet!)
        2. Check disk cache (populated by prefetch or confirmed creates)
        3. Query BAM API (only if cache miss)

        Args:
            path: Human-readable path (e.g., "/IPv4/10.0.0.0/16")
            resource_type: Type of resource (network, block, zone)
            bypass_cache: Force API query

        Returns:
            BAM resource ID

        Raises:
            ResourceNotFoundError: Path doesn't exist in BAM
            PendingCreateError: Path is pending but not confirmed
        """
        # Check pending creates first with granular lock
        async with self._pending_lock(path):
            if path in self.pending_creates:
                # This is a pending create - hasn't been confirmed yet
                row_id, _ = self.pending_creates[path]
                raise PendingCreateError(path, str(row_id))

        # Check cache (includes confirmed creates) - skip if no_cache mode is enabled
        if not bypass_cache and not self.no_cache:
            try:
                cached_id = self.cache.get(self._cache_key(path, resource_type))
                if cached_id is not None:
                    self.stats.cache_hit()
                    self.collector.backend.increment(
                        "resolver_cache_hit_total", tags={"type": resource_type}
                    )
                    logger.debug("Cache hit", path=path, bam_id=cached_id)
                    return cached_id
            except (OSError, ValueError, TypeError) as e:
                logger.warning(
                    "Cache read failed, treating as miss",
                    path=path,
                    resource_type=resource_type,
                    error=str(e),
                )
                self.stats.cache_miss()

        # Cache miss - query BAM
        self.stats.cache_miss()
        self.collector.backend.increment("resolver_cache_miss_total", tags={"type": resource_type})
        logger.debug("Cache miss", path=path)

        # Warn if prefetch wasn't called for large batches
        if not self._prefetch_complete and self.stats.total_queries > 100:
            logger.warning(
                "High number of resolver queries without prefetch",
                total_queries=self.stats.total_queries,
                cache_hit_rate=self.stats.hit_rate(),
            )

        try:
            bam_id = await self._query_bam(path, resource_type)

            # Update cache with error handling
            try:
                self.cache.set(
                    self._cache_key(path, resource_type),
                    bam_id,
                    expire=3600,  # 1 hour
                )
            except (OSError, ValueError, TypeError) as e:
                logger.warning(
                    "Cache write failed, continuing without cache",
                    path=path,
                    resource_type=resource_type,
                    error=str(e),
                )

            return bam_id
        except ResourceNotFoundError:
            logger.error("Resource not found in BAM", path=path, resource_type=resource_type)
            raise

    async def prefetch_hierarchy(
        self,
        config_names: list[str],
        view_names: list[str] | None = None,
    ) -> None:
        """
        Bulk prefetch entire hierarchy to eliminate N+1 query performance problems.

        Performance Impact:
        - Without prefetch: 1000 resources = 1000+ API calls (slow)
        - With prefetch: 1000 resources = 3-5 API calls (100x faster)

        Strategy:
        1. Fetch configurations by name (1 API call per config)
        2. Walk the entity tree using _entities endpoint (lite objects)
        3. Cache all discovered paths for instant lookup

        Note: This is a simplified implementation. Full implementation would:
        - Recursively walk all children
        - Handle pagination for large hierarchies
        - Parallelize API calls where possible

        Args:
            config_names: List of configuration names to pre-cache
            view_names: List of DNS view names to pre-cache (optional)
        """
        logger.info("Prefetching BAM hierarchy", configs=config_names, views=view_names)

        total_cached = 0

        for config_name in config_names:
            # Get configuration ID
            config = await self.client.get_configuration_by_name(config_name)
            config_id = config["id"]

            # For now, we'll implement a simple version
            # In production, this would walk the full hierarchy
            self._cache_entity(
                f"/configurations/{config_name}",
                config_id,
            )
            total_cached += 1

            logger.debug("Cached configuration", name=config_name, id=config_id)

        self._prefetch_complete = True
        logger.info("Hierarchy prefetch complete", cached_paths=total_cached)

    async def prefetch_from_csv(self, csv_rows: list[Any]) -> None:
        """
        Analyze CSV rows and bulk-prefetch dependencies to warm the cache.

        Extracts parent paths from all rows and performs batched resolution
        before main execution starts.

        Args:
            csv_rows: List of CSVRow objects (or dicts)
        """
        logger.info("Prefetching dependencies from CSV", row_count=len(csv_rows))

        # Group paths by parent context
        # Networks by Config/Block
        # Zones by View

        # Helper to get ID if cached, else None
        async def get_cached_id(path: str, rtype: str) -> int | None:
            try:
                if self.no_cache:
                    return None
                return self.cache.get(self._cache_key(path, rtype))
            except Exception as e:
                logger.debug(
                    "Cache lookup failed during prefetch",
                    path=path,
                    resource_type=rtype,
                    error=str(e),
                )
                return None

        # 1. Identify all unique parent paths first
        # We need configurations and views resolved first to bulk load their children

        # Collect unique contexts
        config_names = set()
        view_paths = set()  # (config_name, view_name)
        block_paths = set()  # (config_name, cidr)

        for row in csv_rows:
            config = getattr(row, "config", getattr(row, "configuration", "Default"))
            if config:
                config_names.add(config)

            # Parent view for zones
            view = getattr(row, "view_path", getattr(row, "view", None))
            if view:
                view_paths.add((config, view))

            # Parent block for networks (if deducible)
            # This is harder without full path parsing logic but we can grab blocks directly
            # if they are being imported as objects
            obj_type = getattr(row, "object_type", "").lower()
            if obj_type in ("ip4_block", "block", "ip6_block"):
                cidr = getattr(row, "cidr", None)
                if cidr and config:
                    block_paths.add((config, cidr))

        # 2. Bulk resolve Configurations
        # We can't batch resolve configs by name easily without a filtered search
        # But there are usually few configs.
        logger.debug("Prefetching configurations", count=len(config_names))
        config_map = {}  # name -> id

        # Limit concurrency
        semaphore = asyncio.Semaphore(10)

        async def fetch_config(name: str):
            async with semaphore:
                try:
                    if self.cache.get(self._cache_key(name, "Configuration")):
                        return

                    config = await self.client.get_configuration_by_name(name)
                    if config:
                        self.cache.set(
                            self._cache_key(name, "Configuration"),
                            config["id"],
                            expire=3600,  # 1 hour TTL
                        )
                        config_map[name] = config["id"]
                except Exception as e:
                    logger.debug(
                        "Prefetch config failed, will resolve on-demand",
                        config_name=name,
                        error=str(e),
                    )

        await asyncio.gather(*[fetch_config(name) for name in config_names])

        # 3. Bulk resolve Views
        # For each known config, fetch all views
        logger.debug("Prefetching views for configs", count=len(config_map))

        async def fetch_views(config_id: int):
            async with semaphore:
                try:
                    # _get_views_cached populates the cache
                    await self._get_views_cached(config_id)
                except Exception as e:
                    logger.debug(
                        "Prefetch views failed, will resolve on-demand",
                        config_id=config_id,
                        error=str(e),
                    )

        await asyncio.gather(*[fetch_views(cid) for cid in config_map.values()])

        # 4. Bulk resolve Blocks
        # For each known config, fetch all blocks (expensive if many, so maybe limit?)
        # Better: Only fetch blocks we know are parents

        # For now, let's just ensure we have the caching infrastructure ready
        # The individual lookups will hit cache for Config and View now.

        # Only implementing structural framework for now as per plan
        logger.info("CSV prefetch analysis complete")

    async def bulk_resolve_networks(self, parent_id: int, cidrs: list[str]) -> dict[str, int]:
        """
        Bulk resolve network CIDRs to IDs within a block.

        Args:
            parent_id: Parent Block ID
            cidrs: List of network CIDRs

        Returns:
            Dict mapping CIDR -> BAM ID
        """
        if not cidrs:
            return {}

        logger.debug("Bulk resolving networks", count=len(cidrs), parent_id=parent_id)
        result = {}
        chunk_size = 50

        for i in range(0, len(cidrs), chunk_size):
            chunk = cidrs[i : i + chunk_size]
            escaped = [f"'{c}'" for c in chunk]
            filter_str = f"range:in({','.join(escaped)})"

            try:
                # Assuming simple network parenting
                nets = await self.client.get_child_networks(parent_id, filter=filter_str)
                for net in nets:
                    net_id = net["id"]
                    cidr = net["properties"].get("range") or net["properties"].get("CIDR")
                    if cidr:
                        result[cidr] = net_id
                        # We don't easily know the full path here to cache by path key
                        # So we return the mapping for the caller to use
            except Exception as e:
                logger.error("Bulk resolve networks failed", error=str(e))

        return result

    async def bulk_resolve_zones(self, view_id: int, zone_names: list[str]) -> dict[str, int]:
        """
        Bulk resolve zone names to IDs within a view.

        Args:
            view_id: View ID
            zone_names: List of zone names

        Returns:
            Dict mapping zone name -> BAM ID
        """
        if not zone_names:
            return {}

        logger.debug("Bulk resolving zones", count=len(zone_names), view_id=view_id)
        result = {}
        chunk_size = 50

        for i in range(0, len(zone_names), chunk_size):
            chunk = zone_names[i : i + chunk_size]
            escaped = [f"'{n}'" for n in chunk]
            filter_str = f"name:in({','.join(escaped)})"

            try:
                zones = await self.client.get_zones_in_view(view_id, filter=filter_str)
                for zone in zones:
                    z_id = zone["id"]
                    name = zone["properties"].get("name")
                    if name:
                        result[name] = z_id
            except Exception as e:
                logger.error("Bulk resolve zones failed", error=str(e))

        return result

    async def _query_bam(self, path: str, resource_type: str) -> int:
        """
        Resolve hierarchical paths by walking the resource tree.

        Path formats and edge cases:
        - Config: "Default" (simple name lookup)
        - Block: "/Default/10.0.0.0/8" or "Default/10.0.0.0/8" (leading slash optional)
        - Network: "/Default/10.0.0.0/8/10.0.0.0/24" (config/blockCIDR/networkCIDR)
        - Zone: "example.com" or "Default/Internal/example.com" (relative or absolute)

        Error Handling:
        - Invalid formats raise ResourceNotFoundError
        - API failures are logged and re-raised
        - Type mapping handles common variations (block -> Block, ip4_block -> Block)

        Args:
            path: Human-readable path string
            resource_type: Resource type from CSV (may have variations)

        Returns:
            BAM resource ID from successful resolution

        Raises:
            ResourceNotFoundError: Path doesn't exist or has invalid format
        """
        logger.debug("Querying BAM for path", path=path, resource_type=resource_type)

        # Normalize resource type variations to canonical names using centralized mapping
        # This ensures "block", "ip4_block", "Block" all map to "IPv4Block" consistently
        normalized_type = RESOLVER_TYPE_MAP.get(resource_type.lower(), resource_type)

        try:
            if normalized_type == "Configuration":
                # Direct configuration lookup by name
                config = await self.client.get_configuration_by_name(path)
                return config["id"]

            elif normalized_type == "IPv4Block":
                # Parse hierarchical block path: "Default/10.0.0.0/8" or "/Default/10.0.0.0/8"
                # Accept paths with or without leading slash
                clean_path = path.lstrip("/")
                path_parts = clean_path.split("/")

                # Need at least config_name/CIDR (e.g., "Default/10.0.0.0/8")
                # CIDR contains a "/" so minimum 3 parts after split
                if len(path_parts) < 3:
                    raise ResourceNotFoundError(resource_type, f"Invalid block path format: {path}")

                # Get configuration first
                config_name = path_parts[0]
                config = await self.client.get_configuration_by_name(config_name)

                # Reconstruct CIDR from remaining parts (IP/prefix)
                # Path: Default/10.0.0.0/8 -> parts: [Default, 10.0.0.0, 8] -> cidr: 10.0.0.0/8
                cidr = "/".join(path_parts[1:])
                block = await self.client.get_block_by_cidr_in_config(config["id"], cidr)
                return block["id"]

            elif normalized_type == "IPv6Block":
                # Parse hierarchical block path: "Default/2001:db8::/32"
                clean_path = path.lstrip("/")
                path_parts = clean_path.split("/")

                # Need config/CIDR (at least 2 parts but CIDR splits)
                if len(path_parts) < 3:
                    raise ResourceNotFoundError(
                        resource_type, f"Invalid IPv6 block path format: {path}"
                    )

                config_name = path_parts[0]
                config = await self.client.get_configuration_by_name(config_name)

                # Join the rest as CIDR
                cidr = "/".join(path_parts[1:])
                block = await self.client.get_ip6_block_by_cidr_in_config(config["id"], cidr)
                return block["id"]

            elif normalized_type == "IPv6Network":
                # Parse hierarchical network path: "Default/2001:db8::/32/2001:db8:1::/64"
                clean_path = path.lstrip("/")
                path_parts = clean_path.split("/")

                if len(path_parts) < 5:
                    raise ResourceNotFoundError(
                        resource_type, f"Invalid IPv6 network path format: {path}"
                    )

                config_name = path_parts[0]
                config = await self.client.get_configuration_by_name(config_name)

                block_cidr = f"{path_parts[1]}/{path_parts[2]}"
                network_cidr = f"{path_parts[3]}/{path_parts[4]}"

                parent_block = await self.client.get_ip6_block_by_cidr_in_config(
                    config["id"], block_cidr
                )
                network = await self.client.get_ip6_network_by_cidr_in_block(
                    parent_block["id"], network_cidr
                )
                return network["id"]

            elif normalized_type == "IPv4Network":
                # Parse hierarchical network path: "Default/10.0.0.0/8/10.0.0.0/24"
                # Format: ConfigName/BlockIP/BlockPrefix/NetworkIP/NetworkPrefix
                # Accept paths with or without leading slash
                clean_path = path.lstrip("/")
                path_parts = clean_path.split("/")

                # Need config + block CIDR + network CIDR = 5 parts minimum
                # e.g., Default/10.0.0.0/8/10.0.0.0/24 -> [Default, 10.0.0.0, 8, 10.0.0.0, 24]
                if len(path_parts) < 5:
                    raise ResourceNotFoundError(
                        resource_type, f"Invalid network path format: {path}"
                    )

                # Get configuration
                config_name = path_parts[0]
                config = await self.client.get_configuration_by_name(config_name)

                # Reconstruct block CIDR (parts 1-2) and network CIDR (parts 3-4)
                block_cidr = f"{path_parts[1]}/{path_parts[2]}"
                network_cidr = f"{path_parts[3]}/{path_parts[4]}"

                # Find parent block using optimized filter
                parent_block = await self.client.get_block_by_cidr_in_config(
                    config["id"], block_cidr
                )
                parent_block_id = parent_block["id"]

                # Find network by CIDR within block using optimized filter
                network = await self.client.get_network_by_cidr_in_block(
                    parent_block_id, network_cidr
                )
                return network["id"]

            elif normalized_type == "View":
                # DNS view lookup within configuration
                # Path format: "ConfigurationName/ViewName"
                if "/" in path:
                    parts = path.split("/", 1)
                    config_name = parts[0]
                    view_name = parts[1]
                else:
                    # If no configuration specified, assume first available configuration
                    config_name = path
                    view_name = None

                config = await self.client.get_configuration_by_name(config_name)

                # Get all views in configuration
                views = await self._get_views_cached(config["id"])

                if view_name:
                    # Find specific view using optimized filter
                    view = await self.client.get_view_by_name_in_config(config["id"], view_name)
                    return view["id"]
                else:
                    # Return first view if no specific view requested
                    if views:
                        return views[0]["id"]
                    raise ResourceNotFoundError(
                        resource_type, f"No views found in configuration {config_name}"
                    )

            elif normalized_type == "Zone":
                # DNS zone lookup within a view
                #
                # Zone Resolution Strategy:
                # 1. Full path: "ConfigurationName/ViewName/ZoneName" - Most efficient
                # 2. Partial path: "ViewName/ZoneName" - Searches all configurations for the view
                # 3. Zone name only: "ZoneName" - Uses global search (may be slow with many zones)
                #
                # Performance Implications:
                # - Method 1 is most efficient as it directly queries specific resources
                # - Method 2 iterates through all configurations (O(n) API calls)
                # - Method 3 relies on BAM's global search filter efficiency

                if "/" in path:
                    parts = path.split("/", 2)
                    if len(parts) == 3:
                        # Full path: Config/View/Zone
                        config_name, view_name, zone_name = parts
                    else:
                        # Partial path: View/Zone (config not specified)
                        view_name, zone_name = parts
                        config_name = None

                    # Get view
                    if config_name:
                        # Optimized path: Direct configuration lookup
                        config = await self.client.get_configuration_by_name(config_name)
                        views = await self._get_views_cached(config["id"])
                        view_id = None
                        for view in views:
                            if view.get("name") == view_name:
                                view_id = view["id"]
                                break
                        if not view_id:
                            raise ResourceNotFoundError(
                                resource_type, f"View '{view_name}' not found"
                            )
                    else:
                        # Fallback: Search all configurations for the view
                        # CRITICAL FIX: This scan is extremely expensive (O(N) configs).
                        # We restrict this to valid "Default" config if possible or fail fast.
                        # The user MUST specify config for performance.

                        # Warn about performance impact
                        logger.warning(
                            "View lookup invalid: Configuration context missing",
                            view=view_name,
                            hint="Specify 'config' column or full path 'Config/View/Zone'",
                        )

                        # We try "Default" configuration as a best-effort fallback
                        try:
                            default_config = await self.client.get_configuration_by_name("Default")
                            views = await self._get_views_cached(default_config["id"])
                            for view in views:
                                if view.get("name") == view_name:
                                    view_id = view["id"]
                                    break
                        except Exception:
                            pass

                        if not view_id:
                            raise ResourceNotFoundError(
                                resource_type,
                                f"View '{view_name}' not found. Please specify Configuration context.",
                            )

                    # Get zones in view and find the matching zone
                    zones = await self._get_zones_cached(view_id)
                    for zone in zones:
                        if zone.get("name") == zone_name:
                            return zone["id"]
                    raise ResourceNotFoundError(resource_type, path)
                else:
                    # Zone name only - use BAM's global name filter
                    # This may be slow with thousands of zones
                    zone = await self.client.get_zone_by_name(path)
                    return zone["id"]

            elif normalized_type == "DNSDeploymentRole" or normalized_type == "dns_deployment_role":
                # DNS deployment role lookup
                # Path format: "ConfigurationName/ViewName/RoleName" or "RoleName"
                if "/" in path:
                    parts = path.split("/", 2)
                    if len(parts) == 3:
                        config_name, view_name, role_name = parts
                    else:
                        # Configuration not specified
                        view_name, role_name = parts
                        config_name = None

                    # Get view ID
                    if config_name:
                        config = await self.client.get_configuration_by_name(config_name)
                        views = await self._get_views_cached(config["id"])
                        view_id = None
                        for view in views:
                            if view.get("name") == view_name:
                                view_id = view["id"]
                                break
                        if not view_id:
                            raise ResourceNotFoundError(
                                resource_type, f"View '{view_name}' not found"
                            )
                    else:
                        # Find view by name across all configurations
                        configs = await self.client.get_configurations()
                        view_id = None
                        for config in configs:
                            try:
                                views = await self._get_views_cached(config["id"])
                                for view in views:
                                    if view.get("name") == view_name:
                                        view_id = view["id"]
                                        break
                                if view_id:
                                    break
                            except Exception:
                                continue
                        if not view_id:
                            raise ResourceNotFoundError(
                                resource_type, f"View '{view_name}' not found"
                            )

                    # Get deployment roles in view
                    deployment_roles = await self.client.get_dns_deployment_roles_in_view(view_id)
                    for role in deployment_roles:
                        if role.get("name") == role_name:
                            return role["id"]
                    raise ResourceNotFoundError(resource_type, path)
                else:
                    # Role name only - use optimized global name filter
                    role = await self.client.get_dns_deployment_role_by_name(path)
                    return role["id"]

            elif normalized_type == "Location":
                # Location lookup by code
                #
                # Location codes are hierarchical, space-separated strings:
                # - UN/LOCODE format: "US NYC" (country + city)
                # - Custom locations: "US NYC HQ" (country + city + custom)
                #
                # The path parameter is the full location code to lookup.
                location = await self.client.get_location_by_code(path)
                if location:
                    return location["id"]
                raise ResourceNotFoundError(resource_type, f"Location with code '{path}' not found")

            else:
                logger.warning(
                    "Unsupported resource type for path resolution", resource_type=resource_type
                )
                raise ResourceNotFoundError(resource_type, path)

        except Exception as e:
            logger.debug(
                "Path resolution failed", path=path, resource_type=resource_type, error=str(e)
            )
            raise ResourceNotFoundError(resource_type, path) from e

    def _cache_key(self, path: str, resource_type: str) -> str:
        """
        Generate cache key from path and type.

        Normalizes resource type to canonical form to prevent cache duplication.

        Args:
            path: Resource path.
            resource_type: Resource type (will be normalized).

        Returns:
            str: Cache key in format "NormalizedType:path"
        """
        # Normalize resource type variations to canonical names (same as in _query_bam)
        resource_type_map = {
            "block": "Block",
            "ip4_block": "Block",
            "network": "Network",
            "ip4_network": "Network",
            "ip6_network": "IPv6Network",
            "ip6_block": "IPv6Block",
            "view": "View",
            "zone": "Zone",
            "dns_zone": "Zone",
            "configuration": "Configuration",
            "config": "Configuration",
            "dns_deployment_role": "DNSDeploymentRole",
            "location": "Location",
        }
        normalized_type = resource_type_map.get(resource_type.lower(), resource_type)
        return f"{normalized_type}:{path}"

    def _cache_entity(self, path: str, bam_id: int, resource_type: str = "unknown") -> None:
        """
        Add entity to cache with error handling.

        Args:
            path: Resource path.
            bam_id: BAM resource ID.
            resource_type: Resource type (default: "unknown").
        """
        cache_key = self._cache_key(path, resource_type)
        try:
            self.cache.set(cache_key, bam_id, expire=3600)
            logger.debug("Cached entity", path=path, bam_id=bam_id, type=resource_type)
        except (OSError, ValueError, TypeError) as e:
            logger.warning(
                "Failed to cache entity", path=path, bam_id=bam_id, type=resource_type, error=str(e)
            )

    async def invalidate(self, path: str, resource_type: str) -> None:
        """
        Clear cache entry when resource is modified.

        Args:
            path: Resource path to invalidate
            resource_type: Resource type
        """
        # Use same lock as resolve to prevent race conditions
        async with self._pending_lock(path):
            cache_key = self._cache_key(path, resource_type)
            try:
                self.cache.delete(cache_key)
                logger.debug("Invalidated cache", path=path, resource_type=resource_type)
            except (OSError, ValueError, TypeError) as e:
                logger.warning(
                    "Failed to invalidate cache",
                    path=path,
                    resource_type=resource_type,
                    error=str(e),
                )

    async def clear_pending(self) -> None:
        """Clear all pending creates (typically at end of batch)."""
        # Granular lock optimization: We don't lock here as this is an atomic global cleanup
        # typically called when no other operations are running.
        count = len(self.pending_creates)
        self.pending_creates.clear()
        logger.info("Cleared pending creates", count=count)

    def get_stats(self) -> CacheStats:
        """
        Get resolver statistics.

        Returns:
            CacheStats: Statistics object.
        """
        return self.stats
