"""Execution Planner - Optimize execution order for operations.

Creates execution plans with batching and parallelization strategies.

Overview:
--------
The ExecutionPlanner takes a validated DependencyGraph and converts it into
an ExecutionPlan with batches of operations that can run in parallel.

Key Concepts:
------------
- Batch: A group of operations with no dependencies between them (can run parallel)
- Depth: The dependency depth in the graph (depth 0 = no dependencies)
- Plan: Ordered list of batches to execute sequentially

Batching Strategy:
-----------------
1. DependencyGraph.get_execution_batches() groups nodes by depth
2. Planner converts nodes to operations, optionally splitting large batches
3. Each batch's operations can execute concurrently within the batch
4. Batches execute sequentially (batch N must complete before batch N+1)

Example:
-------
Given CSV:
  Row 1: Create Block 10.0.0.0/8  (depth 0, no dependencies)
  Row 2: Create Network 10.1.0.0/24 in Block  (depth 1, depends on Row 1)
  Row 3: Create Network 10.2.0.0/24 in Block  (depth 1, depends on Row 1)
  Row 4: Create Address 10.1.0.5 in Network  (depth 2, depends on Row 2)

Resulting Plan:
  Batch 0: [Row 1]           - Must complete first
  Batch 1: [Row 2, Row 3]    - Can run in parallel
  Batch 2: [Row 4]           - Runs after batch 1

Duration Estimation:
-------------------
Durations are rough estimates for progress reporting. Actual times depend on
BAM server load, network latency, and operation complexity. The estimates
assume average conditions and are used for user feedback, not scheduling.

Relationship to DependencyGraph:
-------------------------------
- DependencyGraph handles DAG structure, phasing, and topological sort
- ExecutionPlanner handles batching, optimization, and execution metadata
- This separation allows the graph to be reused for dry-run analysis
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

from ..config import PolicyConfig
from ..dependency.graph import DependencyGraph, DependencyNode
from ..models.operations import Operation, OperationType

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionBatch:
    """
    A batch of operations that can execute in parallel.

    Attributes:
        batch_id: Unique identifier for this batch
        operations: List of operations in this batch
        depth: Dependency depth of this batch
        estimated_duration: Estimated execution time in seconds
    """

    batch_id: int
    operations: list[Operation] = field(default_factory=list)
    depth: int = 0
    estimated_duration: float = 0.0

    def __len__(self) -> int:
        """Number of operations in batch."""
        return len(self.operations)


@dataclass
class ExecutionPlan:
    """
    Complete execution plan with batches and metadata.

    Attributes:
        batches: List of execution batches in order
        total_operations: Total number of operations
        max_parallelism: Maximum number of parallel operations in any batch
        estimated_total_duration: Estimated total execution time
        metadata: Additional plan metadata
    """

    batches: list[ExecutionBatch] = field(default_factory=list)
    total_operations: int = 0
    max_parallelism: int = 0
    estimated_total_duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionPlanner:
    """
    Create optimized execution plans from dependency graphs.

    Features:
    - Batch creation for parallel execution
    - Operation grouping by type
    - Estimated duration calculation
    - Resource-aware scheduling
    """

    def __init__(self, policy: PolicyConfig) -> None:
        """
        Initialize Execution Planner.

        Args:
            policy: Policy configuration for planning
        """
        self.policy = policy

        # Estimated duration per operation type (seconds)
        self.operation_durations = {
            OperationType.CREATE: 0.5,
            OperationType.UPDATE: 0.3,
            OperationType.DELETE: 0.2,
            OperationType.NOOP: 0.01,
            OperationType.ORPHAN: 0.0,
        }

    def create_plan(
        self,
        dependency_graph: DependencyGraph,
        max_batch_size: int | None = None,
    ) -> ExecutionPlan:
        """
        Create an execution plan from a dependency graph.

        Args:
            dependency_graph: Validated dependency graph
            max_batch_size: Maximum operations per batch (None = unlimited)

        Returns:
            ExecutionPlan with batches ready for execution
        """
        logger.info("Creating execution plan", nodes=len(dependency_graph.nodes))

        # Validate graph first
        dependency_graph.validate()

        # Get execution batches from graph
        node_batches = dependency_graph.get_execution_batches()

        # Convert node batches to execution batches
        execution_batches: list[ExecutionBatch] = []

        for batch_idx, node_batch in enumerate(node_batches):
            # If max_batch_size is set, split large batches
            if max_batch_size and len(node_batch) > max_batch_size:
                sub_batches = self._split_batch(node_batch, max_batch_size)
                for _sub_idx, sub_batch_nodes in enumerate(sub_batches):
                    exec_batch = self._create_execution_batch(
                        batch_id=len(execution_batches),
                        nodes=sub_batch_nodes,
                    )
                    execution_batches.append(exec_batch)
            else:
                exec_batch = self._create_execution_batch(
                    batch_id=batch_idx,
                    nodes=node_batch,
                )
                execution_batches.append(exec_batch)

        # Calculate plan statistics
        total_ops = sum(len(batch) for batch in execution_batches)
        max_parallelism = max(len(batch) for batch in execution_batches) if execution_batches else 0
        estimated_duration = sum(batch.estimated_duration for batch in execution_batches)

        # Create execution plan
        plan = ExecutionPlan(
            batches=execution_batches,
            total_operations=total_ops,
            max_parallelism=max_parallelism,
            estimated_total_duration=estimated_duration,
            metadata={
                "batch_count": len(execution_batches),
                "creates": sum(
                    1
                    for batch in execution_batches
                    for op in batch.operations
                    if op.operation_type == OperationType.CREATE
                ),
                "updates": sum(
                    1
                    for batch in execution_batches
                    for op in batch.operations
                    if op.operation_type == OperationType.UPDATE
                ),
                "deletes": sum(
                    1
                    for batch in execution_batches
                    for op in batch.operations
                    if op.operation_type == OperationType.DELETE
                ),
                "noops": sum(
                    1
                    for batch in execution_batches
                    for op in batch.operations
                    if op.operation_type == OperationType.NOOP
                ),
            },
        )

        logger.info(
            "Execution plan created",
            total_operations=total_ops,
            batches=len(execution_batches),
            max_parallelism=max_parallelism,
            estimated_duration=f"{estimated_duration:.1f}s",
        )

        return plan

    def _create_execution_batch(
        self,
        batch_id: int,
        nodes: list[DependencyNode],
    ) -> ExecutionBatch:
        """
        Create an execution batch from dependency nodes.

        Args:
            batch_id: Unique batch identifier
            nodes: List of dependency nodes

        Returns:
            ExecutionBatch with operations
        """
        operations = [node.operation for node in nodes]
        depth = nodes[0].depth if nodes else 0

        # Estimate batch duration (max of concurrent operations)
        estimated_duration = (
            max(self.operation_durations.get(op.operation_type, 0.5) for op in operations)
            if operations
            else 0.0
        )

        return ExecutionBatch(
            batch_id=batch_id,
            operations=operations,
            depth=depth,
            estimated_duration=estimated_duration,
        )

    def _split_batch(
        self,
        nodes: list[DependencyNode],
        max_size: int,
    ) -> list[list[DependencyNode]]:
        """
        Split a large batch into smaller sub-batches.

        Args:
            nodes: List of nodes to split
            max_size: Maximum nodes per sub-batch

        Returns:
            List of sub-batches
        """
        sub_batches: list[list[DependencyNode]] = []

        for i in range(0, len(nodes), max_size):
            sub_batch = nodes[i : i + max_size]
            sub_batches.append(sub_batch)

        logger.debug(
            "Split large batch",
            original_size=len(nodes),
            sub_batches=len(sub_batches),
            max_size=max_size,
        )

        return sub_batches

    def optimize_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """
        Optimize an execution plan for better performance.

        Optimization Strategy:
        The goal is to minimize API calls and maximize cache efficiency while
        respecting dependency constraints.

        Key Optimizations:
        1. Group similar operations: All CREATEs of same type together
           - Improves API endpoint locality
           - Allows for potential future batching
           - Reduces context switching in handlers

        2. Sort by object type within operations:
           - Improves caching (e.g., all zone lookups together)
           - Reduces API endpoint thrashing
           - Makes error patterns clearer

        3. Stable sort by row_id:
           - Ensures deterministic execution order
           - Makes debugging and testing easier
           - Provides predictable behavior for users

        Trade-offs:
        - We don't interleave CREATEs and UPDATEs of same type to avoid conflicts
        - We don't reorder across dependency boundaries
        - We maintain original order within same operation types

        Args:
            plan: Execution plan to optimize

        Returns:
            Optimized execution plan with same logical dependencies
        """
        logger.info("Optimizing execution plan", batches=len(plan.batches))

        # Optimize each batch while preserving dependency order
        for batch in plan.batches:
            # Multi-key sort for optimal execution:
            # 1. Operation type (CREATE before UPDATE before DELETE)
            # 2. Object type (group all blocks, then networks, etc.)
            # 3. Row ID (stable ordering for reproducibility)
            batch.operations.sort(
                key=lambda op: (op.operation_type.value, op.object_type, str(op.row_id))
            )

        logger.debug("Plan optimization complete")

        return plan

    def get_plan_summary(self, plan: ExecutionPlan) -> dict[str, Any]:
        """
        Get a summary of the execution plan.

        Args:
            plan: Execution plan

        Returns:
            Dictionary with plan summary
        """
        return {
            "total_operations": plan.total_operations,
            "batch_count": len(plan.batches),
            "max_parallelism": plan.max_parallelism,
            "estimated_duration_seconds": plan.estimated_total_duration,
            "estimated_duration_minutes": plan.estimated_total_duration / 60,
            "operation_breakdown": plan.metadata,
            "batches": [
                {
                    "batch_id": batch.batch_id,
                    "operation_count": len(batch.operations),
                    "depth": batch.depth,
                    "estimated_duration": batch.estimated_duration,
                }
                for batch in plan.batches
            ],
        }
