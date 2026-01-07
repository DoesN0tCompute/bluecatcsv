"""Export module for extracting BlueCat resources to CSV format."""

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from ..bam.client import BAMClient

logger = structlog.get_logger(__name__)


class BlueCatExporter:
    """
    Export BlueCat Address Manager resources to CSV format.

    Supports scoped exports of networks, blocks, and zones with automatic
    UDF discovery and hierarchical child resource fetching.
    """

    def __init__(self, client: BAMClient, allow_formulas: bool = False):
        """
        Initialize exporter with BAM client.

        Args:
            client: Authenticated BAM API client
            allow_formulas: Whether to allow CSV formulas (default: False)
        """
        self.client = client
        self.allow_formulas = allow_formulas
        self.discovered_udfs: set[str] = set()
        self.exported_resources: list[dict[str, Any]] = []

    async def export_network(
        self,
        network_identifier: str | int,
        config_id: int | None = None,
        include_children: bool = True,
        include_addresses: bool = True,
        action: str = "update",
        filter_str: str | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Export a network and optionally its children.

        Args:
            network_identifier: Network ID or CIDR notation
            config_id: Configuration ID (required if using CIDR)
            include_children: Include child networks
            include_addresses: Include IP addresses
            action: Default action for resources (create or update)

        Returns:
            List of resource dictionaries ready for CSV export
        """
        logger.info(
            "Exporting network", identifier=network_identifier, include_children=include_children
        )

        # Fetch the network
        if isinstance(network_identifier, int):
            # Filtering on single get by ID is usually not supported/useful, but keeping signature consistent
            network = await self.client.get_network_by_id(network_identifier)
        else:
            if not config_id:
                raise ValueError("config_id is required when using CIDR notation")
            # If we were using get_entity_by_name/cidr, filtering might irrelevant for a specific fetch
            # But if the user wants to export a LIST of networks based on filter, that's a different method.
            # The current CLI structure asks for a specific network (ID or CIDR).
            # If the user passed a filter, they probably want to filter the CHILDREN or the ADDRESSES.
            # However, the task implies generic filtering.
            # Let's apply filtering to the children fetching/address fetching if implied.

            # WAIT: The client.get_network_by_cidr doesn't take filters.
            # The Requirement says: "Export only static IPs in Subnet X".
            # So `filter` applies to the *contents* (addresses/children).

            network = await self.client.get_network_by_cidr(config_id, network_identifier)

        # Export the network itself
        await self._export_network_resource(network, action)

        # Recursively export children if requested
        if include_children:
            await self._export_network_hierarchy(
                network["id"],
                include_addresses,
                action,
                filter_str=filter_str,
                fields=fields,
                limit=limit,
                order_by=order_by,
            )

        return self.exported_resources

    async def export_block(
        self,
        block_id: int,
        include_children: bool = True,
        include_addresses: bool = True,
        action: str = "update",
        filter_str: str | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Export a block and all its children (blocks and networks).

        Args:
            block_id: Block ID
            include_children: Include child blocks and networks
            include_addresses: Include IP addresses in networks
            action: Default action for resources (create or update)

        Returns:
            List of resource dictionaries ready for CSV export
        """
        logger.info("Exporting block", block_id=block_id, include_children=include_children)

        # Fetch the block
        block = await self.client.get_block_by_id(block_id)

        # Export the block itself
        await self._export_block_resource(block, action)

        # Recursively export children if requested
        if include_children:
            await self._export_block_hierarchy(
                block_id,
                include_addresses,
                action,
                filter_str=filter_str,
                fields=fields,
                limit=limit,
                order_by=order_by,
            )

        return self.exported_resources

    async def export_zone(
        self,
        zone_identifier: str | int,
        view_id: int | None = None,
        include_children: bool = True,
        include_records: bool = True,
        action: str = "update",
        filter_str: str | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Export a DNS zone and optionally its children.

        Args:
            zone_identifier: Zone ID or FQDN
            view_id: View ID (required if using FQDN)
            include_children: Include child zones
            include_records: Include DNS resource records
            action: Default action for resources (create or update)

        Returns:
            List of resource dictionaries ready for CSV export
        """
        logger.info("Exporting zone", identifier=zone_identifier, include_children=include_children)

        # Fetch the zone
        if isinstance(zone_identifier, int):
            zone = await self.client.get_zone_by_id(zone_identifier)
        else:
            if not view_id:
                raise ValueError("view_id is required when using FQDN")
            zone = await self.client.get_zone_by_fqdn(view_id, zone_identifier)

        # Export the zone itself
        await self._export_zone_resource(zone, action)

        # Export resource records if requested
        if include_records:
            await self._export_zone_records(
                zone["id"],
                action,
                filter_str=filter_str,
                fields=fields,
                limit=limit,
                order_by=order_by,
            )

        # Recursively export children if requested
        if include_children:
            await self._export_zone_hierarchy(
                zone["id"],
                include_records,
                action,
                filter_str=filter_str,
                fields=fields,
                limit=limit,
                order_by=order_by,
            )

        return self.exported_resources

    async def _export_block_hierarchy(
        self,
        parent_id: int,
        include_addresses: bool,
        action: str,
        filter_str: str | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> None:
        """
        Export child blocks and networks using iterative BFS to avoid recursion depth issues.
        """
        from collections import deque

        # Queue stores tuples of (id, type_str) where type_str is "Block" or "Network"
        queue = deque([(parent_id, "Block")])

        while queue:
            current_id, current_type = queue.popleft()

            if current_type == "Block":
                # Get children of block (blocks + networks)
                results = await asyncio.gather(
                    self.client.get_child_blocks(
                        current_id, filter=filter_str, fields=fields, limit=limit, order_by=order_by
                    ),
                    self.client.get_child_networks(
                        current_id, filter=filter_str, fields=fields, limit=limit, order_by=order_by
                    ),
                )
                child_blocks, child_networks = results

                # Export and queue blocks
                for block in child_blocks:
                    await self._export_block_resource(block, action)
                    queue.append((block["id"], "Block"))

                # Export and queue networks
                for network in child_networks:
                    await self._export_network_resource(network, action)
                    queue.append((network["id"], "Network"))

            elif current_type == "Network":
                # Get child networks
                child_networks = await self.client.get_child_networks(
                    current_id, filter=filter_str, fields=fields, limit=limit, order_by=order_by
                )

                for network in child_networks:
                    await self._export_network_resource(network, action)
                    queue.append((network["id"], "Network"))

                # Get addresses if requested
                if include_addresses:
                    addresses = await self.client.get_addresses_in_network(
                        current_id, filter=filter_str, fields=fields, limit=limit, order_by=order_by
                    )
                    for address in addresses:
                        await self._export_address_resource(address, action)

    async def _export_network_hierarchy(
        self,
        network_id: int,
        include_addresses: bool,
        action: str,
        filter_str: str | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> None:
        """
        Export child networks and addresses using iterative BFS.
        """
        from collections import deque

        queue = deque([network_id])

        while queue:
            current_id = queue.popleft()

            # Get child networks
            child_networks = await self.client.get_child_networks(
                current_id, filter=filter_str, fields=fields, limit=limit, order_by=order_by
            )

            for network in child_networks:
                await self._export_network_resource(network, action)
                queue.append(network["id"])

            # Get addresses if requested
            if include_addresses:
                addresses = await self.client.get_addresses_in_network(
                    current_id, filter=filter_str, fields=fields, limit=limit, order_by=order_by
                )
                for address in addresses:
                    await self._export_address_resource(address, action)

    async def _export_zone_hierarchy(
        self,
        zone_id: int,
        include_records: bool,
        action: str,
        filter_str: str | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> None:
        """
        Recursively export child zones and their records.

        Args:
            zone_id: ID of the zone.
            include_records: Whether to include DNS records.
            action: The action to set in the exported CSV rows.
            filter_str: Optional BAM filter string
            fields: Optional list of fields to fetch
            limit: Optional limit on results
            order_by: Optional sort order
        """
        # Get child zones
        child_zones = await self.client.get_child_zones(
            zone_id,
            filter=filter_str,
            fields=fields,
            limit=limit,
            order_by=order_by,
        )
        for zone in child_zones:
            await self._export_zone_resource(zone, action)

            # Export resource records if requested
            if include_records:
                await self._export_zone_records(
                    zone["id"],
                    action,
                    filter_str=filter_str,
                    fields=fields,
                    limit=limit,
                    order_by=order_by,
                )

            # Recursively export this zone's children
            await self._export_zone_hierarchy(
                zone["id"],
                include_records,
                action,
                filter_str=filter_str,
                fields=fields,
                limit=limit,
                order_by=order_by,
            )

    async def _export_zone_records(
        self,
        zone_id: int,
        action: str,
        filter_str: str | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        order_by: str | None = None,
    ) -> None:
        """
        Export all resource records in a zone.

        Args:
            zone_id: ID of the zone.
            action: The action to set in the exported CSV rows.
            filter_str: Optional BAM filter string
            fields: Optional list of fields to fetch
            limit: Optional limit on results
            order_by: Optional sort order
        """
        records = await self.client.get_resource_records_in_zone(
            zone_id,
            filter=filter_str,
            fields=fields,
            limit=limit,
            order_by=order_by,
        )
        for record in records:
            await self._export_resource_record(record, action)

    async def _export_block_resource(self, block: dict[str, Any], action: str) -> None:
        """
        Convert a block resource to CSV row format.

        Args:
            block: The block resource dictionary from BAM.
            action: The action to set in the exported CSV row.
        """
        logger.debug("Exporting block", block_id=block.get("id"), name=block.get("name"))

        # Extract UDFs
        udfs = self._extract_udfs(block)

        # BAM API returns "IPv4Block" or "IPv6Block" (not "IP4Block")
        block_type = block.get("type", "")
        row = {
            "row_id": len(self.exported_resources) + 1,
            "object_type": "ip4_block" if block_type in ("IP4Block", "IPv4Block") else "ip6_block",
            "action": action,
            "bam_id": block.get("id"),
            "config": block.get("configuration", {}).get("name", ""),
            "name": block.get("name"),
            "cidr": block.get("range") or block.get("properties", {}).get("CIDR"),
            **udfs,
        }

        self.exported_resources.append(row)

    async def _export_network_resource(self, network: dict[str, Any], action: str) -> None:
        """
        Convert a network resource to CSV row format.

        Args:
            network: The network resource dictionary from BAM.
            action: The action to set in the exported CSV row.
        """
        logger.debug("Exporting network", network_id=network.get("id"), name=network.get("name"))

        # Extract UDFs
        udfs = self._extract_udfs(network)

        # BAM API returns "IPv4Network" or "IPv6Network" (not "IP4Network")
        network_type = network.get("type", "")
        row = {
            "row_id": len(self.exported_resources) + 1,
            "object_type": (
                "ip4_network" if network_type in ("IP4Network", "IPv4Network") else "ip6_network"
            ),
            "action": action,
            "bam_id": network.get("id"),
            "config": network.get("configuration", {}).get("name", ""),
            "name": network.get("name"),
            "cidr": network.get("range") or network.get("properties", {}).get("CIDR"),
            **udfs,
        }

        self.exported_resources.append(row)

    async def _export_address_resource(self, address: dict[str, Any], action: str) -> None:
        """
        Convert an address resource to CSV row format.

        Args:
            address: The address resource dictionary from BAM.
            action: The action to set in the exported CSV row.
        """
        logger.debug(
            "Exporting address", address_id=address.get("id"), address=address.get("address")
        )

        # Extract UDFs
        udfs = self._extract_udfs(address)

        # BAM API returns "IPv4Address" or "IPv6Address" (not "IP4Address")
        address_type = address.get("type", "")
        row = {
            "row_id": len(self.exported_resources) + 1,
            "object_type": (
                "ip4_address" if address_type in ("IP4Address", "IPv4Address") else "ip6_address"
            ),
            "action": action,
            "bam_id": address.get("id"),
            "config": address.get("configuration", {}).get("name", ""),
            "name": address.get("name"),
            "address": address.get("address") or address.get("properties", {}).get("address"),
            "mac": address.get("macAddress") or address.get("properties", {}).get("macAddress"),
            **udfs,
        }

        self.exported_resources.append(row)

    async def _export_zone_resource(self, zone: dict[str, Any], action: str) -> None:
        """
        Convert a zone resource to CSV row format.

        Args:
            zone: The zone resource dictionary from BAM.
            action: The action to set in the exported CSV row.
        """
        logger.debug("Exporting zone", zone_id=zone.get("id"), name=zone.get("name"))

        # Extract UDFs
        udfs = self._extract_udfs(zone)

        row = {
            "row_id": len(self.exported_resources) + 1,
            "object_type": "dns_zone",
            "action": action,
            "bam_id": zone.get("id"),
            "config": zone.get("configuration", {}).get("name", ""),
            "view_path": zone.get("view", {}).get("name", ""),
            "zone_name": zone.get("absoluteName") or zone.get("name"),
            "name": zone.get("name"),
            **udfs,
        }

        self.exported_resources.append(row)

    async def _export_resource_record(self, record: dict[str, Any], action: str) -> None:
        """
        Convert a resource record to CSV row format.

        Args:
            record: The resource record dictionary from BAM.
            action: The action to set in the exported CSV row.
        """
        logger.debug(
            "Exporting resource record", record_id=record.get("id"), name=record.get("name")
        )

        # Extract UDFs
        udfs = self._extract_udfs(record)

        # Determine object type
        record_type = record.get("type", "")
        object_type_map = {
            "HostRecord": "host_record",
            "AliasRecord": "alias_record",
            "MXRecord": "mx_record",
            "TXTRecord": "txt_record",
            "SRVRecord": "srv_record",
        }
        object_type = object_type_map.get(record_type, "resource_record")

        # Extract addresses (for host records)
        addresses = None
        if (
            record_type == "HostRecord"
            and "_embedded" in record
            and "addresses" in record["_embedded"]
        ):
            addr_list = record["_embedded"]["addresses"]
            addresses = "|".join([addr.get("address", "") for addr in addr_list])

        row = {
            "row_id": len(self.exported_resources) + 1,
            "object_type": object_type,
            "action": action,
            "bam_id": record.get("id"),
            "config": record.get("configuration", {}).get("name", ""),
            "view_path": record.get("view", {}).get("name", ""),
            "name": record.get("name"),
            "addresses": addresses,
            "ttl": record.get("ttl"),
            **udfs,
        }

        self.exported_resources.append(row)

    def _extract_udfs(self, resource: dict[str, Any]) -> dict[str, str]:
        """
        Extract user-defined fields from a resource.

        Args:
            resource: BlueCat resource object

        Returns:
            Dictionary of UDF columns (udf_name: value)
        """
        udfs = {}
        udf_data = resource.get("userDefinedFields")

        if udf_data and isinstance(udf_data, dict):
            for udf_name, udf_value in udf_data.items():
                # Create column name with udf_ prefix
                column_name = f"udf_{udf_name}"
                # Track discovered UDFs
                self.discovered_udfs.add(column_name)
                # Convert value to string
                udfs[column_name] = str(udf_value) if udf_value is not None else ""

        return udfs

    def get_csv_columns(self) -> list[str]:
        """
        Get all CSV columns including dynamically discovered UDFs.

        Returns:
            List of column names in correct order
        """
        # Base columns that should always be present
        base_columns = [
            "row_id",
            "object_type",
            "action",
            "bam_id",
            "config",
            "view_path",
            "parent",
            "zone_name",
            "name",
            "cidr",
            "address",
            "addresses",
            "mac",
            "ttl",
            "description",
        ]

        # Add discovered UDF columns in sorted order
        udf_columns = sorted(self.discovered_udfs)

        return base_columns + udf_columns

    async def write_csv(self, output_file: Path) -> None:
        """
        Write exported resources to CSV file.

        Args:
            output_file: Path to output CSV file
        """
        logger.info(
            "Writing CSV file",
            output_file=str(output_file),
            resource_count=len(self.exported_resources),
        )

        # Ensure parent directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Get all columns
        columns = self.get_csv_columns()

        # Write CSV
        with open(output_file, "w", newline="") as csvfile:
            # Write metadata comments
            csvfile.write("# Exported from BlueCat Address Manager\n")
            csvfile.write(f"# Export Date: {datetime.now().isoformat()}\n")
            csvfile.write(f"# Total Resources: {len(self.exported_resources)}\n")
            csvfile.write("# Schema Version: 3.0\n")

            writer = csv.DictWriter(csvfile, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()

            # Write each resource
            # Write each resource
            for resource in self.exported_resources:
                if not self.allow_formulas:
                    # Create a copy to avoid modifying original data
                    sanitized_resource = {}
                    for k, v in resource.items():
                        if isinstance(v, str):
                            sanitized_resource[k] = self._sanitize_csv_field(v)
                        else:
                            sanitized_resource[k] = v
                    writer.writerow(sanitized_resource)
                else:
                    writer.writerow(resource)

        logger.info("CSV export completed", output_file=str(output_file))

    def _sanitize_csv_field(self, value: str) -> str:
        """
        Prevent CSV injection by escaping formula characters.

        Ref: https://owasp.org/www-community/attacks/CSV_Injection

        Args:
            value: The field value to sanitize

        Returns:
            Sanitized value (prefixed with ' if dangerous)
        """
        if value.startswith(("=", "@", "+", "-", "\t", "\r")):
            return "'" + value
        return value
