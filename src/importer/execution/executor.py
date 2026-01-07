"""Operation Executor - Execute operations against BAM with throttling and error handling.

Executes operations from execution plan with concurrency control and retries.
"""

import asyncio
import copy
import time
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from ..dependency.graph import DependencyGraph

from ..bam.client import BAMClient
from ..config import PolicyConfig, ThrottleConfig
from ..models.operations import Operation, OperationStatus, OperationType
from ..models.results import OperationResult
from ..persistence.checkpoint import CheckpointManager
from ..utils.exceptions import (
    BAMRateLimitError,
    DeferredResolutionError,
    ResourceAlreadyExistsError,
    ResourceNotFoundError,
)
from .handlers import get_handler
from .planner import ExecutionBatch, ExecutionPlan
from .throttle import AdaptiveThrottle

logger = structlog.get_logger(__name__)


class OperationExecutor:
    """
    Execute operations against BAM with concurrency control and error recovery.

    Execution Strategy:
    1. Sequential batches: All operations in batch N complete before batch N+1 starts
       - Enforces dependency barriers
       - Prevents resource conflicts
       - Simplifies error recovery

    2. Parallel operations within batch: Concurrency limited by throttle
       - Maximizes throughput
       - Respects API limits
       - Maintains ordering guarantees
    """

    def __init__(
        self,
        bam_client: BAMClient,
        policy: PolicyConfig,
        throttle: AdaptiveThrottle | None = None,
        allow_dangerous_operations: bool = False,
        dependency_graph: Optional["DependencyGraph"] = None,
        checkpoint_manager: CheckpointManager | None = None,
        session_id: str | None = None,
        initial_created_resources: dict[str, dict[str, int]] | None = None,
    ) -> None:
        """
        Initialize executor with throttling and safety controls.

        Args:
            bam_client: Authenticated BAM client for API operations
            policy: Policy configuration defining safety rules and limits
            throttle: Optional custom throttle (creates from policy if None)
            allow_dangerous_operations: Allow deletion of critical resources
            dependency_graph: Optional dependency graph for cascading failure handling
            checkpoint_manager: Optional checkpoint manager for persistence
            session_id: Optional session ID for checkpointing
            initial_created_resources: Optional pre-populated created resources maps
                for resume support. Structure: {'block': {cidr: id}, 'network': {...}, ...}
        """
        self.client = bam_client
        self.policy = policy
        self.allow_dangerous_operations = allow_dangerous_operations

        # Initialize throttle from policy if not provided
        if throttle is None:
            # Create throttle with policy-defined concurrency limits
            throttle_config = ThrottleConfig(
                initial_concurrency=policy.max_concurrent_operations,
                min_concurrency=policy.min_concurrency,
                max_concurrency=policy.max_concurrency,
            )
            self.throttle = AdaptiveThrottle(throttle_config)
        else:
            self.throttle = throttle

        # Runtime state
        self.dry_run = False
        self.results: list[OperationResult] = []

        # Dependency graph for cascading failure handling
        self.dependency_graph = dependency_graph

        # Checkpointing
        self.checkpoint_manager = checkpoint_manager
        self.session_id = session_id

        # Track failed operations to cascade failures
        self.failed_operations: set[str] = set()
        # Track operations that have been marked as skipped
        self.skipped_operations: dict[str, str] = {}  # operation_id -> reason

        # Deferred resolution tracking
        # Enables resources created earlier in a batch to be referenced by later operations
        # Example: Block created in row 1, Network in row 2 needs block_id
        # These maps can be pre-populated from checkpoint on resume
        if initial_created_resources:
            self.created_blocks = dict(initial_created_resources.get("block", {}))
            self.created_networks = dict(initial_created_resources.get("network", {}))
            self.created_zones = dict(initial_created_resources.get("zone", {}))
            self.created_locations = dict(initial_created_resources.get("location", {}))
            self.created_device_types = dict(
                initial_created_resources.get("device_type", {})
            )
            self.created_device_subtypes = dict(
                initial_created_resources.get("device_subtype", {})
            )
            self.created_devices = dict(initial_created_resources.get("device", {}))
        else:
            self.created_blocks = {}  # CIDR -> block_id
            self.created_networks = {}  # CIDR -> network_id
            self.created_zones = {}  # zone_name -> zone_id
            self.created_locations = {}  # location_code -> location_id
            self.created_device_types = {}  # name -> device_type_id
            self.created_device_subtypes = {}  # name -> device_subtype_id
            self.created_devices = {}  # config/name -> device_id

    async def execute_plan(
        self,
        plan: ExecutionPlan,
        dry_run: bool = False,
        start_batch_id: int = 0,
        input_hash: str | None = None,
    ) -> list[OperationResult]:
        """
        Execute all operations in plan with proper ordering and error handling.

        Execution Guarantees:
        1. All operations in a batch complete before next batch starts
        2. Operations within a batch run in parallel (subject to throttle)
        3. Failed operations don't prevent others from completing
        4. Results include detailed error information for debugging

        Args:
            plan: Execution plan containing batches of operations
            dry_run: Simulate execution without API calls

        Returns:
            List of results for all operations in execution order
        """
        self.dry_run = dry_run
        self.results = []

        logger.info(
            "Starting plan execution",
            total_operations=plan.total_operations,
            batch_count=len(plan.batches),
            dry_run=dry_run,
        )

        execution_start = time.time()

        # Execute batches sequentially to maintain dependency order
        for batch_index, batch in enumerate(plan.batches):
            logger.info(
                "Executing batch",
                batch_id=batch.batch_id,
                batch_number=batch_index + 1,
                total_batches=len(plan.batches),
                operations_in_batch=len(batch.operations),
                depth=batch.depth,
            )

            # Check if we should skip this batch (resume logic)
            if batch.batch_id < start_batch_id:
                logger.info(
                    "Skipping batch (already completed)",
                    batch_id=batch.batch_id,
                    reason="resume",
                )
                continue

            # All operations in batch execute in parallel
            batch_results = await self._execute_batch(batch)
            self.results.extend(batch_results)

            # Log batch completion stats
            batch_successful = sum(1 for r in batch_results if r.success)
            logger.info(
                "Batch completed",
                batch_id=batch.batch_id,
                successful=batch_successful,
                failed=len(batch_results) - batch_successful,
                total=len(batch_results),
            )

            # Save checkpoint if configured and not dry run
            if self.checkpoint_manager and self.session_id and not self.dry_run:
                completed_count = sum(1 for r in self.results if r.success)
                self.checkpoint_manager.save_checkpoint(
                    session_id=self.session_id,
                    batch_id=batch.batch_id,
                    operation_index=len(self.results),
                    completed_operations=completed_count,
                    total_operations=plan.total_operations,
                    input_hash=input_hash,
                )

        # Final execution statistics
        total_duration = time.time() - execution_start
        total_successful = sum(1 for r in self.results if r.success)
        total_failed = len(self.results) - total_successful

        logger.info(
            "Plan execution complete",
            duration_seconds=f"{total_duration:.2f}",
            total_operations=len(self.results),
            successful=total_successful,
            failed=total_failed,
            success_rate=f"{total_successful / len(self.results):.1%}" if self.results else "N/A",
            final_throttle_state=self.throttle.get_metrics(),
        )

        return self.results

    async def _execute_batch(self, batch: ExecutionBatch) -> list[OperationResult]:
        """
        Execute a single batch of operations in parallel.

        Args:
            batch: Execution batch

        Returns:
            List of operation results
        """
        logger.debug("Executing batch", batch_id=batch.batch_id, operations=len(batch.operations))

        # Execute all operations in parallel with throttling
        tasks = [self._execute_operation(op) for op in batch.operations]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        batch_results: list[OperationResult] = []
        for op, result in zip(batch.operations, results, strict=True):
            if isinstance(result, Exception):
                # Handle exception
                batch_results.append(
                    OperationResult(
                        row_id=op.row_id,
                        operation=op.operation_type,
                        success=False,
                        error_message=str(result),
                        duration_ms=0,
                    )
                )
            else:
                batch_results.append(result)

        return batch_results

    def _resolve_deferred_ids(self, operation: Operation) -> None:
        """
        Resolve placeholder IDs with actual resource IDs from earlier operations.

        Deferred Resolution Problem:
        When building the dependency graph, some operations need to reference
        resources that haven't been created yet. We insert placeholders that
        get resolved just before execution.

        This mechanism is CRITICAL for idempotency and graph integrity. It decouples
        graph construction (which happens before any API calls) from execution (which
        produces the actual IDs).

        Example Flow:
        1. CSV row 1: CREATE block 10.0.0.0/8
        2. CSV row 2: CREATE network 10.0.0.0/24 (needs block_id)
        3. Graph builder: Adds placeholder "_deferred_block_cidr": "10.0.0.0/8"
        4. At execution: Check if block 10.0.0.0/8 was created earlier
        5. If yes: Replace placeholder with actual block_id
        6. If no: Raise DeferredResolutionError to fail fast with clear message

        Raises:
            DeferredResolutionError: If a deferred dependency cannot be resolved
        """
        payload = operation.payload

        # Check for deferred block references
        if "_deferred_block_cidr" in payload:
            block_cidr = payload["_deferred_block_cidr"]
            if block_cidr in self.created_blocks:
                # Resolve to actual block ID
                payload["block_id"] = self.created_blocks[block_cidr]
                logger.info(
                    "Resolved deferred block ID",
                    row_id=operation.row_id,
                    block_cidr=block_cidr,
                    resolved_id=payload["block_id"],
                )
                # Clean up deferred key after resolution
                del payload["_deferred_block_cidr"]
            else:
                # Parent block was not created - fail fast with clear error
                logger.error(
                    "Deferred block ID resolution failed",
                    row_id=operation.row_id,
                    block_cidr=block_cidr,
                    available_blocks=list(self.created_blocks.keys()),
                )
                raise DeferredResolutionError(
                    row_id=operation.row_id,
                    resource_type="block",
                    deferred_key="_deferred_block_cidr",
                    deferred_value=block_cidr,
                )

        # Resolve deferred network_id
        if "_deferred_network_cidr" in payload:
            cidr = payload["_deferred_network_cidr"]
            if cidr in self.created_networks:
                payload["network_id"] = self.created_networks[cidr]
                logger.info(
                    "Resolved deferred network_id",
                    row_id=operation.row_id,
                    cidr=cidr,
                    network_id=payload["network_id"],
                )
                # Clean up deferred key after resolution
                del payload["_deferred_network_cidr"]
            else:
                # Parent network was not created - fail fast with clear error
                logger.error(
                    "Deferred network ID resolution failed",
                    row_id=operation.row_id,
                    network_cidr=cidr,
                    available_networks=list(self.created_networks.keys()),
                )
                raise DeferredResolutionError(
                    row_id=operation.row_id,
                    resource_type="network",
                    deferred_key="_deferred_network_cidr",
                    deferred_value=cidr,
                )

        # Resolve deferred zone_id
        if "_deferred_zone_name" in payload:
            zone_name = payload["_deferred_zone_name"]
            if zone_name in self.created_zones:
                payload["zone_id"] = self.created_zones[zone_name]
                logger.info(
                    "Resolved deferred zone_id",
                    row_id=operation.row_id,
                    zone_name=zone_name,
                    zone_id=payload["zone_id"],
                )
                # Clean up deferred key after resolution
                del payload["_deferred_zone_name"]
            else:
                # Parent zone was not created - fail fast with clear error
                logger.error(
                    "Deferred zone ID resolution failed",
                    row_id=operation.row_id,
                    zone_name=zone_name,
                    available_zones=list(self.created_zones.keys()),
                )
                raise DeferredResolutionError(
                    row_id=operation.row_id,
                    resource_type="zone",
                    deferred_key="_deferred_zone_name",
                    deferred_value=zone_name,
                )

        # Resolve deferred location references
        if "_deferred_location_code" in payload:
            location_code = payload["_deferred_location_code"]
            if location_code in self.created_locations:
                location_id = self.created_locations[location_code]
                # For location objects, set parent_location_id
                # For other resources, set location association
                if operation.object_type == "location":
                    payload["parent_location_id"] = location_id
                    logger.info(
                        "Resolved deferred parent_location_id",
                        row_id=operation.row_id,
                        location_code=location_code,
                        parent_location_id=location_id,
                    )
                else:
                    payload["location"] = {"id": location_id}
                    logger.info(
                        "Resolved deferred location association",
                        row_id=operation.row_id,
                        location_code=location_code,
                        location_id=location_id,
                    )
                # Clean up deferred key after resolution
                del payload["_deferred_location_code"]
            else:
                # Location was not created - fail fast with clear error
                logger.error(
                    "Deferred location ID resolution failed",
                    row_id=operation.row_id,
                    location_code=location_code,
                    available_locations=list(self.created_locations.keys()),
                )
                raise DeferredResolutionError(
                    row_id=operation.row_id,
                    resource_type="location",
                    deferred_key="_deferred_location_code",
                    deferred_value=location_code,
                )

        # Resolve deferred device_type references
        if "_deferred_device_type_name" in payload:
            device_type_name = payload["_deferred_device_type_name"]
            if device_type_name in self.created_device_types:
                payload["device_type_id"] = self.created_device_types[device_type_name]
                logger.info(
                    "Resolved deferred device_type_id",
                    row_id=operation.row_id,
                    device_type_name=device_type_name,
                    device_type_id=payload["device_type_id"],
                )
                del payload["_deferred_device_type_name"]
                if "_deferred_device_type_row" in payload:
                    del payload["_deferred_device_type_row"]
            else:
                logger.error(
                    "Deferred device_type ID resolution failed",
                    row_id=operation.row_id,
                    device_type_name=device_type_name,
                    available_device_types=list(self.created_device_types.keys()),
                )
                raise DeferredResolutionError(
                    row_id=operation.row_id,
                    resource_type="device_type",
                    deferred_key="_deferred_device_type_name",
                    deferred_value=device_type_name,
                )

        # Resolve deferred device_subtype references
        if "_deferred_device_subtype_name" in payload:
            device_subtype_name = payload["_deferred_device_subtype_name"]
            if device_subtype_name in self.created_device_subtypes:
                payload["device_subtype_id"] = self.created_device_subtypes[
                    device_subtype_name
                ]
                logger.info(
                    "Resolved deferred device_subtype_id",
                    row_id=operation.row_id,
                    device_subtype_name=device_subtype_name,
                    device_subtype_id=payload["device_subtype_id"],
                )
                del payload["_deferred_device_subtype_name"]
                if "_deferred_device_subtype_row" in payload:
                    del payload["_deferred_device_subtype_row"]
            else:
                logger.error(
                    "Deferred device_subtype ID resolution failed",
                    row_id=operation.row_id,
                    device_subtype_name=device_subtype_name,
                    available_device_subtypes=list(self.created_device_subtypes.keys()),
                )
                raise DeferredResolutionError(
                    row_id=operation.row_id,
                    resource_type="device_subtype",
                    deferred_key="_deferred_device_subtype_name",
                    deferred_value=device_subtype_name,
                )

        # Resolve deferred device references (for device_address operations)
        if "_deferred_device_name" in payload:
            device_name = payload["_deferred_device_name"]
            device_config = payload.get("_deferred_device_config", "")
            device_key = f"{device_config}/{device_name}" if device_config else device_name
            if device_key in self.created_devices:
                payload["device_id"] = self.created_devices[device_key]
                logger.info(
                    "Resolved deferred device_id",
                    row_id=operation.row_id,
                    device_name=device_name,
                    device_id=payload["device_id"],
                )
                del payload["_deferred_device_name"]
                if "_deferred_device_config" in payload:
                    del payload["_deferred_device_config"]
                if "_deferred_device_row" in payload:
                    del payload["_deferred_device_row"]
            else:
                logger.error(
                    "Deferred device ID resolution failed",
                    row_id=operation.row_id,
                    device_key=device_key,
                    available_devices=list(self.created_devices.keys()),
                )
                raise DeferredResolutionError(
                    row_id=operation.row_id,
                    resource_type="device",
                    deferred_key="_deferred_device_name",
                    deferred_value=device_key,
                )

    def _store_created_resource(self, operation: Operation, resource_id: int) -> None:
        """Store created resource ID for deferred resolution.

        This method:
        1. Updates the in-memory maps for immediate deferred resolution
        2. Persists to checkpoint database for resume support

        The persistence ensures that if the session is interrupted and resumed,
        resources created in earlier (now skipped) batches can still be resolved
        by operations in later batches that depend on them.
        """
        csv_row = operation.csv_row
        if not csv_row:
            return

        resource_type: str | None = None
        resource_key: str | None = None

        if operation.object_type == "ip4_block":
            cidr = getattr(csv_row, "cidr", None)
            if cidr:
                self.created_blocks[cidr] = resource_id
                resource_type = "block"
                resource_key = cidr
                logger.debug("Stored created block", cidr=cidr, id=resource_id)

        elif operation.object_type == "ip4_network":
            cidr = getattr(csv_row, "cidr", None)
            if cidr:
                self.created_networks[cidr] = resource_id
                resource_type = "network"
                resource_key = cidr
                logger.debug("Stored created network", cidr=cidr, id=resource_id)

        elif operation.object_type == "dns_zone":
            zone_name = getattr(csv_row, "zone_name", None)
            if zone_name:
                self.created_zones[zone_name] = resource_id
                resource_type = "zone"
                resource_key = zone_name
                logger.debug("Stored created zone", zone_name=zone_name, id=resource_id)

        elif operation.object_type == "location":
            code = getattr(csv_row, "code", None)
            if code:
                self.created_locations[code] = resource_id
                resource_type = "location"
                resource_key = code
                logger.debug("Stored created location", code=code, id=resource_id)

        elif operation.object_type == "ip6_block":
            cidr = getattr(csv_row, "cidr", None)
            if cidr:
                self.created_blocks[cidr] = resource_id
                resource_type = "block"
                resource_key = cidr
                logger.debug("Stored created ipv6 block", cidr=cidr, id=resource_id)

        elif operation.object_type == "ip6_network":
            cidr = getattr(csv_row, "cidr", None)
            if cidr:
                self.created_networks[cidr] = resource_id
                resource_type = "network"
                resource_key = cidr
                logger.debug("Stored created ipv6 network", cidr=cidr, id=resource_id)

        elif operation.object_type == "device_type":
            name = getattr(csv_row, "name", None)
            if name:
                self.created_device_types[name] = resource_id
                resource_type = "device_type"
                resource_key = name
                logger.debug("Stored created device_type", name=name, id=resource_id)

        elif operation.object_type == "device_subtype":
            name = getattr(csv_row, "name", None)
            if name:
                self.created_device_subtypes[name] = resource_id
                resource_type = "device_subtype"
                resource_key = name
                logger.debug("Stored created device_subtype", name=name, id=resource_id)

        elif operation.object_type == "device":
            name = getattr(csv_row, "name", None)
            config = getattr(csv_row, "config", None)
            if name and config:
                # Use consistent key format matching pending.devices indexing
                # Devices are per-configuration resources, both name and config required
                device_key = f"{config}/{name}"
                self.created_devices[device_key] = resource_id
                resource_type = "device"
                resource_key = device_key
                logger.debug("Stored created device", name=name, config=config, id=resource_id)
            elif name:
                # Fallback for devices without config (shouldn't happen in normal operation)
                # Store by name only, won't match deferred resolution expectations
                self.created_devices[name] = resource_id
                resource_type = "device"
                resource_key = name
                logger.warning(
                    "Stored device without config - may cause deferred resolution failures",
                    name=name,
                    id=resource_id,
                )

        # Persist to checkpoint database for resume support
        if (
            resource_type
            and resource_key
            and self.checkpoint_manager
            and self.session_id
            and not self.dry_run
        ):
            self.checkpoint_manager.save_created_resource(
                session_id=self.session_id,
                resource_type=resource_type,
                resource_key=resource_key,
                bam_id=resource_id,
            )

    async def _execute_operation(self, operation: Operation) -> OperationResult:
        """
        Execute a single operation with throttling and retries.

        Args:
            operation: Operation to execute

        Returns:
            OperationResult
        """
        # Check if operation should be skipped due to parent failure
        skipped_result = self._check_operation_skipped(operation)
        if skipped_result:
            return skipped_result

        # Check for pre-existing errors (fail-fast)
        if "error" in operation.payload:
            error_msg = operation.payload["error"]
            tb_str = operation.payload.get("traceback")

            logger.error(
                "Operation failed during Creation/Resolution",
                row_id=operation.row_id,
                error=error_msg,
                traceback=tb_str,
            )

            self._mark_operation_failed(operation, error_msg)

            return OperationResult(
                row_id=operation.row_id,
                operation=operation.operation_type,
                success=False,
                error_message=error_msg,
                duration_ms=0,
                metadata={"traceback": tb_str} if tb_str else {},
            )

        start_time = time.time()

        # Create a working copy of the operation for this execution attempt
        # This prevents in-place mutation of the original operation payload (by _resolve_deferred_ids)
        # ensuring idempotency for retries.
        working_op = copy.deepcopy(operation)

        # Resolve any deferred IDs before execution using the working copy
        self._resolve_deferred_ids(working_op)

        # Acquire throttle slot
        async with self.throttle:
            try:
                # Execute based on operation type using the working copy
                if working_op.operation_type == OperationType.CREATE:
                    result = await self._execute_create(working_op)
                elif working_op.operation_type == OperationType.UPDATE:
                    result = await self._execute_update(working_op)
                elif working_op.operation_type == OperationType.DELETE:
                    result = await self._execute_delete(working_op)
                elif working_op.operation_type == OperationType.NOOP:
                    result = self._execute_noop(working_op)
                else:
                    raise ValueError(f"Unknown operation type: {working_op.operation_type}")

                # Update the original operation with success state

                if not self.dry_run:
                    # Update the original operation with success state
                    operation.status = OperationStatus.SUCCEEDED
                    operation.resource_id = working_op.resource_id

                    # IMPORTANT: If success, we *do* want the resolved IDs to be reflected in the original
                    # operation payload if we want them there?
                    # Actually, for the purpose of the log/report, the resolved payload is better.
                    # So we update the original payload with the resolved one upon success.
                    operation.payload = working_op.payload

                # Record success metrics
                duration_ms = (time.time() - start_time) * 1000
                self.throttle.record_success(duration_ms)

                return result

            except BAMRateLimitError as e:
                # Handle rate limiting
                self.throttle.record_failure(is_rate_limit=True)
                logger.warning(
                    "Rate limit hit",
                    operation=operation.row_id,
                    retry_after=e.retry_after,
                )

                # Wait and retry
                await asyncio.sleep(e.retry_after)
                return await self._execute_operation(operation)

            except Exception as e:
                # Record failure
                self.throttle.record_failure(is_rate_limit=False)

                logger.error(
                    "Operation failed",
                    operation_type=operation.operation_type.value,
                    row_id=operation.row_id,
                    error=str(e),
                )

                # Mark operation as failed and cascade to dependents
                self._mark_operation_failed(operation, str(e))

                return OperationResult(
                    row_id=operation.row_id,
                    operation=operation.operation_type,
                    success=False,
                    error_message=str(e),
                    duration_ms=(time.time() - start_time) * 1000,
                )

    async def _execute_create(self, operation: Operation) -> OperationResult:
        """Execute CREATE operation using handler registry."""
        if self.dry_run:
            # Simulate resource creation for dependency chain
            # Use deterministic dummy ID based on row_id to ensure consistency
            dummy_id = abs(hash(str(operation.row_id))) % 1000000
            if dummy_id == 0:
                dummy_id = 1

            # Store for deferred resolution by dependent operations
            self._store_created_resource(operation, dummy_id)

            return OperationResult(
                row_id=operation.row_id,
                operation=operation.operation_type,
                success=True,
                resource_id=dummy_id,
                metadata={"dry_run": True},
            )

        # Get appropriate handler for this object type
        handler = get_handler(operation.object_type)

        try:
            # Execute CREATE operation using handler
            result = await handler.create(self.client, operation)

            # Handler may return OperationResult or dict - handle both
            if isinstance(result, OperationResult):
                # Handler returned OperationResult
                if not result.success:
                    raise ValueError(
                        result.error_message
                        or f"Handler for {operation.object_type} failed in row {operation.row_id}"
                    )
                resource_id = result.resource_id
            else:
                # Handler returned dict (API response)
                resource_id = result.get("id")
                result = OperationResult(
                    row_id=operation.row_id,
                    operation=operation.operation_type,
                    success=True,
                    resource_id=resource_id,
                )

            if not resource_id:
                raise ValueError(
                    f"Handler for {operation.object_type} did not return resource ID in row {operation.row_id}"
                )

        except ResourceAlreadyExistsError:
            # Resource already exists - look up the existing resource ID
            resource_id = await self._lookup_existing_resource(operation)
            if resource_id:
                logger.info(
                    "Resource already exists, using existing ID",
                    row_id=operation.row_id,
                    object_type=operation.object_type,
                    resource_id=resource_id,
                )
                result = OperationResult(
                    row_id=operation.row_id,
                    operation=operation.operation_type,
                    success=True,
                    resource_id=resource_id,
                    metadata={"already_exists": True},
                )
            else:
                # Could not find existing resource, re-raise the error
                raise

        operation.status = OperationStatus.SUCCEEDED
        operation.resource_id = resource_id

        # Store created resource for deferred resolution by dependent operations
        self._store_created_resource(operation, resource_id)

        return result

    async def _lookup_existing_resource(self, operation: Operation) -> int | None:
        """
        Look up the ID of an existing resource when a 409 Conflict occurs.

        Fallback Strategy:
        When a CREATE operation fails with 409 Conflict, the resource likely already exists.
        Instead of failing the operation, we look up the existing resource to maintain idempotency.

        Rationale:
        This allows the importer to be run multiple times on the same CSV without erroring out
        on resources that were already created in a previous run.

        Resolution Priority:
        1. Use the resource's unique identifier (CIDR for blocks/networks, name for zones, etc.)
        2. Search within the appropriate parent container (config, view, network)
        3. Return the existing ID if found to continue with dependent operations

        Performance Considerations:
        - This method performs additional API calls on conflicts
        - Lookups use the most specific search possible to avoid full enumeration
        - If multiple resources match, only the first is returned (shouldn't happen in normal cases)

        Args:
            operation: The operation that failed with 409

        Returns:
            Resource ID if found, None otherwise (operation will be retried)
        """
        csv_row = operation.csv_row
        if not csv_row:
            return None

        try:
            if operation.object_type == "ip4_block":
                # Block is uniquely identified by CIDR within a configuration
                cidr = getattr(csv_row, "cidr", None)
                config_id = operation.payload.get("config_id")
                if cidr and config_id:
                    block = await self.client.get_block_by_cidr_in_config(config_id, cidr)
                    return block.get("id") if block else None

            elif operation.object_type == "ip4_network":
                # Network is uniquely identified by CIDR within a configuration
                # Note: Networks can be looked up via parent block or global config search
                cidr = getattr(csv_row, "cidr", None)
                config_id = operation.payload.get("config_id")
                if cidr and config_id:
                    network = await self.client.get_network_by_cidr(config_id, cidr)
                    return network.get("id") if network else None

            elif operation.object_type == "ip6_block":
                cidr = getattr(csv_row, "cidr", None)
                config_id = operation.payload.get("config_id")
                if cidr and config_id:
                    block = await self.client.get_ip6_block_by_cidr_in_config(config_id, cidr)
                    return block.get("id") if block else None

            elif operation.object_type == "ip6_network":
                cidr = getattr(csv_row, "cidr", None)
                config_id = operation.payload.get("config_id")
                if cidr and config_id:
                    network = await self.client.get_network_by_cidr(config_id, cidr)
                    return network.get("id") if network else None

            elif operation.object_type == "location":
                code = getattr(csv_row, "code", None)
                if code:
                    location = await self.client.get_location_by_code(code)
                    return location.get("id") if location else None

            elif operation.object_type == "dns_zone":
                # Zone is uniquely identified by name within a view
                # Zone name can be in csv_row.zone_name or payload["name"]
                zone_name = getattr(csv_row, "zone_name", None) or operation.payload.get("name")
                view_id = operation.payload.get("view_id")
                if zone_name and view_id:
                    zone = await self.client.get_zone_by_fqdn(view_id, zone_name)
                    return zone.get("id") if zone else None

            elif operation.object_type == "ip4_address":
                # Address is uniquely identified by IP within a configuration
                address = getattr(csv_row, "address", None)
                config_id = operation.payload.get("config_id")
                if address and config_id:
                    addr = await self.client.get_ip4_address(config_id, address)
                    return addr.get("id") if addr else None

            elif operation.object_type == "ip6_address":
                address = getattr(csv_row, "address", None)
                config_id = operation.payload.get("config_id")
                if address and config_id:
                    addr = await self.client.get_ip6_address(config_id, address)
                    return addr.get("id") if addr else None

            elif operation.object_type in (
                "host_record",
                "alias_record",
                "mx_record",
                "txt_record",
                "srv_record",
                "external_host_record",
            ):
                # For DNS records, look up by name in the zone
                name = getattr(csv_row, "name", None)
                zone_id = operation.payload.get("zone_id")
                if name and zone_id:
                    # Try lookup by absoluteName first (for FQDNs like www.example.com)
                    records = await self.client.get(
                        f"zones/{zone_id}/resourceRecords",
                        params={"filter": f"absoluteName:'{name}'"},
                    )
                    if (
                        records
                        and isinstance(records, dict)
                        and "data" in records
                        and records["data"]
                    ):
                        for record in records["data"]:
                            if record.get("absoluteName") == name or record.get("name") == name:
                                return record.get("id")

                    # If not found, try lookup by short name (for names like www2)
                    records = await self.client.get(
                        f"zones/{zone_id}/resourceRecords", params={"filter": f"name:'{name}'"}
                    )
                    if (
                        records
                        and isinstance(records, dict)
                        and "data" in records
                        and records["data"]
                    ):
                        for record in records["data"]:
                            if record.get("name") == name:
                                return record.get("id")

        except ResourceNotFoundError:
            # Resource not found during lookup - this is expected if it was created and deleted
            logger.debug(
                "Resource not found during 409 lookup",
                row_id=operation.row_id,
                object_type=operation.object_type,
            )
        except Exception as e:
            logger.warning(
                "Failed to lookup existing resource",
                row_id=operation.row_id,
                object_type=operation.object_type,
                error=str(e),
            )

        return None

    async def _execute_update(self, operation: Operation) -> OperationResult:
        """Execute UPDATE operation using handler registry."""
        if self.dry_run:
            return OperationResult(
                row_id=operation.row_id,
                operation=operation.operation_type,
                success=True,
                resource_id=operation.resource_id,
                metadata={"dry_run": True},
            )

        # Get appropriate handler for this object type
        handler = get_handler(operation.object_type)

        # Execute UPDATE operation using handler
        await handler.update(self.client, operation)

        operation.status = OperationStatus.SUCCEEDED

        return OperationResult(
            row_id=operation.row_id,
            operation=operation.operation_type,
            success=True,
            resource_id=operation.resource_id,
        )

    async def _execute_delete(self, operation: Operation) -> OperationResult:
        """Execute DELETE operation using handler registry."""
        if self.dry_run:
            return OperationResult(
                row_id=operation.row_id,
                operation=operation.operation_type,
                success=True,
                resource_id=operation.resource_id,
                metadata={"dry_run": True},
            )

        # Get appropriate handler for this object type
        handler = get_handler(operation.object_type)

        # Execute DELETE operation using handler
        await handler.delete(
            self.client,
            operation,
            allow_dangerous_operations=self.allow_dangerous_operations,
        )

        operation.status = OperationStatus.SUCCEEDED

        return OperationResult(
            row_id=operation.row_id,
            operation=operation.operation_type,
            success=True,
            resource_id=operation.resource_id,
            metadata={"noop": True},
        )

    def _execute_noop(self, operation: Operation) -> OperationResult:
        """Execute NOOP operation (no-op)."""
        operation.status = OperationStatus.SUCCEEDED

        return OperationResult(
            row_id=operation.row_id,
            operation=operation.operation_type,
            success=True,
            resource_id=operation.resource_id,
        )

    def _mark_operation_failed(self, operation: Operation, error_message: str) -> None:
        """Mark an operation as failed and cascade to dependents.

        Args:
            operation: The operation that failed
            error_message: The error message explaining the failure
        """
        operation.mark_failure(error_message)
        operation_id = f"{operation.object_type}:{operation.row_id}"
        self.failed_operations.add(operation_id)

        # If we have a dependency graph, cascade the failure
        if self.dependency_graph:
            self._cascade_failure(operation, error_message)

    def _cascade_failure(self, failed_operation: Operation, error_message: str) -> None:
        """
        Mark all dependent operations as skipped using DFS traversal.

        Cascade Failure Algorithm:
        When an operation fails, all operations that depend on it cannot execute.
        This prevents partial updates and maintains data consistency.
        For example, we cannot create a network if the parent block failed to create.

        Algorithm Details:
        1. Find the failed node in the dependency graph
        2. Perform depth-first traversal of all dependent nodes
        3. Mark each unvisited dependent as SKIPPED with detailed reason
        4. Continue traversal recursively to catch transitive dependencies

        Why DFS:
        - Ensures we visit all dependents exactly once
        - Handles deep dependency chains efficiently
        - Maintains topological ordering for failure propagation

        Example:
        If block creation fails:
        - Networks in that block are skipped
        - Addresses in those networks are skipped
        - Records using those addresses are skipped

        Args:
            failed_operation: The operation that failed
            error_message: The error message from the failed operation
        """
        if not self.dependency_graph:
            return

        failed_node_id = f"{failed_operation.object_type}:{failed_operation.row_id}"

        # Find the node in the dependency graph
        if failed_node_id not in self.dependency_graph.nodes:
            return

        failed_node = self.dependency_graph.nodes[failed_node_id]

        # Perform DFS to find and mark all dependents as skipped
        to_visit = list(failed_node.dependents)
        visited = set()

        while to_visit:
            dependent_id = to_visit.pop()

            if dependent_id in visited:
                continue

            visited.add(dependent_id)

            if dependent_id in self.dependency_graph.nodes:
                dependent_node = self.dependency_graph.nodes[dependent_id]
                dependent_op = dependent_node.operation

                # Mark as skipped if not already failed or skipped
                if dependent_op.status not in [OperationStatus.FAILED, OperationStatus.SKIPPED]:
                    skip_reason = f"Skipped because parent {failed_operation.object_type}:{failed_operation.row_id} failed: {error_message}"
                    dependent_op.mark_skipped(skip_reason)
                    self.skipped_operations[dependent_id] = skip_reason

                    logger.warning(
                        "Operation skipped due to parent failure",
                        operation_type=dependent_op.object_type,
                        row_id=dependent_op.row_id,
                        parent_operation=failed_operation.object_type,
                        parent_row_id=failed_operation.row_id,
                        reason=error_message,
                    )

                    # Add this operation's dependents to the queue
                    to_visit.extend(dependent_node.dependents)

    def _check_operation_skipped(self, operation: Operation) -> OperationResult | None:
        """Check if an operation should be skipped due to parent failure.

        Args:
            operation: The operation to check

        Returns:
            OperationResult if operation should be skipped, None otherwise
        """
        operation_id = f"{operation.object_type}:{operation.row_id}"

        # Check if already marked as skipped
        if operation.status == OperationStatus.SKIPPED:
            return OperationResult(
                row_id=operation.row_id,
                operation=operation.operation_type,
                success=False,  # Skipped operations are not successful
                error_message=operation.error_message,
                metadata={"skipped": True},
            )

        # Check in our skip tracking
        if operation_id in self.skipped_operations:
            return OperationResult(
                row_id=operation.row_id,
                operation=operation.operation_type,
                success=False,  # Skipped operations are not successful
                error_message=self.skipped_operations[operation_id],
                metadata={"skipped": True},
            )

        return None

    def get_statistics(self) -> dict[str, Any]:
        """
        Get execution statistics.

        Returns:
            Dictionary of statistics
        """
        total = len(self.results)
        if total == 0:
            return {"total": 0}

        successful = sum(1 for r in self.results if r.success)
        failed = sum(1 for r in self.results if not r.success)

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total,
            "throttle_metrics": self.throttle.get_metrics(),
            "operation_breakdown": {
                "create": sum(1 for r in self.results if r.operation == OperationType.CREATE),
                "update": sum(1 for r in self.results if r.operation == OperationType.UPDATE),
                "delete": sum(1 for r in self.results if r.operation == OperationType.DELETE),
                "noop": sum(1 for r in self.results if r.operation == OperationType.NOOP),
            },
        }
