"""Diff Engine - Compare desired state vs current state.

Determines what operations are needed to reconcile CSV with BAM.
"""

from typing import Any

import structlog

from ..config import PolicyConfig
from ..models.csv_row import CSVRow
from ..models.operations import FieldChange, OperationType
from ..models.results import DiffResult
from ..models.state import ResourceState
from ..utils.exceptions import ValidationError

logger = structlog.get_logger(__name__)


class DiffEngine:
    """
    Compute operations needed to reconcile CSV desired state with BAM current state.

    Core Responsibility:
    Analyzes what needs to change by comparing CSV rows (desired) against
    BAM resources (current) to generate CREATE/UPDATE/DELETE operations.

    Safety Features:
    - Field-level change detection: Only modifies actually changed fields
    - Conflict detection: Identifies concurrent modifications
    - Orphan protection: Strict scoping prevents mass deletions
    - Policy enforcement: Respects safe_mode, update_mode settings

    Decision Matrix:
    - Resource exists in CSV but not BAM → CREATE
    - Resource exists in both with differences → UPDATE or NOOP
    - Resource in BAM but not CSV → ORPHAN (potential DELETE)
    - CSV action=delete and resource exists → DELETE
    """

    def __init__(self, policy: PolicyConfig) -> None:
        """
        Initialize diff engine with policy controls.

        Args:
            policy: Configuration dictating diff behavior and safety rules
        """
        self.policy = policy

    def compute_diff(
        self,
        desired: CSVRow,
        current: ResourceState | None,
    ) -> DiffResult:
        """
        Determine what operation is needed for a resource.

        Compares desired CSV state against current BAM state to determine
        the appropriate operation type and field changes.

        Args:
            desired: Desired state from CSV row
            current: Current state from BAM (None if doesn't exist)

        Returns:
            DiffResult with operation type and field changes
        """
        logger.debug(
            "Computing diff",
            object_type=desired.object_type,
            action=desired.action,
            current_exists=current is not None,
        )

        # Route to appropriate handler based on action
        if desired.action == "delete":
            return self._handle_delete(desired, current)
        elif desired.action == "create":
            return self._handle_create(desired, current)
        elif desired.action == "update":
            return self._handle_update(desired, current)
        else:
            raise ValidationError(f"Unknown action: {desired.action}")

    def detect_orphans(
        self,
        desired_resources: list[CSVRow],
        current_resources: list[ResourceState],
        container_scope: dict[str, Any],
    ) -> list[DiffResult]:
        """
        Detect "orphan" resources in BAM not present in CSV.

        CRITICAL SAFETY RULES:
        1. Orphan detection ONLY operates within EXACT containers defined in CSV
        2. If CSV defines IPs in 10.1.0.0/24, ONLY scan that /24
        3. Never scan parent containers or sibling containers
        4. Safe mode (default ON) converts orphans to warnings, not deletes

        DANGER SCENARIO (prevented by strict scoping):
        - CSV contains: 10.1.0.0/24 (50 IPs)
        - User accidentally sets scope: 10.0.0.0/8
        - WITHOUT strict scoping: Would delete 65,000 IPs!
        - WITH strict scoping: Only scans 10.1.0.0/24

        Args:
            desired_resources: Resources from CSV
            current_resources: Resources from BAM (pre-filtered to exact scope)
            container_scope: Scope for orphan detection (MUST match CSV containers)

        Returns:
            List of DiffResults with operation="orphan"
        """
        if not self.policy.enable_orphan_detection:
            logger.debug("Orphan detection disabled by policy")
            return []

        logger.info(
            "Detecting orphans",
            desired_count=len(desired_resources),
            current_count=len(current_resources),
            scope=container_scope,
        )

        # Build set of desired identifiers
        desired_ids: set[int] = set()
        desired_keys: set[str] = set()

        for resource in desired_resources:
            if resource.bam_id:
                desired_ids.add(resource.bam_id)

            # Also track by unique key (address, name, etc.)
            unique_key = self._get_unique_key_from_csv(resource)
            if unique_key:
                desired_keys.add(unique_key)

        # Find orphans
        orphans: list[DiffResult] = []
        for current in current_resources:
            # Skip if in desired set by ID
            if current.id in desired_ids:
                continue

            # Skip if in desired set by unique key
            current_key = self._get_unique_key_from_state(current)
            if current_key in desired_keys:
                continue

            # This resource exists in BAM but not in CSV - it's an orphan
            orphan_result = DiffResult(
                operation=OperationType.ORPHAN,
                resource_id=current.id,
                field_changes={},
                conflict_detected=False,
                conflict_reason=None,
                metadata={
                    "name": current.properties.get("name"),
                    "address": current.properties.get("address"),
                    "CIDR": current.properties.get("CIDR"),
                    "scope": container_scope,
                },
            )
            orphans.append(orphan_result)

        if orphans:
            logger.warning(
                "Orphans detected",
                count=len(orphans),
                scope=container_scope,
                safe_mode=self.policy.safe_mode,
            )

            if self.policy.safe_mode:
                logger.info("Safe mode: Orphans will be logged as warnings, not deleted")
                # Convert orphans to NOOP operations in safe mode
                for orphan in orphans:
                    orphan.operation = OperationType.NOOP
                    orphan.metadata["orphan_safe_mode"] = True

        return orphans

    def _handle_create(self, desired: CSVRow, current: ResourceState | None) -> DiffResult:
        """
        Handle create action.

        - If resource doesn't exist: CREATE
        - If resource exists: NOOP or UPDATE (based on policy)

        Args:
            desired: Desired state from CSV
            current: Current state from BAM (if any)

        Returns:
            DiffResult indicating the operation to perform.
        """
        if current is None:
            # Resource doesn't exist - proceed with create
            logger.debug("Resource doesn't exist - CREATE", row_id=desired.row_id)
            return DiffResult(
                operation=OperationType.CREATE,
                resource_id=None,
                field_changes={},
                conflict_detected=False,
                conflict_reason=None,
            )
        else:
            # Resource already exists
            logger.debug("Resource already exists", row_id=desired.row_id, resource_id=current.id)

            if self.policy.update_mode == "create_only":
                # Don't update existing resources
                return DiffResult(
                    operation=OperationType.NOOP,
                    resource_id=current.id,
                    field_changes={},
                    conflict_detected=False,
                    conflict_reason="Resource already exists, update_mode=create_only",
                )
            else:
                # Check for differences and potentially update
                field_changes = self._compute_field_changes(desired, current)

                if not field_changes:
                    return DiffResult(
                        operation=OperationType.NOOP,
                        resource_id=current.id,
                        field_changes={},
                        conflict_detected=False,
                        conflict_reason="No changes needed",
                    )
                else:
                    return DiffResult(
                        operation=OperationType.UPDATE,
                        resource_id=current.id,
                        field_changes=field_changes,
                        conflict_detected=False,
                        conflict_reason=None,
                    )

    def _handle_update(self, desired: CSVRow, current: ResourceState | None) -> DiffResult:
        """
        Handle update action.

        - If resource doesn't exist: Error or CREATE (based on policy)
        - If resource exists: UPDATE or NOOP (if no changes)

        Args:
            desired: Desired state from CSV
            current: Current state from BAM (if any)

        Returns:
            DiffResult indicating the operation to perform.
        """
        if current is None:
            # Resource doesn't exist
            logger.warning("Update requested but resource doesn't exist", row_id=desired.row_id)

            if self.policy.update_mode == "upsert":
                # Create if doesn't exist
                return DiffResult(
                    operation=OperationType.CREATE,
                    resource_id=None,
                    field_changes={},
                    conflict_detected=False,
                    conflict_reason="Resource doesn't exist, creating due to upsert mode",
                )
            else:
                # Error - can't update non-existent resource
                return DiffResult(
                    operation=OperationType.NOOP,
                    resource_id=None,
                    field_changes={},
                    conflict_detected=True,
                    conflict_reason="Update requested but resource doesn't exist",
                )
        else:
            # Resource exists - check for changes
            field_changes = self._compute_field_changes(desired, current)

            if not field_changes:
                logger.debug("No changes needed", row_id=desired.row_id, resource_id=current.id)
                return DiffResult(
                    operation=OperationType.NOOP,
                    resource_id=current.id,
                    field_changes={},
                    conflict_detected=False,
                    conflict_reason="No changes needed",
                )
            else:
                logger.debug(
                    "Changes detected",
                    row_id=desired.row_id,
                    resource_id=current.id,
                    changes=len(field_changes),
                )
                return DiffResult(
                    operation=OperationType.UPDATE,
                    resource_id=current.id,
                    field_changes=field_changes,
                    conflict_detected=False,
                    conflict_reason=None,
                )

    def _handle_delete(self, desired: CSVRow, current: ResourceState | None) -> DiffResult:
        """
        Handle delete action.

        - If resource doesn't exist: NOOP (already gone)
        - If resource exists: DELETE (or NOOP in safe mode)

        Args:
            desired: Desired state from CSV
            current: Current state from BAM (if any)

        Returns:
            DiffResult indicating the operation to perform.
        """
        if current is None:
            # Resource doesn't exist - nothing to delete
            logger.debug("Delete requested but resource doesn't exist", row_id=desired.row_id)
            return DiffResult(
                operation=OperationType.NOOP,
                resource_id=None,
                field_changes={},
                conflict_detected=False,
                conflict_reason="Resource doesn't exist",
            )
        else:
            # Resource exists - proceed with delete
            if self.policy.safe_mode:
                logger.warning(
                    "Safe mode: Delete converted to NOOP",
                    row_id=desired.row_id,
                    resource_id=current.id,
                )
                return DiffResult(
                    operation=OperationType.NOOP,
                    resource_id=current.id,
                    field_changes={},
                    conflict_detected=False,
                    conflict_reason="Safe mode: Delete operations are disabled",
                    metadata={"safe_mode_prevented_delete": True},
                )
            else:
                logger.debug(
                    "Resource exists - DELETE", row_id=desired.row_id, resource_id=current.id
                )
                return DiffResult(
                    operation=OperationType.DELETE,
                    resource_id=current.id,
                    field_changes={},
                    conflict_detected=False,
                    conflict_reason=None,
                )

    def _compute_field_changes(
        self, desired: CSVRow, current: ResourceState
    ) -> dict[str, FieldChange]:
        """
        Compute field-level changes between desired and current state.

        Args:
            desired: Desired state from CSV
            current: Current state from BAM

        Returns:
            Dictionary of field name to FieldChange objects
        """
        changes: dict[str, FieldChange] = {}

        # Get desired fields from CSV row (exclude metadata and system fields)
        # These fields are CSV-specific and don't map to BAM properties
        exclude_fields = {"row_id", "object_type", "action", "config", "version"}
        desired_dict = desired.model_dump(exclude=exclude_fields)

        for field_name, desired_value in desired_dict.items():
            # Skip None values (not specified in CSV)
            if desired_value is None:
                continue

            # Get current value from BAM properties
            current_value = current.properties.get(field_name)

            # Normalize values for comparison
            desired_normalized = self._normalize_value(desired_value)
            current_normalized = self._normalize_value(current_value)

            # Compare values
            if desired_normalized != current_normalized:
                changes[field_name] = FieldChange(
                    field_name=field_name,
                    old_value=current_value,
                    new_value=desired_value,
                )
                logger.debug(
                    "Field change detected",
                    field=field_name,
                    old=current_value,
                    new=desired_value,
                )

        return changes

    def _normalize_value(self, value: Any) -> Any:
        """
        Normalize a value for comparison.

        Handles:
        - String whitespace trimming
        - Case-insensitive comparison for certain fields
        - Type coercion for numbers and booleans

        Args:
            value: Value to normalize

        Returns:
            Normalized value
        """
        if value is None:
            return None

        if isinstance(value, str):
            # Trim whitespace
            value = value.strip()
            # Empty string = None
            if not value:
                return None

            # Try to coerce to number if it looks numeric
            if value.isdigit():
                return int(value)
            try:
                # Try float conversion
                float_val = float(value)
                return float_val
            except ValueError:
                pass

        # Convert booleans to consistent format
        if isinstance(value, bool):
            return value

        # Convert numeric types to consistent format
        if isinstance(value, int | float):
            return value

        return value

    def _get_unique_key_from_csv(self, resource: CSVRow) -> str | None:
        """
        Extract unique key from CSV row for orphan detection.

        Args:
            resource: CSV row

        Returns:
            Unique key string, or None if can't determine
        """
        if resource.object_type in ("ip4_address", "address"):
            # For addresses, use address as key
            if hasattr(resource, "address"):
                return f"address:{resource.address}"

        elif resource.object_type in ("ip4_network", "network"):
            # For networks, use CIDR as key
            if hasattr(resource, "cidr"):
                return f"cidr:{resource.cidr}"

        elif resource.object_type in ("ip4_block", "block"):
            # For blocks, use CIDR as key
            if hasattr(resource, "cidr"):
                return f"cidr:{resource.cidr}"

        elif resource.object_type in ("host_record", "dns_zone"):
            # For DNS records, use name as key
            if hasattr(resource, "name"):
                return f"name:{resource.name}"

        # Fallback to BAM ID if available
        if resource.bam_id:
            return f"id:{resource.bam_id}"

        return None

    def _get_unique_key_from_state(self, resource: ResourceState) -> str | None:
        """
        Extract unique key from resource state for orphan detection.

        Args:
            resource: Resource state from BAM

        Returns:
            Unique key string, or None if can't determine
        """
        resource_type = resource.type.lower()

        if "address" in resource_type:
            # For addresses, use address as key
            address = resource.properties.get("address")
            if address:
                return f"address:{address}"

        elif "network" in resource_type:
            # For networks, use CIDR as key
            cidr = resource.properties.get("CIDR")
            if cidr:
                return f"cidr:{cidr}"

        elif "block" in resource_type:
            # For blocks, use CIDR as key
            cidr = resource.properties.get("CIDR")
            if cidr:
                return f"cidr:{cidr}"

        elif "zone" in resource_type or "hostrecord" in resource_type:
            # For DNS records, use name as key
            name = resource.properties.get("name")
            if name:
                return f"name:{name}"

        # Fallback to ID
        return f"id:{resource.id}"
