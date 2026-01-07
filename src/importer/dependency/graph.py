"""Dependency Graph - DAG with cycle detection for operation ordering.

Manages dependencies between operations to ensure correct execution order.
"""

from dataclasses import dataclass, field
from enum import Enum

import structlog

from ..models.operations import Operation, OperationStatus, OperationType
from ..utils.exceptions import CyclicDependencyError

logger = structlog.get_logger(__name__)


# -----------------------------------------------------------------------------
# EXECUTION PHASES
# -----------------------------------------------------------------------------
# Defines strict barriers. All operations in Phase N must complete
# before any operation in Phase N+1 can begin.
#
# Creation Order: Phase 0 -> Phase 1 -> ... -> Phase N (parents before children)
# Deletion Order: Phase N -> Phase N-1 -> ... -> Phase 0 (children before parents)
#
# To prevent race conditions between deletions and creations of the same resource,
# all DELETE operations run BEFORE any CREATE/UPDATE operations.
#
# Rationale for PHASE_ORDER:
# This strict ordering reflects the BAM resource hierarchy. We must create containers
# (Blocks, Networks, Zones) before we can populate them with leaf resources (Addresses, Records).
# Violating this order would result in "Parent Not Found" errors during creation
# or "Child Exists" errors during deletion.

PHASE_ORDER = [
    # Phase 0: Global Metadata & Definitions
    # These resources are GLOBAL (not per-configuration) and must exist
    # before other resources can reference them.
    {"device_type", "tag_group", "udf_definition", "udl_definition", "mac_pool"},
    # Phase 1: Secondary Global Resources (depend on Phase 0)
    {"device_subtype", "tag"},
    # Phase 2: Core Infrastructure (Blocks & Networks)
    {"location", "ip4_block", "ip4_network", "ip6_block", "ip6_network"},
    # Phase 3: DNS Containers (Zones) & ACLs
    {"dns_zone", "acl"},
    # Phase 4: Targets (External Hosts)
    {"external_host_record"},
    # Phase 5: Core Records (Hosts, IPs, Groups, MAC Addresses)
    {"host_record", "ip4_address", "ip6_address", "ip4_group", "mac_address"},
    # Phase 6: Dependent DNS Records (and Generic Records)
    {"alias_record", "mx_record", "srv_record", "txt_record", "generic_record"},
    # Phase 7: Devices (after addresses exist for potential linking)
    {"device"},
    # Phase 8: DHCP, Deployment, Associations & Links
    {
        "ipv4_dhcp_range",
        "ipv6_dhcp_range",
        "dhcpv4_client_class",
        "dhcp_deployment_role",
        "dns_deployment_role",
        "dhcpv4_client_deployment_option",
        "dhcpv4_service_deployment_option",
        "device_address",
        "resource_tag",
        "user_defined_link",
        "access_right",
    },
]

# Delete phases run in REVERSE order (children before parents)
# These phases run BEFORE creation phases to prevent race conditions
DELETE_PHASE_ORDER = list(reversed(PHASE_ORDER))


class DependencyType(str, Enum):
    """Types of dependencies between operations."""

    PARENT_CHILD = "parent_child"  # Parent must exist before child
    PREREQUISITE = "prerequisite"  # General prerequisite relationship
    REFERENCE = "reference"  # References another resource


@dataclass
class DependencyNode:
    """
    Node in the dependency graph representing an operation.

    Attributes:
        operation: The operation this node represents
        dependencies: Set of node IDs this node depends on (must execute before this)
        dependents: Set of node IDs that depend on this node (must execute after this)
        depth: Depth in dependency tree (0 = no dependencies)
    """

    operation: Operation
    dependencies: set[str] = field(default_factory=set)
    dependents: set[str] = field(default_factory=set)
    depth: int = 0

    @property
    def node_id(self) -> str:
        """Unique identifier for this node."""
        return f"{self.operation.object_type}:{self.operation.row_id}"

    def __hash__(self) -> int:
        """Hash based on node ID."""
        return hash(self.node_id)


class DependencyGraph:
    """
    Directed Acyclic Graph (DAG) for managing operation dependencies.

    Features:
    - Automatic parent-child dependency detection
    - Cycle detection and prevention
    - Topological sorting for execution order
    - Dependency depth calculation
    - Validation of dependency constraints
    """

    def __init__(self) -> None:
        """Initialize empty dependency graph with optimized indexes."""
        self.nodes: dict[str, DependencyNode] = {}
        self._validated = False

        # QUALITY-005: Add indexes for faster lookups
        # Index of nodes by object type (e.g., "ip4_block" -> [node1, node2])
        self._nodes_by_type: dict[str, list[DependencyNode]] = {}
        # Index of nodes by operation type (e.g., OperationType.CREATE -> [nodes])
        self._nodes_by_operation: dict[OperationType, list[DependencyNode]] = {}
        # Index of CREATE operations by object type (for fast parent lookup)
        self._create_operations: dict[str, list[DependencyNode]] = {}

    def add_operation(self, operation: Operation) -> DependencyNode:
        """
        Add an operation to the dependency graph.

        Args:
            operation: Operation to add

        Returns:
            The created DependencyNode
        """
        node = DependencyNode(operation=operation)
        node_id = node.node_id

        if node_id in self.nodes:
            logger.warning("Operation already in graph", node_id=node_id)
            return self.nodes[node_id]

        self.nodes[node_id] = node
        self._validated = False  # Invalidate validation when graph changes

        # QUALITY-005: Update indexes for faster lookups
        obj_type = operation.object_type
        op_type = operation.operation_type

        # Index by object type
        if obj_type not in self._nodes_by_type:
            self._nodes_by_type[obj_type] = []
        self._nodes_by_type[obj_type].append(node)

        # Index by operation type
        if op_type not in self._nodes_by_operation:
            self._nodes_by_operation[op_type] = []
        self._nodes_by_operation[op_type].append(node)

        # Index CREATE operations for fast parent lookup
        if op_type == OperationType.CREATE:
            if obj_type not in self._create_operations:
                self._create_operations[obj_type] = []
            self._create_operations[obj_type].append(node)

        logger.debug(
            "Added operation to graph",
            node_id=node_id,
            operation_type=operation.operation_type.value,
        )

        return node

    def _find_create_operations_by_type(self, object_type: str) -> list[DependencyNode]:
        """
        Fast lookup of CREATE operations by object type using index.

        QUALITY-005: This method provides O(1) lookup instead of O(n) scan.

        Args:
            object_type: Type of object to find CREATE operations for

        Returns:
            List of DependencyNodes for CREATE operations of the specified type
        """
        return self._create_operations.get(object_type, [])

    def add_dependency(
        self,
        dependent_id: str,
        dependency_id: str,
        dependency_type: DependencyType = DependencyType.PREREQUISITE,
    ) -> None:
        """
        Add a dependency edge between two nodes.

        Args:
            dependent_id: Node that depends on another (executes AFTER)
            dependency_id: Node that is depended upon (executes BEFORE)
            dependency_type: Type of dependency

        Raises:
            CyclicDependencyError: If adding this edge would create a cycle
        """
        if dependent_id not in self.nodes:
            raise ValueError(f"Dependent node not found: {dependent_id}")

        if dependency_id not in self.nodes:
            raise ValueError(f"Dependency node not found: {dependency_id}")

        # Don't create self-dependencies
        if dependent_id == dependency_id:
            logger.warning("Attempted to create self-dependency", node_id=dependent_id)
            return

        # Add the edge
        self.nodes[dependent_id].dependencies.add(dependency_id)
        self.nodes[dependency_id].dependents.add(dependent_id)

        logger.debug(
            "Added dependency edge",
            dependent=dependent_id,
            dependency=dependency_id,
            type=dependency_type.value,
        )

        # Check for cycles using DFS from the dependent node
        # This is sufficient because we check after each edge addition, so any cycle
        # must include the newly added edge and be reachable from dependent_id
        if self._has_cycle_from(dependent_id, set()):
            # Remove the edge we just added
            self.nodes[dependent_id].dependencies.remove(dependency_id)
            self.nodes[dependency_id].dependents.remove(dependent_id)

            raise CyclicDependencyError(
                f"Adding dependency from {dependent_id} to {dependency_id} would create a cycle"
            )

        self._validated = False

    def build_from_operations(self, operations: list[Operation]) -> None:
        """
        Build dependency graph from a list of operations.

        Automatically detects parent-child relationships based on:
        - Resource hierarchy (config → block → network → address)
        - Path-based dependencies
        - bam_id references

        Args:
            operations: List of operations to build graph from
        """
        logger.info("Building dependency graph", operation_count=len(operations))

        # First pass: Add all operations as nodes
        for operation in operations:
            self.add_operation(operation)

        # Second pass: Detect and add dependencies
        for operation in operations:
            self._detect_dependencies(operation)

        # Third: Apply strict phasing barriers
        self._apply_phasing()

        # Calculate depths
        self._calculate_depths()

        logger.info(
            "Dependency graph built",
            nodes=len(self.nodes),
            edges=sum(len(node.dependencies) for node in self.nodes.values()),
        )

    def _apply_phasing(self) -> None:
        """
        Injects virtual 'Barrier' nodes (NOOPs) between phases defined in PHASE_ORDER.

        Phasing Strategy:
        1. DELETE operations run FIRST in REVERSE phase order (children before parents)
           - Phase 5 deletes -> Phase 4 deletes -> ... -> Phase 0 deletes
        2. CREATE/UPDATE operations run AFTER all deletes in NORMAL phase order
           - Phase 0 creates -> Phase 1 creates -> ... -> Phase 5 creates

        This ensures:
        - No race conditions between delete and recreate of the same resource
        - Proper dependency ordering within each operation type

        Side Effect:
        These barriers serialize execution between phases. For example, no Phase 1 creation
        can start until ALL Phase 0 creations are finished. This reduces maximum theoretical
        parallelism but guarantees correctness for the container hierarchy.
        """
        logger.info("Applying phased execution barriers")

        previous_barrier_id = None

        # Phase 1: Apply DELETE phasing (reverse order - children before parents)
        for delete_phase_index, phase_types in enumerate(DELETE_PHASE_ORDER):
            # Find all DELETE operations in this phase
            delete_nodes = [
                node
                for node in self.nodes.values()
                if node.operation.object_type in phase_types
                and node.operation.operation_type == OperationType.DELETE
            ]

            if not delete_nodes:
                logger.debug(f"Delete phase {delete_phase_index} has no operations, skipping")
                continue

            # Link delete nodes to previous barrier (if any)
            if previous_barrier_id:
                for node in delete_nodes:
                    if previous_barrier_id not in node.dependencies:
                        self.add_dependency(
                            node.node_id, previous_barrier_id, DependencyType.PREREQUISITE
                        )

            # Create barrier for END of this delete phase
            barrier_op = Operation(
                row_id=f"barrier_delete_phase_{delete_phase_index}",
                operation_type=OperationType.NOOP,
                object_type="system_barrier",
                resource_id=None,
                payload={},
                csv_row=None,
                status=OperationStatus.PENDING,
            )

            barrier_node = self.add_operation(barrier_op)

            # Barrier depends on ALL delete nodes in this phase
            for node in delete_nodes:
                self.add_dependency(barrier_node.node_id, node.node_id, DependencyType.PREREQUISITE)

            logger.debug(
                f"Created Delete Barrier for Phase {delete_phase_index} with {len(delete_nodes)} nodes"
            )
            previous_barrier_id = barrier_node.node_id

        # Phase 2: Apply CREATE/UPDATE phasing (normal order - parents before children)
        for phase_index, phase_types in enumerate(PHASE_ORDER):
            # Find all CREATE/UPDATE operations in this phase
            phase_nodes = [
                node
                for node in self.nodes.values()
                if node.operation.object_type in phase_types
                and node.operation.operation_type in (OperationType.CREATE, OperationType.UPDATE)
            ]

            if not phase_nodes:
                logger.debug(f"Create phase {phase_index} has no operations, skipping")
                continue

            # Link phase nodes to previous barrier (if any)
            # This includes the last delete barrier, ensuring all deletes complete first
            if previous_barrier_id:
                for node in phase_nodes:
                    if previous_barrier_id not in node.dependencies:
                        self.add_dependency(
                            node.node_id, previous_barrier_id, DependencyType.PREREQUISITE
                        )

            # Create new Barrier for END of this create phase
            barrier_op = Operation(
                row_id=f"barrier_create_phase_{phase_index}",
                operation_type=OperationType.NOOP,
                object_type="system_barrier",
                resource_id=None,
                payload={},
                csv_row=None,
                status=OperationStatus.PENDING,
            )

            barrier_node = self.add_operation(barrier_op)

            # Barrier depends on ALL nodes in this phase
            for node in phase_nodes:
                self.add_dependency(barrier_node.node_id, node.node_id, DependencyType.PREREQUISITE)

            logger.debug(
                f"Created Create Barrier for Phase {phase_index} with {len(phase_nodes)} nodes"
            )
            previous_barrier_id = barrier_node.node_id

        logger.info("Phased execution barriers applied successfully")

    def _detect_dependencies(self, operation: Operation) -> None:
        """
        Detect and add dependencies for an operation.

        Args:
            operation: Operation to detect dependencies for
        """
        node_id = f"{operation.object_type}:{operation.row_id}"

        # DELETE operations depend on all child deletions happening first
        if operation.operation_type == OperationType.DELETE:
            self._add_delete_dependencies(operation, node_id)
            return

        # CREATE/UPDATE operations depend on parent creation
        if operation.operation_type in (OperationType.CREATE, OperationType.UPDATE):
            self._add_parent_dependencies(operation, node_id)

        # Add path-based dependencies
        self._add_path_dependencies(operation, node_id)

        # Add record reference dependencies (CNAME, MX, SRV)
        self._add_record_reference_dependencies(operation, node_id)

    def _add_parent_dependencies(self, operation: Operation, node_id: str) -> None:
        """
        Add dependencies on parent resources.

        For resource hierarchy: Configuration → Block → Network → Address

        Args:
            operation: Operation to add parent dependencies for
            node_id: Node ID of the operation
        """
        csv_row = operation.csv_row

        # Determine parent based on object type
        parent = None

        if operation.object_type in ("ip4_network", "network"):
            # Networks depend on blocks
            if hasattr(csv_row, "parent") and csv_row.parent:
                parent = csv_row.parent

        elif operation.object_type in ("ip4_address", "address"):
            # Addresses depend on networks
            if hasattr(csv_row, "config") and csv_row.config:
                # The config for an address points to its containing network
                parent = csv_row.config

        elif operation.object_type == "host_record":
            # Host records depend on DNS zones
            if hasattr(csv_row, "view_path") and csv_row.view_path:
                parent = csv_row.view_path

        # Find parent node and add dependency
        if parent:
            parent_node_id = self._find_node_by_path(parent)
            if parent_node_id:
                try:
                    self.add_dependency(node_id, parent_node_id, DependencyType.PARENT_CHILD)
                except CyclicDependencyError as e:
                    logger.error(
                        "Cyclic dependency detected with parent",
                        node=node_id,
                        parent=parent_node_id,
                        error=str(e),
                    )

    def _add_delete_dependencies(self, operation: Operation, node_id: str) -> None:
        """
        Add dependencies for delete operations.

        Delete operations must happen AFTER all child resources are deleted.

        Args:
            operation: Delete operation
            node_id: Node ID of the operation
        """
        # PERF: Use indexed lookup instead of O(n) scan
        for other_node in self._nodes_by_operation.get(OperationType.DELETE, []):
            if other_node.node_id == node_id:
                continue

            # Check if other node's resource is a child of this resource
            if self._is_child_of(other_node.operation, operation):
                try:
                    # This delete must wait for child delete
                    self.add_dependency(node_id, other_node.node_id, DependencyType.PARENT_CHILD)
                except CyclicDependencyError as e:
                    logger.error(
                        "Cyclic dependency in delete chain",
                        node=node_id,
                        child=other_node.node_id,
                        error=str(e),
                    )

    def _add_path_dependencies(self, operation: Operation, node_id: str) -> None:
        """
        Add dependencies based on path references.

        Analyzes CSV row data to find dependencies on parent resources
        that must exist before this operation can execute.

        Args:
            operation: Operation to check for path references
            node_id: Node ID of the operation
        """
        csv_row = operation.csv_row

        # Skip operations that don't need dependencies
        if operation.operation_type in [
            OperationType.DELETE,
            OperationType.NOOP,
            OperationType.ORPHAN,
        ]:
            return

        # Analyze different resource types for parent dependencies
        try:
            if operation.object_type == "ip4_network":
                # Network needs parent block
                parent_path = getattr(csv_row, "parent", None)
                config_path = getattr(csv_row, "config", None)

                if parent_path and config_path:
                    # Find parent block operation
                    self._add_dependency_by_path(
                        operation, node_id, "ip4_block", parent_path, config_path
                    )

            elif operation.object_type == "ip4_address":
                # Address needs parent network
                parent_path = getattr(csv_row, "parent", None)
                config_path = getattr(csv_row, "config", None)

                if parent_path and config_path:
                    # Find parent network operation
                    self._add_dependency_by_path(
                        operation, node_id, "ip4_network", parent_path, config_path
                    )

            elif operation.object_type in [
                "host_record",
                "alias_record",
                "mx_record",
                "txt_record",
                "srv_record",
                "external_host_record",
            ]:
                # DNS records need parent zone
                zone_name = getattr(csv_row, "zone_name", None)
                config_path = getattr(csv_row, "config", None)
                view_path = getattr(csv_row, "view_path", None)

                if zone_name and config_path and view_path:
                    # Find parent DNS zone operation
                    self._add_dependency_by_dns_zone(
                        operation, node_id, zone_name, config_path, view_path
                    )

            elif operation.object_type in ["ipv4_dhcp_range"]:
                # DHCP range needs parent network
                network_id = getattr(csv_row, "network_id", None)
                if network_id:
                    # Find network operation by ID
                    self._add_dependency_by_id(operation, node_id, "ip4_network", network_id)

            # Device-related dependencies
            elif operation.object_type == "device_subtype":
                # Device subtype depends on its parent device type
                device_type_name = getattr(csv_row, "device_type", None)
                if device_type_name:
                    self._add_dependency_by_name(
                        operation, node_id, "device_type", device_type_name
                    )

            elif operation.object_type == "device":
                # Device optionally depends on device type and subtype
                device_type_name = getattr(csv_row, "device_type", None)
                device_subtype_name = getattr(csv_row, "device_subtype", None)

                if device_type_name:
                    self._add_dependency_by_name(
                        operation, node_id, "device_type", device_type_name
                    )
                if device_subtype_name:
                    self._add_dependency_by_name(
                        operation, node_id, "device_subtype", device_subtype_name
                    )

            elif operation.object_type == "device_address":
                # Device address depends on the device
                device_name = getattr(csv_row, "device_name", None)
                config_path = getattr(csv_row, "config", None)

                if device_name and config_path:
                    self._add_dependency_by_device_name(
                        operation, node_id, device_name, config_path
                    )

        except AttributeError as e:
            logger.warning(
                "Could not analyze dependencies for operation",
                operation=operation.operation_type,
                error=str(e),
            )

    def _add_dependency_by_path(
        self,
        operation: Operation,
        node_id: str,
        parent_type: str,
        parent_path: str,
        config_path: str,
    ) -> None:
        """
        Add dependency on parent resource identified by path.

        Args:
            operation: Current operation
            node_id: Node ID of current operation
            parent_type: Type of parent resource
            parent_path: Path of parent resource
            config_path: Configuration name
        """
        # PERF: Use indexed lookup instead of O(n) scan
        for other_node in self._create_operations.get(parent_type, []):
            other_operation = other_node.operation
            other_csv_row = other_operation.csv_row

            # Check if paths match
            other_config = getattr(other_csv_row, "config", None)

            if parent_type == "ip4_block":
                # Block: check CIDR with proper segment matching
                other_cidr = getattr(other_csv_row, "cidr", None)
                if (
                    other_config == config_path
                    and other_cidr
                    and self._cidr_in_path(other_cidr, parent_path)
                ):
                    self.add_dependency(node_id, other_node.node_id)
                    logger.debug(
                        "Added path dependency",
                        from_operation=operation.object_type,
                        to_operation=parent_type,
                        parent_path=parent_path,
                    )
                    break

            elif parent_type == "ip4_network":
                # Network: check CIDR in path with proper segment matching
                other_cidr = getattr(other_csv_row, "cidr", None)
                if (
                    other_config == config_path
                    and other_cidr
                    and self._cidr_in_path(other_cidr, parent_path)
                ):
                    self.add_dependency(node_id, other_node.node_id)
                    logger.debug(
                        "Added path dependency",
                        from_operation=operation.object_type,
                        to_operation=parent_type,
                        parent_path=parent_path,
                    )
                    break

    def _cidr_in_path(self, cidr: str, path: str) -> bool:
        """
        Check if a CIDR is present as a complete segment in a path.

        This performs strict segment matching to avoid false positives from
        substring matching (e.g., "1.1.1.1" matching "1.1.1.10").

        Assumptions:
        - Assumes BAM API V2 path format where segments are slash-separated.
        - Assumes CIDRs in paths are normalized (e.g. no extra leading zeros).
        - This logic is tightly coupled to the current API path structure and
          may break if the API changes how it represents paths (e.g. using IDs instead of names).

        Args:
            cidr: CIDR to search for (e.g., "10.0.0.0/8")
            path: Path to search in (e.g., "/IPv4/10.0.0.0/8/10.0.1.0/24")

        Returns:
            True if CIDR is found as a complete path segment
        """
        if not cidr or not path:
            return False

        # Split path into segments and check for exact match
        # Path format: /IPv4/10.0.0.0/8/10.0.1.0/24 or Config/IPv4/10.0.0.0/8
        path_segments = path.split("/")

        # CIDR format: "10.0.0.0/8" - split into address and prefix
        if "/" in cidr:
            cidr_parts = cidr.split("/")
            if len(cidr_parts) == 2:
                address, prefix = cidr_parts
                # Look for consecutive segments matching address and prefix
                for i in range(len(path_segments) - 1):
                    if path_segments[i] == address and path_segments[i + 1] == prefix:
                        return True
        else:
            # Simple address without prefix - check for exact segment match
            return cidr in path_segments

        return False

    def _add_dependency_by_dns_zone(
        self, operation: Operation, node_id: str, zone_name: str, config_path: str, view_path: str
    ) -> None:
        """
        Add dependency on DNS zone.

        Args:
            operation: Current DNS record operation
            node_id: Node ID of current operation
            zone_name: DNS zone name
            config_path: Configuration name
            view_path: View name
        """
        # PERF: Use indexed lookup instead of O(n) scan
        for other_node in self._create_operations.get("dns_zone", []):
            other_operation = other_node.operation
            other_csv_row = other_operation.csv_row

            other_config = getattr(other_csv_row, "config", None)
            other_view = getattr(other_csv_row, "view_path", None)
            other_zone = getattr(other_csv_row, "zone_name", None)

            if other_config == config_path and other_view == view_path and other_zone == zone_name:
                self.add_dependency(node_id, other_node.node_id)
                logger.debug(
                    "Added DNS zone dependency",
                    from_operation=operation.object_type,
                    zone_name=zone_name,
                )
                break

    def _add_dependency_by_id(
        self, operation: Operation, node_id: str, parent_type: str, parent_id: int
    ) -> None:
        """
        Add dependency on parent resource identified by ID.

        Args:
            operation: Current operation
            node_id: Node ID of current operation
            parent_type: Type of parent resource
            parent_id: BAM ID of parent resource
        """
        # PERF: Use indexed lookup instead of O(n) scan
        for other_node in self._create_operations.get(parent_type, []):
            # This is simplified - in practice, we'd need to check
            # if the created resource will have the expected ID
            # For now, add dependency if we find a matching create operation
            self.add_dependency(node_id, other_node.node_id)
            logger.debug(
                "Added ID-based dependency",
                from_operation=operation.object_type,
                to_operation=parent_type,
                parent_id=parent_id,
            )
            break

    def _add_dependency_by_name(
        self, operation: Operation, node_id: str, parent_type: str, parent_name: str
    ) -> None:
        """
        Add dependency on parent resource identified by name.

        Used for GLOBAL resources like device_type and device_subtype where
        the name uniquely identifies the resource.

        Args:
            operation: Current operation
            node_id: Node ID of current operation
            parent_type: Type of parent resource (e.g., "device_type")
            parent_name: Name of parent resource
        """
        # PERF: Use indexed lookup instead of O(n) scan
        for other_node in self._create_operations.get(parent_type, []):
            other_csv_row = other_node.operation.csv_row
            other_name = getattr(other_csv_row, "name", None)

            if other_name == parent_name:
                self.add_dependency(node_id, other_node.node_id)
                logger.debug(
                    "Added name-based dependency",
                    from_operation=operation.object_type,
                    to_operation=parent_type,
                    parent_name=parent_name,
                )
                break

    def _add_dependency_by_device_name(
        self, operation: Operation, node_id: str, device_name: str, config_path: str
    ) -> None:
        """
        Add dependency on a device identified by name and configuration.

        Devices are per-configuration resources, so we need to match both
        the device name and the configuration.

        Args:
            operation: Current operation (device_address)
            node_id: Node ID of current operation
            device_name: Name of the device
            config_path: Configuration name
        """
        # PERF: Use indexed lookup instead of O(n) scan
        for other_node in self._create_operations.get("device", []):
            other_csv_row = other_node.operation.csv_row
            other_name = getattr(other_csv_row, "name", None)
            other_config = getattr(other_csv_row, "config", None)

            if other_name == device_name and other_config == config_path:
                self.add_dependency(node_id, other_node.node_id)
                logger.debug(
                    "Added device dependency",
                    from_operation=operation.object_type,
                    device_name=device_name,
                    config=config_path,
                )
                break

    def _add_record_reference_dependencies(self, operation: Operation, node_id: str) -> None:
        """
        Add dependencies for DNS records that reference other records.

        Handles:
        - AliasRecord (CNAME) -> matches 'linked_record_name'
        - MXRecord -> matches 'exchange'
        - SRVRecord -> matches 'target'

        Args:
            operation: Current operation
            node_id: Node ID of current operation
        """
        csv_row = operation.csv_row
        target_fqdn = None

        if operation.object_type == "alias_record":
            target_fqdn = getattr(csv_row, "linked_record_name", None)
        elif operation.object_type == "mx_record":
            target_fqdn = getattr(csv_row, "exchange", None)
        elif operation.object_type == "srv_record":
            target_fqdn = getattr(csv_row, "target", None)

        if not target_fqdn:
            return

        # PERF: Use indexed lookup instead of O(n) scan
        # Combine host_record and external_host_record CREATE operations
        potential_targets = self._create_operations.get(
            "host_record", []
        ) + self._create_operations.get("external_host_record", [])
        for other_node in potential_targets:
            other_op = other_node.operation
            other_name = getattr(other_op.csv_row, "name", "")

            # Direct match on name (assuming simple case where name is FQDN or unique enough)
            # In a robust system, we'd need full FQDN resolution logic
            if other_name and other_name == target_fqdn:
                self.add_dependency(node_id, other_node.node_id, DependencyType.REFERENCE)
                logger.debug(
                    "Added record reference dependency",
                    dependent=operation.object_type,
                    target=other_op.object_type,
                    fqdn=target_fqdn,
                )
                # We found a match, but there might be others (e.g. same name in diff views)
                # For now, adding dependency on the first match is a reasonable heuristic
                # to prevent "not found" errors.
                break

    def _is_child_of(self, child_op: Operation, parent_op: Operation) -> bool:
        """
        Check if one operation's resource is a child of another.

        Args:
            child_op: Potential child operation
            parent_op: Potential parent operation

        Returns:
            True if child_op is a child of parent_op
        """
        child_row = child_op.csv_row
        parent_row = parent_op.csv_row

        # Get paths - use empty string as fallback to prevent None errors
        child_path = getattr(child_row, "config", None) or getattr(child_row, "parent", None) or ""
        parent_path = (
            getattr(parent_row, "config", None) or getattr(parent_row, "parent", None) or ""
        )

        # Check if both paths are valid strings before comparison
        if not (
            child_path
            and parent_path
            and isinstance(child_path, str)
            and isinstance(parent_path, str)
        ):
            return False

        # Use segment-based comparison to avoid false positives like:
        # "10.0.0.0/80".startswith("10.0.0.0/8") == True (incorrect)
        # We need exact segment matching where segments are separated by "/" or "."

        # For exact match, child cannot be a child of parent
        if child_path == parent_path:
            return False

        # Check for segment-based prefix matching
        # Split by common path separators and check segment-by-segment
        child_segments = self._split_path_segments(child_path)
        parent_segments = self._split_path_segments(parent_path)

        # Child must have more segments than parent to be a child
        if len(child_segments) <= len(parent_segments):
            return False

        # Check if parent segments are a prefix of child segments
        return child_segments[: len(parent_segments)] == parent_segments

    def _split_path_segments(self, path: str) -> list[str]:
        """
        Split a path into segments for comparison.

        Handles both traditional paths (e.g., "config/block/network") and
        CIDR notation (e.g., "10.0.0.0/8").

        Args:
            path: Path string to split

        Returns:
            List of path segments
        """
        # If path contains "/" but looks like CIDR (has digits before and after "/")
        # treat the whole thing as one segment to avoid false prefix matches
        if "/" in path:
            parts = path.split("/")
            # Check if this looks like CIDR notation (IP/prefix)
            if len(parts) == 2 and parts[1].isdigit():
                # This is a CIDR - return as single segment
                return [path]
            # Otherwise split by "/"
            return [s for s in parts if s]

        # Split by common path separators
        if "." in path:
            return path.split(".")

        # Return as single segment
        return [path]

    def _find_node_by_path(self, path: str) -> str | None:
        """
        Find a node by its resource path.

        Args:
            path: Resource path to search for

        Returns:
            Node ID if found, None otherwise
        """
        for node_id, node in self.nodes.items():
            csv_row = node.operation.csv_row

            # Check various path fields
            row_path = (
                getattr(csv_row, "config", None)
                or getattr(csv_row, "parent", None)
                or getattr(csv_row, "view_path", None)
            )

            if row_path and row_path == path:
                return node_id

        return None

    def _has_cycle_from(self, start_node_id: str, recursion_stack: set[str]) -> bool:
        """
        Detect cycles using Depth-First Search (DFS) with recursion stack tracking.

        Algorithm:
        - DFS traverses the graph following dependencies
        - recursion_stack tracks nodes in current traversal path
        - Finding a node already in stack = cycle (back edge)

        Why recursion_stack:
        Simple visited set isn't enough because:
        - A→B→C is fine (A visited again after traversal complete)
        - A→B→A is cycle (A visited again during traversal)

        Example:
        Path: A → B → C → A
        1. DFS visits A (stack: {A})
        2. DFS visits B (stack: {A, B})
        3. DFS visits C (stack: {A, B, C})
        4. C depends on A (in stack!) → CYCLE DETECTED

        Args:
            start_node_id: Node to start DFS from
            recursion_stack: Set of nodes in current traversal path

        Returns:
            True if cycle detected, False otherwise
        """
        # Cycle detected: current node already in traversal path
        if start_node_id in recursion_stack:
            return True

        # Invalid node - shouldn't happen in normal operation
        if start_node_id not in self.nodes:
            return False

        # Add current node to active traversal path
        recursion_stack.add(start_node_id)

        # Recursively check all dependencies
        node = self.nodes[start_node_id]
        for dependency_id in node.dependencies:
            if self._has_cycle_from(dependency_id, recursion_stack):
                return True

        # Backtrack: remove from path as we return up the call stack
        recursion_stack.remove(start_node_id)

        return False

    def _calculate_depths(self) -> None:
        """
        Calculate dependency depth for each node.

        Depth = maximum distance from a root node (node with no dependencies).
        """
        # Reset all depths
        for node in self.nodes.values():
            node.depth = 0

        try:
            # Calculate depths using topological order
            sorted_nodes = self.topological_sort()
        except CyclicDependencyError as e:
            logger.error("Cannot calculate depths: cyclic dependency detected", error=str(e))
            # Keep all depths at 0
            return

        for node in sorted_nodes:
            if node.dependencies:
                # Depth is 1 + max depth of dependencies
                max_dep_depth = max(self.nodes[dep_id].depth for dep_id in node.dependencies)
                node.depth = max_dep_depth + 1

        logger.debug(
            "Calculated node depths",
            max_depth=max(node.depth for node in self.nodes.values()) if self.nodes else 0,
        )

    def topological_sort(self) -> list[DependencyNode]:
        """
        Perform topological sort using Kahn's algorithm.

        ALGORITHM (Kahn's, 1962):
        1. Calculate in-degree (number of dependencies) for each node
        2. Add all nodes with in-degree 0 to queue (no dependencies)
        3. While queue not empty:
           a. Remove node from queue (can execute now)
           b. For each dependent of this node:
              - Decrement its in-degree (dependency satisfied)
              - If in-degree becomes 0, add to queue
        4. If all nodes processed → valid DAG
           If some nodes remain → cycle detected

        TIME COMPLEXITY: O(V + E) where V = nodes, E = edges
        SPACE COMPLEXITY: O(V) for in-degree map and queue

        Example:
            A → B → C
            A → C

        Perform topological sort to determine execution order.

        Returns:
            List of nodes in execution order

        Raises:
            CyclicDependencyError: If a cycle is detected
        """
        from collections import deque

        # Create a copy of in-degree count for each node
        in_degree: dict[str, int] = {
            node_id: len(node.dependencies) for node_id, node in self.nodes.items()
        }

        # Queue of nodes with no dependencies
        # Use deque for O(1) pops (vs O(n) for list.pop(0))
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])

        sorted_nodes: list[DependencyNode] = []

        while queue:
            # Get a node that can execute now (no unmet dependencies)
            node_id = queue.popleft()
            sorted_nodes.append(self.nodes[node_id])

            # Update dependents that were waiting for this node
            for dependent_id in self.nodes[node_id].dependents:
                in_degree[dependent_id] -= 1  # One dependency satisfied

                # If all dependencies satisfied, add to execution queue
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # If we didn't process all nodes, there's a cycle
        if len(sorted_nodes) != len(self.nodes):
            unprocessed = set(self.nodes.keys()) - {node.node_id for node in sorted_nodes}
            raise CyclicDependencyError(
                f"Cyclic dependency detected involving nodes: {unprocessed}"
            )

        logger.debug("Topological sort complete", node_count=len(sorted_nodes))

        return sorted_nodes

    def to_dot(self) -> str:
        """
        Generate DOT format representation of the dependency graph.

        Returns:
            String containing the Graphviz DOT definition
        """
        lines = ["digraph DependencyGraph {"]
        lines.append("    rankdir=LR;")
        lines.append("    node [shape=box style=filled];")

        for node in self.nodes.values():
            op_type = node.operation.operation_type.value
            obj_type = node.operation.object_type
            row_id = node.operation.row_id
            node_id = node.node_id

            # Label
            label = f"{obj_type}\\n{row_id}\\n({op_type})"

            # Color based on op type
            color = "#eeeeee"  # Default gray
            if op_type == "create":
                color = "#d4edda"  # Green
            elif op_type == "delete":
                color = "#f8d7da"  # Red
            elif op_type == "update":
                color = "#cce5ff"  # Blue
            elif op_type == "noop":
                color = "#fff3cd"  # Yellow (Barriers)

            lines.append(f'    "{node_id}" [label="{label}" fillcolor="{color}"];')

            for dep_id in node.dependencies:
                lines.append(f'    "{dep_id}" -> "{node_id}";')

        lines.append("}")
        return "\n".join(lines)

    def get_execution_batches(self) -> list[list[DependencyNode]]:
        """
        Group operations into batches for parallel execution using depth-based leveling.

        ALGORITHM:
        1. Perform topological sort to get dependency order
        2. Use pre-calculated node depths (distance from roots)
        3. Group nodes by depth - all nodes at same depth can execute in parallel
        4. Return batches in depth order (ascending)

        DEPTH DEFINITION:
        - Root nodes (no dependencies): depth = 0
        - Node depth = 1 + max(depth of all dependencies)
        - Nodes at same depth have no dependency paths between them

        TIME COMPLEXITY: O(V + E) for topological sort + O(V) for grouping
        SPACE COMPLEXITY: O(V) for storing batches

        Example:
            A → B → D
            A → C → D

            Depths: {A: 0, B: 1, C: 1, D: 2}
            Batches: [[A], [B, C], [D]]

            - Batch 0: A (no dependencies)
            - Batch 1: B, C (both depend only on A)
            - Batch 2: D (depends on B and C)

        Returns:
            List of batches in execution order, where each batch contains
            nodes that can be executed concurrently without conflicts

        Raises:
            CyclicDependencyError: If dependency graph contains cycles
        """
        # Ensure depths are calculated before grouping
        self._calculate_depths()

        sorted_nodes = self.topological_sort()

        # Group by depth (nodes at same depth can execute in parallel)
        batches: dict[int, list[DependencyNode]] = {}

        for node in sorted_nodes:
            depth = node.depth
            if depth not in batches:
                batches[depth] = []
            batches[depth].append(node)

        # Convert to ordered list of batches
        result = [batches[depth] for depth in sorted(batches.keys())]

        logger.info(
            "Created execution batches",
            batch_count=len(result),
            max_batch_size=max(len(batch) for batch in result) if result else 0,
        )

        return result

    def validate(self) -> bool:
        """
        Validate the dependency graph.

        Checks:
        - All dependencies are valid
        - No cycles
        - Execution order is deterministic

        Returns:
            True if graph is valid

        Raises:
            CyclicDependencyError: If cycles are detected
        """
        if self._validated:
            return True

        logger.info("Validating dependency graph")

        # Validate all dependency references exist first
        for node_id, node in self.nodes.items():
            for dep_id in node.dependencies:
                if dep_id not in self.nodes:
                    raise ValueError(f"Invalid dependency reference: {dep_id} in node {node_id}")

            for dep_id in node.dependents:
                if dep_id not in self.nodes:
                    raise ValueError(f"Invalid dependent reference: {dep_id} in node {node_id}")

        # Check for cycles using topological sort
        try:
            self.topological_sort()
        except CyclicDependencyError:
            raise

        # Validate phase coverage for all object types
        self._validate_phase_coverage()

        self._validated = True
        logger.info("Dependency graph validation successful")

        return True

    def _validate_phase_coverage(self) -> None:
        """Ensure all defined object types have a phase assignment."""
        defined_types = set()
        for node in self.nodes.values():
            if node.operation.object_type != "system_barrier":
                defined_types.add(node.operation.object_type)

        phased_types = set().union(*PHASE_ORDER)
        unassigned = defined_types - phased_types

        if unassigned:
            logger.warning(
                "Object types without phase assignment",
                types=sorted(unassigned),
                message="These types will not be constrained by phasing",
            )
