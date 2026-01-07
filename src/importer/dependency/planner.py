"""Dependency Planner - robust dependency wiring for operations.

Handles complex dependency resolution, including deferred references for
resources created within the same import batch.

Purpose:
-------
The DependencyPlanner wires dependencies between operations in a DependencyGraph.
It examines each operation's payload and CSV row to determine what other
operations must complete first.

Dependency Types:
----------------
1. Parent-Child Hierarchies:
   - Block <- Network <- Address
   - View <- Zone <- Records
   - Parent Location <- Child Location

2. DNS Record Target Dependencies:
   - alias_record depends on host_record it points to (linked_record_name)
   - mx_record depends on host_record for exchange server
   - srv_record depends on host_record for target

3. Deployment Role Dependencies:
   - DHCP roles depend on networks/blocks they serve
   - DNS roles depend on zones they serve

Detection Mechanism:
-------------------
Dependencies are detected via:
1. Explicit parent paths (parent_path, network_path, zone_path)
2. Deferred resolution keys (_deferred_block_cidr, _deferred_network_cidr, etc.)
3. CIDR containment (address in network, network in block)
4. Named references (exchange, target, linked_record_name)

Important Design Notes:
----------------------
- Operations with errors in payload are skipped (no dependencies wired)
- Dependencies are only added if both source and target are valid
- The graph itself handles cycle detection via validate()
- Node IDs use format "object_type:row_id" for uniqueness

Example Workflow:
----------------
1. OperationFactory creates operations with _deferred_* keys
2. DependencyPlanner.build_graph() wires dependencies based on those keys
3. DependencyGraph.validate() checks for cycles
4. ExecutionPlanner creates batches respecting dependency order
5. Executor runs batches, resolving deferred IDs as parents complete
"""

import structlog

from ..models.operations import Operation
from .graph import DependencyGraph

logger = structlog.get_logger(__name__)


class DependencyPlanner:
    """
    Plan dependencies between operations.

    Extracts dependency wiring logic from the CLI to a dedicated component,
    handling standard parent-child relationships as well as deferred
    resolution for resources created in the same batch.
    """

    def build_graph(self, graph: DependencyGraph, operations: list[Operation]) -> None:
        """
        Add operations to the graph and wire dependencies.

        Args:
            graph: Dependency graph to populate
            operations: List of operations to process
        """
        # First add all operations to the graph
        for op in operations:
            graph.add_operation(op)

        # Build lookup maps of valid operations only (those with no errors in payload)
        # Maps resource key -> node_id (format: "object_type:row_id")
        blocks = {}  # cidr -> node_id
        networks = {}  # cidr -> node_id
        zones = {}  # zone_name -> node_id
        host_records = {}  # fqdn -> node_id (for linked record dependencies)
        locations = {}  # location_code -> node_id
        addresses = {}  # address -> node_id (for UDL dependencies)
        devices = {}  # "config/name" -> node_id (for UDL dependencies)
        device_types = {}  # name -> node_id (for device subtype dependencies)
        device_subtypes = {}  # name -> node_id (for device dependencies)
        valid_node_ids = set()

        for op in operations:
            node_id = f"{op.object_type}:{op.row_id}"

            # Skip operations that had resolution errors
            if "error" in op.payload:
                continue

            valid_node_ids.add(node_id)

            if op.object_type == "ip4_block":
                cidr = getattr(op.csv_row, "cidr", None)
                if cidr:
                    blocks[cidr] = node_id

            elif op.object_type == "ip4_network":
                cidr = getattr(op.csv_row, "cidr", None)
                if cidr:
                    networks[cidr] = node_id

            elif op.object_type == "dns_zone":
                zone_name = getattr(op.csv_row, "zone_name", None)
                if zone_name:
                    zones[zone_name] = node_id

            elif op.object_type == "host_record":
                # Build FQDN for host record lookup (for alias/srv/mx dependencies)
                name = getattr(op.csv_row, "name", None)
                if name:
                    host_records[name] = node_id

            elif op.object_type == "location":
                code = getattr(op.csv_row, "code", None)
                if code:
                    locations[code] = node_id

            elif op.object_type in ("ip4_address", "ip6_address"):
                # Track addresses for UDL source/destination dependencies
                address = getattr(op.csv_row, "address", None)
                if address:
                    addresses[address] = node_id

            elif op.object_type == "device":
                # Track devices for UDL destination dependencies
                name = getattr(op.csv_row, "name", None)
                config = getattr(op.csv_row, "config", None)
                if name and config:
                    # Key by config/name since devices are per-configuration
                    devices[f"{config}/{name}"] = node_id
                    # Also store by just name for simpler lookups
                    devices[name] = node_id

            elif op.object_type == "device_type":
                # Track device types for subtype dependencies
                name = getattr(op.csv_row, "name", None)
                if name:
                    device_types[name] = node_id

            elif op.object_type == "device_subtype":
                # Track device subtypes for device dependencies
                name = getattr(op.csv_row, "name", None)
                if name:
                    device_subtypes[name] = node_id

        # Add dependencies (only for valid operations)
        for op in operations:
            node_id = f"{op.object_type}:{op.row_id}"

            # Skip operations that had resolution errors
            if "error" in op.payload or node_id not in valid_node_ids:
                continue

            if op.object_type == "ip4_network":
                # Networks depend on blocks - check explicit parent_path or deferred block
                parent_path = getattr(op.csv_row, "parent_path", None)
                deferred_block_cidr = op.payload.get("_deferred_block_cidr")

                # Determine block CIDR from parent_path or deferred resolution
                block_cidr = None
                if parent_path:
                    # Extract CIDR from parent path (e.g., Default/10.0.0.0/8 -> 10.0.0.0/8)
                    # Path format: ConfigName/IP/Prefix -> need IP/Prefix
                    path_parts = parent_path.lstrip("/").split("/")
                    if len(path_parts) >= 3:
                        # ConfigName/IP/Prefix -> IP/Prefix
                        block_cidr = f"{path_parts[-2]}/{path_parts[-1]}"
                    else:
                        block_cidr = parent_path
                elif deferred_block_cidr:
                    # Use deferred block CIDR from auto-discovery
                    block_cidr = deferred_block_cidr

                if block_cidr and block_cidr in blocks and blocks[block_cidr] in valid_node_ids:
                    try:
                        # Network (dependent) depends on Block (dependency)
                        # add_dependency(dependent_id, dependency_id)
                        graph.add_dependency(node_id, blocks[block_cidr])
                        logger.info(
                            "Added block->network dependency",
                            network=op.row_id,
                            block_cidr=block_cidr,
                        )
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

            elif op.object_type == "ip4_address":
                # Addresses depend on networks - check for deferred network
                deferred_cidr = op.payload.get("_deferred_network_cidr")
                if (
                    deferred_cidr
                    and deferred_cidr in networks
                    and networks[deferred_cidr] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, networks[deferred_cidr])
                        logger.info(
                            "Added network->address dependency",
                            address=op.row_id,
                            network_cidr=deferred_cidr,
                        )
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

            elif op.object_type in (
                "host_record",
                "alias_record",
                "mx_record",
                "txt_record",
                "srv_record",
                "external_host_record",
            ):
                # DNS records depend on zones - check explicit zone_name or deferred zone
                zone_name = getattr(op.csv_row, "zone_name", None)
                deferred_zone_name = op.payload.get("_deferred_zone_name")

                # Use deferred zone name if available
                effective_zone_name = deferred_zone_name or zone_name

                if (
                    effective_zone_name
                    and effective_zone_name in zones
                    and zones[effective_zone_name] in valid_node_ids
                ):
                    try:
                        # DNS record (dependent) depends on Zone (dependency)
                        graph.add_dependency(node_id, zones[effective_zone_name])
                        logger.info(
                            "Added zone->dns_record dependency",
                            record=op.row_id,
                            zone=effective_zone_name,
                        )
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

                # Host records with addresses also depend on networks containing those addresses
                if op.object_type == "host_record":
                    import ipaddress

                    addresses = getattr(op.csv_row, "addresses", None)
                    if addresses:
                        # Parse addresses (pipe-separated)
                        addr_list = (
                            addresses.split("|") if isinstance(addresses, str) else [addresses]
                        )
                        for addr_str in addr_list:
                            try:
                                addr = ipaddress.ip_address(addr_str.strip())
                                # Check if address is in any network being created
                                for network_cidr, network_node_id in networks.items():
                                    if network_node_id in valid_node_ids:
                                        try:
                                            network = ipaddress.ip_network(
                                                network_cidr, strict=False
                                            )
                                            if addr in network:
                                                try:
                                                    graph.add_dependency(node_id, network_node_id)
                                                    logger.info(
                                                        "Added network->host_record dependency",
                                                        record=op.row_id,
                                                        network_cidr=network_cidr,
                                                    )
                                                except Exception as e:
                                                    logger.warning(
                                                        "Failed to add dependency", error=str(e)
                                                    )
                                                break
                                        except ValueError:
                                            pass
                            except ValueError:
                                logger.debug(
                                    f"Skipping invalid IP address in dependency check: {addr_str}"
                                )

            elif op.object_type == "ipv4_dhcp_range":
                # DHCP ranges depend on networks - check for deferred network
                deferred_cidr = op.payload.get("_deferred_network_cidr")
                if (
                    deferred_cidr
                    and deferred_cidr in networks
                    and networks[deferred_cidr] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, networks[deferred_cidr])
                        logger.info(
                            "Added network->dhcp_range dependency",
                            range=op.row_id,
                            network_cidr=deferred_cidr,
                        )
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

            elif op.object_type in ("dhcp_deployment_role", "dns_deployment_role"):
                # Dependencies: Network (dhcp), Block (dhcp/dns), Zone (dns)

                # Check for deferred Network
                deferred_network_cidr = op.payload.get("_deferred_network_cidr")
                if (
                    deferred_network_cidr
                    and deferred_network_cidr in networks
                    and networks[deferred_network_cidr] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, networks[deferred_network_cidr])
                        logger.info(
                            "Added network->deployment_role dependency",
                            role=op.row_id,
                            network_cidr=deferred_network_cidr,
                        )
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

                # Check for deferred Block
                deferred_block_cidr = op.payload.get("_deferred_block_cidr")
                if (
                    deferred_block_cidr
                    and deferred_block_cidr in blocks
                    and blocks[deferred_block_cidr] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, blocks[deferred_block_cidr])
                        logger.info(
                            "Added block->deployment_role dependency",
                            role=op.row_id,
                            block_cidr=deferred_block_cidr,
                        )
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

                # Check for deferred Zone
                deferred_zone_name = op.payload.get("_deferred_zone_name")
                if (
                    deferred_zone_name
                    and deferred_zone_name in zones
                    and zones[deferred_zone_name] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, zones[deferred_zone_name])
                        logger.info(
                            "Added zone->deployment_role dependency",
                            role=op.row_id,
                            zone_name=deferred_zone_name,
                        )
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

                # Also check standard network_path if no deferred resolution
                network_path = getattr(op.csv_row, "network_path", None)
                if (
                    network_path
                    and network_path in networks
                    and networks[network_path] in valid_node_ids
                    and not deferred_network_cidr
                ):
                    try:
                        graph.add_dependency(node_id, networks[network_path])
                    except Exception as e:
                        logger.warning("Failed to add dependency", error=str(e))

            # Note: Using 'if' instead of 'elif' here so these checks execute
            # AFTER the DNS record zone dependency check above (which also matches these types)
            if op.object_type == "alias_record":
                # Alias records depend on their linked (CNAME target) record
                linked_record = getattr(op.csv_row, "linked_record_name", None) or getattr(
                    op.csv_row, "cname", None
                )
                if (
                    linked_record
                    and linked_record in host_records
                    and host_records[linked_record] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, host_records[linked_record])
                        logger.info(
                            "Added host_record->alias_record dependency",
                            alias=op.row_id,
                            target=linked_record,
                        )
                    except Exception as e:
                        logger.warning("Failed to add linked record dependency", error=str(e))

            if op.object_type == "srv_record":
                # SRV records depend on their target record
                target = getattr(op.csv_row, "target", None)
                if target and target in host_records and host_records[target] in valid_node_ids:
                    try:
                        graph.add_dependency(node_id, host_records[target])
                        logger.info(
                            "Added host_record->srv_record dependency",
                            srv=op.row_id,
                            target=target,
                        )
                    except Exception as e:
                        logger.warning("Failed to add linked record dependency", error=str(e))

            if op.object_type == "mx_record":
                # MX records depend on their exchange (mail server) record
                exchange = getattr(op.csv_row, "exchange", None)
                if (
                    exchange
                    and exchange in host_records
                    and host_records[exchange] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, host_records[exchange])
                        logger.info(
                            "Added host_record->mx_record dependency",
                            mx=op.row_id,
                            exchange=exchange,
                        )
                    except Exception as e:
                        logger.warning("Failed to add linked record dependency", error=str(e))

            elif op.object_type == "location":
                # Child locations depend on parent locations - check for deferred location
                deferred_location_code = op.payload.get("_deferred_location_code")
                if (
                    deferred_location_code
                    and deferred_location_code in locations
                    and locations[deferred_location_code] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, locations[deferred_location_code])
                        logger.info(
                            "Added location->location dependency",
                            child_location=op.row_id,
                            parent_location_code=deferred_location_code,
                        )
                    except Exception as e:
                        logger.warning("Failed to add location dependency", error=str(e))

            # Generic checks for ALL object types
            # Check for deferred location dependency (location associations)
            # This handles blocks, networks, addresses, etc. that link to a location created in the same batch
            deferred_location_code = op.payload.get("_deferred_location_code")
            if (
                deferred_location_code
                and deferred_location_code in locations
                and locations[deferred_location_code] in valid_node_ids
                and op.object_type != "location"  # Already handled above
            ):
                try:
                    graph.add_dependency(node_id, locations[deferred_location_code])
                    logger.info(
                        "Added location dependency",
                        source_row=op.row_id,
                        source_type=op.object_type,
                        location_code=deferred_location_code,
                    )
                except Exception as e:
                    logger.warning("Failed to add location generic dependency", error=str(e))

            # User-Defined Link (UDL) dependencies
            # UDLs depend on both source and destination resources being created first
            if op.object_type == "user_defined_link":
                # Source dependencies (ip4_address, ip4_network, etc.)
                source_type = getattr(op.csv_row, "source_type", None)
                source_path = getattr(op.csv_row, "source_path", None)

                if source_type and source_path:
                    source_node_id = None

                    if source_type in ("ip4_address", "ip6_address"):
                        source_node_id = addresses.get(source_path)
                    elif source_type in ("ip4_network", "ip6_network"):
                        source_node_id = networks.get(source_path)
                    elif source_type in ("ip4_block", "ip6_block"):
                        source_node_id = blocks.get(source_path)
                    elif source_type == "device":
                        # Try both config/name and just name
                        config = getattr(op.csv_row, "config", None)
                        if config:
                            source_node_id = devices.get(f"{config}/{source_path}")
                        if not source_node_id:
                            source_node_id = devices.get(source_path)

                    if source_node_id and source_node_id in valid_node_ids:
                        try:
                            graph.add_dependency(node_id, source_node_id)
                            logger.info(
                                "Added UDL source dependency",
                                udl_row=op.row_id,
                                source_type=source_type,
                                source_path=source_path,
                            )
                        except Exception as e:
                            logger.warning("Failed to add UDL source dependency", error=str(e))

                # Destination dependencies (device, ip4_network, etc.)
                dest_type = getattr(op.csv_row, "destination_type", None)
                dest_path = getattr(op.csv_row, "destination_path", None)

                if dest_type and dest_path:
                    dest_node_id = None

                    if dest_type in ("ip4_address", "ip6_address"):
                        dest_node_id = addresses.get(dest_path)
                    elif dest_type in ("ip4_network", "ip6_network"):
                        dest_node_id = networks.get(dest_path)
                    elif dest_type in ("ip4_block", "ip6_block"):
                        dest_node_id = blocks.get(dest_path)
                    elif dest_type == "device":
                        # Try both config/name and just name
                        config = getattr(op.csv_row, "config", None)
                        if config:
                            dest_node_id = devices.get(f"{config}/{dest_path}")
                        if not dest_node_id:
                            dest_node_id = devices.get(dest_path)
                    elif dest_type == "dns_zone":
                        dest_node_id = zones.get(dest_path)

                    if dest_node_id and dest_node_id in valid_node_ids:
                        try:
                            graph.add_dependency(node_id, dest_node_id)
                            logger.info(
                                "Added UDL destination dependency",
                                udl_row=op.row_id,
                                destination_type=dest_type,
                                destination_path=dest_path,
                            )
                        except Exception as e:
                            logger.warning("Failed to add UDL destination dependency", error=str(e))

            # Device subtype dependencies on device types
            elif op.object_type == "device_subtype":
                device_type_name = getattr(op.csv_row, "device_type", None)
                if (
                    device_type_name
                    and device_type_name in device_types
                    and device_types[device_type_name] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, device_types[device_type_name])
                        logger.info(
                            "Added device_type->device_subtype dependency",
                            subtype_row=op.row_id,
                            device_type=device_type_name,
                        )
                    except Exception as e:
                        logger.warning("Failed to add device subtype dependency", error=str(e))

            # Device dependencies on device types and subtypes
            elif op.object_type == "device":
                # Depend on device type
                device_type_name = getattr(op.csv_row, "device_type", None)
                if (
                    device_type_name
                    and device_type_name in device_types
                    and device_types[device_type_name] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, device_types[device_type_name])
                        logger.info(
                            "Added device_type->device dependency",
                            device_row=op.row_id,
                            device_type=device_type_name,
                        )
                    except Exception as e:
                        logger.warning("Failed to add device type dependency", error=str(e))

                # Depend on device subtype
                device_subtype_name = getattr(op.csv_row, "device_subtype", None)
                if (
                    device_subtype_name
                    and device_subtype_name in device_subtypes
                    and device_subtypes[device_subtype_name] in valid_node_ids
                ):
                    try:
                        graph.add_dependency(node_id, device_subtypes[device_subtype_name])
                        logger.info(
                            "Added device_subtype->device dependency",
                            device_row=op.row_id,
                            device_subtype=device_subtype_name,
                        )
                    except Exception as e:
                        logger.warning("Failed to add device subtype dependency", error=str(e))
