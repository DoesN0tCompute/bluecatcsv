"""Safety validation for dangerous operations.

This module implements safety checks to prevent accidental deletion of critical
BlueCat Address Manager resources. Resources are organized into safety tiers:

Safety Tiers:
    1. NEVER_DELETE_VIA_CSV (configuration, view):
       - Permanently blocked from deletion via CSV import
       - Cannot be bypassed with --allow-dangerous-operations
       - Self-test cleanup can only delete configs with 'selftest-' prefix

    2. HIGH_RISK_RESOURCE_TYPES (ip4_block, ip4_network, dns_zone):
       - Blocked by default
       - Can be bypassed with --allow-dangerous-operations flag

    3. Other resources (ip4_address, host_record, etc.):
       - Safe to delete via normal CSV import
"""

from typing import Any

import structlog

from ..models.operations import OperationType
from ..utils.exceptions import ValidationError

logger = structlog.get_logger(__name__)

# SAFETY TIER SYSTEM: Three-Level Protection Against Destructive Operations
# ==========================================================================
#
# TIER 1: NEVER_DELETE_VIA_CSV (Absolute Restriction)
# ---------------------------------------------------
# Resources: configuration, view
# Protection Level: PERMANENT BLOCK - Cannot be bypassed by ANY flag
# Rationale:
#   - Deleting a configuration destroys ALL child resources (blocks, networks,
#     addresses, DHCP services, DNS zones, records) across the entire system
#   - Deleting a view destroys ALL zones and records in that namespace
#   - Risk: Catastrophic data loss affecting entire organizations
#   - Recovery: Often impossible (need full backup restore)
#
# Exception: Self-test cleanup CAN delete configs with 'selftest-' prefix
# for automated testing cleanup only.
#
# TIER 2: HIGH_RISK_RESOURCE_TYPES (Bypassable with Flag)
# ---------------------------------------------------------
# Resources: ip4_block, ip4_network, ip6_block, ip6_network, dns_zone
# Protection Level: Blocked by default, --allow-dangerous-operations bypasses
# Rationale:
#   - Deleting blocks cascades to all contained networks and addresses
#   - Deleting networks cascades to all addresses, DHCP ranges, reservations
#   - Deleting zones cascades to all DNS records (A, AAAA, CNAME, MX, etc.)
#   - Risk: Significant data loss, service disruption
#   - Recovery: Difficult but possible with exports or backups
#
# TIER 3: SAFE_TO_DELETE (No Restrictions)
# ------------------------------------------
# Resources: ip4_address, ip6_address, host_record, alias_record, etc.
# Protection Level: None (can delete freely via CSV)
# Rationale:
#   - Leaf-level resources with minimal cascading effects
#   - Deletion is reversible (can recreate from CSV)
#   - Low risk of unintended consequences
#
# IMPLEMENTATION NOTES:
# ====================
# - validate_operation_safety() called BEFORE execution planning
# - check_csv_for_dangerous_operations() called during validation
# - Both functions check TIER 1 first (absolute block) then TIER 2 (conditional)
# - Error messages clearly distinguish between tiers to guide users

# Tier 1: Absolute Restriction (Cannot be bypassed)
NEVER_DELETE_VIA_CSV = {
    "configuration",  # CRITICAL: Deletes entire IP/DNS infrastructure
    "view",  # CRITICAL: Deletes all zones and records in namespace
}

# Legacy name for backward compatibility
DANGEROUS_RESOURCE_TYPES = NEVER_DELETE_VIA_CSV

# Tier 2: High Risk (Requires --allow-dangerous-operations)
HIGH_RISK_RESOURCE_TYPES = {
    "ip4_block",  # Cascades to all contained networks and addresses
    "ip4_network",  # Cascades to all addresses and DHCP ranges
    "ip6_block",  # Cascades to all contained IPv6 networks and addresses
    "ip6_network",  # Cascades to all IPv6 addresses and DHCPv6 ranges
    "dns_zone",  # Cascades to all DNS records (A, AAAA, CNAME, MX, TXT, etc.)
}

# All resource types that require explicit permission to delete
# The --allow-dangerous-operations flag is required for any DELETE operation on these types
PROTECTED_RESOURCE_TYPES = DANGEROUS_RESOURCE_TYPES | HIGH_RISK_RESOURCE_TYPES
DANGEROUS_OPERATIONS = {OperationType.DELETE}


def validate_operation_safety(
    operations: list[Any],
    allow_dangerous_operations: bool = False,
) -> None:
    """
    Validate operations for safety constraints.

    Checks if any operations involve deleting protected resource types
    (configurations, views, blocks, networks, zones) and raises an error
    if explicit permission has not been granted.

    Args:
        operations: List of operations to validate.
        allow_dangerous_operations: Whether to allow dangerous operations.

    Raises:
        ValidationError: If dangerous operations are found but not allowed.
    """
    if not operations:
        return

    # ABSOLUTE RESTRICTION: Config and View deletions are NEVER allowed via CSV
    # This check cannot be bypassed by any flag
    never_delete_ops = [
        op
        for op in operations
        if (
            hasattr(op, "object_type")
            and hasattr(op, "operation_type")
            and op.object_type.lower() in NEVER_DELETE_VIA_CSV
            and op.operation_type in DANGEROUS_OPERATIONS
        )
    ]

    if never_delete_ops:
        op_details = []
        for op in never_delete_ops:
            row_id = getattr(op, "row_id", "unknown")
            op_type = getattr(op, "operation_type", None)
            op_type_name = op_type.name.upper() if op_type and hasattr(op_type, "name") else "UNKNOWN"
            obj_type = getattr(op, "object_type", "unknown")
            op_details.append(f"  - Row {row_id}: {op_type_name} {obj_type}")

        error_msg = (
            f"ABSOLUTE SAFETY VIOLATION: Found {len(never_delete_ops)} forbidden operation(s):\n"
            + "\n".join(op_details)
            + "\n\nDeletion of configurations and views via CSV import is PERMANENTLY BLOCKED. "
            "This restriction cannot be bypassed. These resources can only be managed "
            "directly in BlueCat Address Manager."
        )

        logger.error(
            "Forbidden operations blocked (config/view deletion)",
            count=len(never_delete_ops),
            operations=[
                {
                    "row_id": getattr(op, "row_id", None),
                    "object_type": getattr(op, "object_type", None),
                    "operation_type": getattr(op, "operation_type", None),
                }
                for op in never_delete_ops
            ],
        )

        raise ValidationError(error_msg)

    # Use list comprehension for filtering dangerous operations
    dangerous_ops = [
        op
        for op in operations
        if (
            hasattr(op, "object_type")
            and hasattr(op, "operation_type")
            and op.object_type.lower() in PROTECTED_RESOURCE_TYPES
            and op.operation_type in DANGEROUS_OPERATIONS
        )
    ]

    if dangerous_ops and not allow_dangerous_operations:
        # Format detailed error message using list comprehension
        op_details = [
            f"  - Row {getattr(op, 'row_id', 'unknown')}: "
            f"{getattr(op, 'operation_type', 'unknown').upper()} "
            f"{getattr(op, 'object_type', 'unknown')}"
            for op in dangerous_ops
        ]

        error_msg = (
            f"CRITICAL SAFETY VIOLATION: Found {len(dangerous_ops)} dangerous operation(s) "
            f"that could cause catastrophic data loss:\n"
            + "\n".join(op_details)
            + "\n\nThese operations require explicit permission with --allow-dangerous-operations flag. "
            "Deletion of configurations and views is EXTREMELY DANGEROUS and can destroy "
            "critical infrastructure."
        )

        logger.error(
            "Dangerous operations blocked",
            count=len(dangerous_ops),
            operations=[
                {
                    "row_id": getattr(op, "row_id", None),
                    "object_type": getattr(op, "object_type", None),
                    "operation_type": getattr(op, "operation_type", None),
                }
                for op in dangerous_ops
            ],
        )

        raise ValidationError(error_msg)

    if dangerous_ops and allow_dangerous_operations:
        logger.warning(
            "DANGEROUS OPERATIONS APPROVED",
            count=len(dangerous_ops),
            operations=[
                {
                    "row_id": getattr(op, "row_id", None),
                    "object_type": getattr(op, "object_type", None),
                    "operation_type": getattr(op, "operation_type", None),
                }
                for op in dangerous_ops
            ],
            warning="User has explicitly allowed dangerous operations",
        )


def check_csv_for_dangerous_operations(
    csv_data: list[dict[str, Any]],
    allow_dangerous_operations: bool = False,
) -> None:
    """
    Check CSV data for potentially dangerous operations.

    Scans parsed CSV data for rows that attempt to delete protected resources.
    This is a pre-flight check before any processing begins.

    Args:
        csv_data: Parsed CSV data as list of dictionaries.
        allow_dangerous_operations: Whether to allow dangerous operations.

    Raises:
        ValidationError: If dangerous operations are found but not allowed.
    """
    # ABSOLUTE RESTRICTION: Config and View deletions are NEVER allowed via CSV
    # This check runs first and cannot be bypassed by any flag
    never_delete_rows = []
    for row in csv_data:
        object_type = row.get("object_type", "").lower()
        action = row.get("action", "").lower()
        row_id = row.get("row_id", "unknown")

        if object_type in NEVER_DELETE_VIA_CSV and action == "delete":
            never_delete_rows.append(
                {
                    "row_id": row_id,
                    "object_type": object_type,
                    "action": action,
                    "name": row.get("name", "unnamed"),
                }
            )

    if never_delete_rows:
        row_details = [
            f"  - Row {row['row_id']}: {row['action'].upper()} {row['object_type']} "
            f"'{row['name']}'"
            for row in never_delete_rows
        ]

        error_msg = (
            f"ABSOLUTE SAFETY VIOLATION: CSV contains {len(never_delete_rows)} forbidden operation(s):\n"
            + "\n".join(row_details)
            + "\n\nDeletion of configurations and views via CSV import is PERMANENTLY BLOCKED. "
            "This restriction cannot be bypassed. These resources can only be managed "
            "directly in BlueCat Address Manager."
        )

        logger.error(
            "Forbidden CSV operations blocked (config/view deletion)",
            count=len(never_delete_rows),
            rows=never_delete_rows,
        )

        raise ValidationError(error_msg)

    dangerous_rows = []

    for row in csv_data:
        object_type = row.get("object_type", "").lower()
        action = row.get("action", "").lower()
        row_id = row.get("row_id", "unknown")

        if object_type in PROTECTED_RESOURCE_TYPES and action == "delete":
            dangerous_rows.append(
                {
                    "row_id": row_id,
                    "object_type": object_type,
                    "action": action,
                    "name": row.get("name", "unnamed"),
                }
            )

    if dangerous_rows and not allow_dangerous_operations:
        row_details = []
        for row in dangerous_rows:
            row_details.append(
                f"  - Row {row['row_id']}: {row['action'].upper()} {row['object_type']} "
                f"'{row['name']}'"
            )

        error_msg = (
            f"CRITICAL SAFETY VIOLATION: CSV contains {len(dangerous_rows)} dangerous operation(s):\n"
            + "\n".join(row_details)
            + "\n\nThese operations require explicit permission with --allow-dangerous-operations flag. "
            "Deletion of configurations and views is EXTREMELY DANGEROUS and can destroy "
            "critical infrastructure."
        )

        logger.error(
            "Dangerous CSV operations blocked", count=len(dangerous_rows), rows=dangerous_rows
        )

        raise ValidationError(error_msg)

    if dangerous_rows and allow_dangerous_operations:
        logger.warning(
            "DANGEROUS CSV OPERATIONS APPROVED",
            count=len(dangerous_rows),
            rows=dangerous_rows,
            warning="User has explicitly allowed dangerous operations",
        )
