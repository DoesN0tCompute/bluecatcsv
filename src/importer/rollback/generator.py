"""Rollback Generator - Generate inverse CSV for rollback operations.

Creates CSV files that can undo changes made by an import session.

Purpose:
-------
After an import session completes (or fails partway), the RollbackGenerator
creates a CSV file containing operations that will undo the changes made.
This enables safe recovery from unwanted imports.

Operation Inversion:
-------------------
Original Operation  ->  Rollback Operation
CREATE              ->  DELETE (using resource_id from after_state)
UPDATE              ->  UPDATE (using before_state to restore original values)
DELETE              ->  CREATE (using before_state to recreate - risky/complex)

Example:
-------
If import created:
  Row 1: CREATE ip4_network 10.1.0.0/24 (resource_id=456)
  Row 2: CREATE ip4_address 10.1.0.5 (resource_id=789)

Rollback CSV would contain (in reverse order):
  Row 1: DELETE ip4_address (resource_id=789)
  Row 2: DELETE ip4_network (resource_id=456)

Note: Reverse order is critical because dependent resources must be deleted
before their parents (can't delete network with addresses in it).

Output Format:
-------------
Rollback CSV is saved to rollbacks/<session_id>_rollback.csv with:
- Comment header describing source session
- Standard CSV columns for the resource type
- action=delete with bam_id set to resource_id

Limitations:
-----------
1. DELETE rollbacks require recreating resources from before_state, which
   may be incomplete (e.g., missing custom fields, associations)
2. Some operations are not safely reversible (e.g., config/view deletion)
3. Time-sensitive data may have changed between import and rollback

Usage:
-----
```python
generator = RollbackGenerator(changelog)
stats = generator.generate_rollback_csv(
    session_id="import-12345",
    output_path=Path("rollbacks/import-12345_rollback.csv"),
    include_updates=True
)
```
"""

import csv
import json
from pathlib import Path
from typing import Any

import structlog

from ..persistence.changelog import ChangeLog, ChangeLogEntry

logger = structlog.get_logger(__name__)


class RollbackGenerator:
    """
    Generate inverse CSV files for rollback operations.

    Features:
    - Generates DELETE operations for successful CREATEs
    - Generates UPDATE operations to restore previous state
    - Maintains field order for readability
    - Includes metadata comments
    """

    def __init__(self, changelog: ChangeLog) -> None:
        """
        Initialize Rollback Generator.

        Args:
            changelog: ChangeLog instance
        """
        self.changelog = changelog

    def generate_rollback_csv(
        self,
        session_id: str,
        output_path: Path,
        include_updates: bool = True,
    ) -> dict[str, Any]:
        """
        Generate rollback CSV for a session.

        Args:
            session_id: Session to generate rollback for
            output_path: Path to write rollback CSV
            include_updates: Whether to include UPDATE rollbacks

        Returns:
            Dictionary with rollback statistics
        """
        logger.info(
            "Generating rollback CSV",
            session_id=session_id,
            output_path=str(output_path),
        )

        entries = self.changelog.get_session_entries(session_id)

        # Filter to successful operations only
        successful_entries = [e for e in entries if e.success]

        # Generate inverse operations
        rollback_rows = []

        for entry in reversed(successful_entries):  # Reverse order for rollback
            if entry.operation_type == "create":
                # CREATE → DELETE
                rollback_row = self._create_delete_row(entry)
                if rollback_row:
                    rollback_rows.append(rollback_row)

            elif entry.operation_type == "update" and include_updates:
                # UPDATE → UPDATE (restore previous state)
                rollback_row = self._create_restore_row(entry)
                if rollback_row:
                    rollback_rows.append(rollback_row)

            elif entry.operation_type == "delete":
                # DELETE → CREATE (recreate resource)
                # This is complex and risky - log warning
                logger.warning(
                    "DELETE operation in changelog - rollback requires recreation",
                    entry_id=entry.id,
                    resource_id=entry.resource_id,
                )
                # Could implement if before_state is complete enough

        # Write CSV
        if rollback_rows:
            self._write_csv(output_path, rollback_rows, session_id)

        stats = {
            "session_id": session_id,
            "total_entries": len(entries),
            "successful_entries": len(successful_entries),
            "rollback_operations": len(rollback_rows),
            "output_path": str(output_path),
        }

        logger.info(
            "Rollback CSV generated",
            session_id=session_id,
            rollback_operations=len(rollback_rows),
        )

        return stats

    def _create_delete_row(self, entry: ChangeLogEntry) -> dict[str, Any] | None:
        """
        Create DELETE row from CREATE entry.

        Args:
            entry: ChangeLog entry for CREATE operation

        Returns:
            Dictionary representing CSV row
        """
        if not entry.resource_id:
            logger.warning("No resource_id for CREATE entry", entry_id=entry.id)
            return None

        # Parse after_state to get resource details
        after_state = json.loads(entry.after_state) if entry.after_state else {}

        row = {
            "row_id": f"rollback_{entry.row_id}",
            "object_type": entry.object_type,
            "action": "delete",
            "bam_id": entry.resource_id,
            "verify_name": after_state.get("name", ""),
            "verify_address": after_state.get("address", ""),
            "_comment": f"Rollback CREATE from session {entry.session_id}",
        }

        return row

    def _create_restore_row(self, entry: ChangeLogEntry) -> dict[str, Any] | None:
        """
        Create UPDATE row to restore previous state.

        Args:
            entry: ChangeLog entry for UPDATE operation

        Returns:
            Dictionary representing CSV row
        """
        if not entry.resource_id or not entry.before_state:
            return None

        # Parse before_state to get previous values
        before_state = json.loads(entry.before_state)

        row = {
            "row_id": f"rollback_{entry.row_id}",
            "object_type": entry.object_type,
            "action": "update",
            "bam_id": entry.resource_id,
            "_comment": f"Restore from session {entry.session_id}",
        }

        # Add all fields from before_state
        for key, value in before_state.items():
            if key not in ("id", "type"):
                row[key] = value

        return row

    def _write_csv(
        self,
        output_path: Path,
        rows: list[dict[str, Any]],
        session_id: str,
    ) -> None:
        """
        Write rollback CSV file.

        Args:
            output_path: Output file path
            rows: List of row dictionaries
            session_id: Session ID for header comment
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not rows:
            logger.warning("No rows to write")
            return

        # Determine all columns
        all_columns: set[str] = set()
        for row in rows:
            all_columns.update(row.keys())

        # Order columns logically
        ordered_columns = [
            "row_id",
            "object_type",
            "action",
            "bam_id",
            "config",
            "view_path",
            "parent",
            "name",
            "address",
            "cidr",
            "mac",
            "verify_name",
            "verify_address",
            "_comment",
        ]

        # Add any remaining columns
        for col in sorted(all_columns):
            if col not in ordered_columns:
                ordered_columns.append(col)

        # Filter to only columns that exist
        columns = [col for col in ordered_columns if col in all_columns]

        # Write CSV
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            # Write header comment
            timestamp = json.dumps({"timestamp": "now"})  # Simplified timestamp
            f.write(f"# Rollback CSV for session: {session_id}\n")
            f.write(f"# Generated: {timestamp}\n")
            f.write(f"# Operations: {len(rows)}\n")
            f.write("#\n")

            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()

            for row in rows:
                writer.writerow(row)

        logger.info("Rollback CSV written", path=str(output_path), rows=len(rows))

    def get_rollback_manifest(self, session_id: str) -> dict[str, Any]:
        """
        Get rollback manifest with summary.

        Args:
            session_id: Session ID

        Returns:
            Manifest dictionary
        """
        entries = self.changelog.get_session_entries(session_id)
        successful = [e for e in entries if e.success]

        creates = [e for e in successful if e.operation_type == "create"]
        updates = [e for e in successful if e.operation_type == "update"]
        deletes = [e for e in successful if e.operation_type == "delete"]

        manifest = {
            "session_id": session_id,
            "total_operations": len(entries),
            "successful_operations": len(successful),
            "rollback_required": {
                "deletes_for_creates": len(creates),
                "restores_for_updates": len(updates),
                "recreates_for_deletes": len(deletes),
            },
            "resources": [
                {
                    "resource_id": e.resource_id,
                    "object_type": e.object_type,
                    "operation": e.operation_type,
                }
                for e in successful
            ],
        }
        return manifest
