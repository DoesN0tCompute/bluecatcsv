"""
Bulk validation engine for detecting issues before import logic runs.
"""

from dataclasses import dataclass, field

import structlog

from ..bam.client import BAMClient
from ..models.csv_row import (
    CSVRow,
    DNSZoneRow,
    HostRecordRow,
    IP4BlockRow,
    IP4NetworkRow,
)

logger = structlog.get_logger(__name__)


@dataclass
class ValidationError:
    """Represents a single validation error found in a CSV row."""

    row_id: str
    field: str
    message: str
    severity: str = "ERROR"  # ERROR, WARNING

    def __str__(self) -> str:
        return f"[{self.severity}] Row {self.row_id} ({self.field}): {self.message}"


@dataclass
class ValidationReport:
    """Collection of validation errors and warnings."""

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    summary: dict[str, int] = field(
        default_factory=lambda: {"errors": 0, "warnings": 0, "checked": 0}
    )

    @property
    def is_valid(self) -> bool:
        """Returns True if there are no errors (warnings are allowed)."""
        return len(self.errors) == 0

    def add_error(self, row_id: str, field_name: str, message: str) -> None:
        self.errors.append(ValidationError(row_id, field_name, message, "ERROR"))
        self.summary["errors"] += 1

    def add_warning(self, row_id: str, field_name: str, message: str) -> None:
        self.warnings.append(ValidationError(row_id, field_name, message, "WARNING"))
        self.summary["warnings"] += 1


class BulkValidator:
    """
    Performs bulk pre-flight checks against BAM to catch common issues
    before the slower import process starts.
    """

    def __init__(self, client: BAMClient):
        self.client = client
        self.report = ValidationReport()

    async def validate(self, rows: list[CSVRow]) -> ValidationReport:
        """
        Run all validation checks on the provided CSV rows.
        """
        self.report = ValidationReport()
        self.report.summary["checked"] = len(rows)

        logger.info("Starting bulk validation", row_count=len(rows))

        # Group rows by type for efficient checking
        networks = [r for r in rows if isinstance(r, IP4NetworkRow)]
        blocks = [r for r in rows if isinstance(r, IP4BlockRow)]
        zones = [r for r in rows if isinstance(r, DNSZoneRow)]
        [
            r for r in rows if isinstance(r, HostRecordRow)
        ]  # And others if we support generic records

        # 1. Check for Duplicate CIDRs (Networks/Blocks)
        if networks or blocks:
            await self._check_duplicate_cidrs(networks + blocks)

        # 2. Check for Duplicate Names (Zones/Records)
        if zones:
            await self._check_duplicate_zone_names(zones)

        # 3. Parent Existence Checks - deliberately omitted here.
        # The Resolver performs full parent path resolution during import.
        # BulkValidator focuses on fast, standalone checks (CIDRs, names).

        logger.info(
            "Bulk validation complete",
            errors=self.report.summary["errors"],
            warnings=self.report.summary["warnings"],
        )

        return self.report

    async def _resolve_config_ids(self, rows: list[CSVRow]) -> dict[str, int]:
        """Resolve configuration names to IDs for all rows using parallel requests."""
        import asyncio

        config_map = {}
        unique_configs = list({r.config for r in rows if r.config})

        if not unique_configs:
            return config_map

        # PERF: Use asyncio.gather for parallel lookups instead of sequential
        async def fetch_config(name: str) -> tuple[str, int | None]:
            try:
                cfg = await self.client.get_configuration_by_name(name)
                if cfg and "id" in cfg:
                    return (name, cfg["id"])
            except Exception as e:
                logger.warning("Failed to resolve configuration", name=name, error=str(e))
            return (name, None)

        results = await asyncio.gather(*[fetch_config(name) for name in unique_configs])

        for name, config_id in results:
            if config_id is not None:
                config_map[name] = config_id

        return config_map

    async def _resolve_view_ids(self, rows: list[DNSZoneRow]) -> dict[str, int]:
        """Resolve view names to IDs for zone rows."""
        import asyncio

        view_map = {}

        # We need both config and view path to resolve a view
        # Create unique keys: (config_name, view_path)
        unique_views = {(r.config, r.view_path) for r in rows if r.config and r.view_path}

        if not unique_views:
            return view_map

        # First resolve configs since we need config_id to find views
        # Note: _resolve_config_ids uses just config names
        config_rows = [type("ConfigRow", (), {"config": c})() for c, _ in unique_views]
        config_map = await self._resolve_config_ids(config_rows)

        async def fetch_view(config_name: str, view_path: str) -> tuple[str, str, int | None]:
            config_id = config_map.get(config_name)
            if not config_id:
                return (config_name, view_path, None)

            try:
                # Use client method to find view in config
                view = await self.client.get_view_by_name_in_config(config_id, view_path)
                if view and "id" in view:
                    return (config_name, view_path, view["id"])
            except Exception as e:
                logger.debug(
                    "Failed to resolve view", config=config_name, view=view_path, error=str(e)
                )

            return (config_name, view_path, None)

        results = await asyncio.gather(*[fetch_view(c, v) for c, v in unique_views])

        for config_name, view_path, view_id in results:
            if view_id is not None:
                # Key the map by "config_name/view_path"
                view_map[f"{config_name}/{view_path}"] = view_id

        return view_map

    async def _check_duplicate_cidrs(self, rows: list[CSVRow]) -> None:
        """
        Check if networks/blocks with action='create' already exist.

        PERF: Uses bulk API filter with range:in() instead of per-CIDR queries.
        """
        import asyncio

        create_rows = [r for r in rows if r.action == "create"]
        if not create_rows:
            return

        # 1. Resolve Config IDs (already optimized with asyncio.gather)
        config_map = await self._resolve_config_ids(create_rows)

        # 2. Group CIDRs by config for bulk checking
        networks_by_config: dict[int, list[tuple[CSVRow, str]]] = {}
        blocks_by_config: dict[int, list[tuple[CSVRow, str]]] = {}

        for row in create_rows:
            if not isinstance(row, IP4NetworkRow | IP4BlockRow) or not row.cidr:
                continue

            config_id = config_map.get(row.config)
            if not config_id:
                self.report.add_warning(
                    str(row.row_id),
                    "config",
                    f"Configuration '{row.config}' not found. Skipping duplicate check.",
                )
                continue

            if isinstance(row, IP4NetworkRow):
                if config_id not in networks_by_config:
                    networks_by_config[config_id] = []
                networks_by_config[config_id].append((row, row.cidr))
            elif isinstance(row, IP4BlockRow):
                if config_id not in blocks_by_config:
                    blocks_by_config[config_id] = []
                blocks_by_config[config_id].append((row, row.cidr))

        # 3. Bulk check networks per config using API filter
        async def check_networks_bulk(config_id: int, items: list[tuple[CSVRow, str]]) -> None:
            if not items:
                return

            # Build filter: range:in('10.0.0.0/8', '10.1.0.0/16', ...)
            cidrs = [cidr for _, cidr in items]
            cidr_list = ", ".join([f"'{c}'" for c in cidrs])
            filter_str = f"range:in({cidr_list})"

            try:
                # Query all networks matching any of the CIDRs in one request
                existing = await self.client.get(
                    f"/configurations/{config_id}/networks",
                    params={"filter": filter_str, "fields": "range"},
                )

                # Build set of existing CIDRs for O(1) lookup
                existing_cidrs = set()
                if existing and "data" in existing:
                    for net in existing["data"]:
                        if "range" in net:
                            existing_cidrs.add(net["range"])

                # Report errors for duplicates
                for row, cidr in items:
                    if cidr in existing_cidrs:
                        self.report.add_error(
                            str(row.row_id),
                            "cidr",
                            f"Network {cidr} already exists in configuration.",
                        )
            except Exception as e:
                # Fallback: if bulk filter fails, log warning but don't block
                logger.warning("Bulk network check failed, skipping", error=str(e))

        async def check_blocks_bulk(config_id: int, items: list[tuple[CSVRow, str]]) -> None:
            if not items:
                return

            cidrs = [cidr for _, cidr in items]
            cidr_list = ", ".join([f"'{c}'" for c in cidrs])
            filter_str = f"range:in({cidr_list})"

            try:
                existing = await self.client.get(
                    f"/configurations/{config_id}/blocks",
                    params={"filter": filter_str, "fields": "range"},
                )

                existing_cidrs = set()
                if existing and "data" in existing:
                    for blk in existing["data"]:
                        if "range" in blk:
                            existing_cidrs.add(blk["range"])

                for row, cidr in items:
                    if cidr in existing_cidrs:
                        self.report.add_error(
                            str(row.row_id),
                            "cidr",
                            f"Block {cidr} already exists in configuration.",
                        )
            except Exception as e:
                logger.warning("Bulk block check failed, skipping", error=str(e))

        # 4. Execute all bulk checks in parallel
        tasks = []
        for config_id, items in networks_by_config.items():
            tasks.append(check_networks_bulk(config_id, items))
        for config_id, items in blocks_by_config.items():
            tasks.append(check_blocks_bulk(config_id, items))

        if tasks:
            await asyncio.gather(*tasks)

    async def _check_duplicate_zone_names(self, rows: list[DNSZoneRow]) -> None:
        """Check if zones to be created already exist."""
        import asyncio

        create_rows = [r for r in rows if r.action == "create"]
        if not create_rows:
            return

        # 1. Resolve View IDs
        view_map = await self._resolve_view_ids(create_rows)

        # 2. Group Zones by View ID
        zones_by_view: dict[int, list[tuple[DNSZoneRow, str]]] = {}

        for row in create_rows:
            if not row.zone_name or not row.config or not row.view_path:
                continue

            view_key = f"{row.config}/{row.view_path}"
            view_id = view_map.get(view_key)

            if not view_id:
                # Skip if view not found (will be caught during import execution)
                continue

            if view_id not in zones_by_view:
                zones_by_view[view_id] = []
            zones_by_view[view_id].append((row, row.zone_name))

        # 3. Bulk check zones per view
        async def check_zones_bulk(view_id: int, items: list[tuple[DNSZoneRow, str]]) -> None:
            if not items:
                return

            names = [name for _, name in items]

            # BAM doesn't support generic name:in() filter easily for zones?
            # Or maybe it does. Let's try name:in().
            # If not, we fall back to parallel individual checks or get all zones in view (risky if many).
            # Let's try name:in(...)
            name_list = ", ".join([f"'{n}'" for n in names])
            filter_str = f"name:in({name_list})"

            try:
                existing = await self.client.get(
                    f"/views/{view_id}/zones", params={"filter": filter_str, "fields": "name"}
                )

                existing_names = set()
                if existing and "data" in existing:
                    for zone in existing["data"]:
                        if "name" in zone:
                            existing_names.add(zone["name"])

                for row, name in items:
                    if name in existing_names:
                        self.report.add_error(
                            str(row.row_id),
                            "zone_name",
                            f"Zone '{name}' already exists in view '{row.view_path}'.",
                        )
            except Exception as e:
                # If bulk filter is not supported/fails, we could fallback to individual checks
                logger.debug(
                    "Bulk zone check failed, falling back to individual checks", error=str(e)
                )
                # Fallback implementation
                for row, name in items:
                    try:
                        # Use client wrapper if exists, or direct query
                        # client.get_zone_by_fqdn(view_id, name)
                        z = await self.client.get_zone_by_fqdn(view_id, name)
                        if z:
                            self.report.add_error(
                                str(row.row_id),
                                "zone_name",
                                f"Zone '{name}' already exists in view '{row.view_path}'.",
                            )
                    except Exception:
                        pass  # Likely 404 not found, which is good

        tasks = []
        for view_id, items in zones_by_view.items():
            tasks.append(check_zones_bulk(view_id, items))

        if tasks:
            await asyncio.gather(*tasks)
