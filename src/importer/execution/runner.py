"""
Import Runner - Encapsulates the execution logic for import sessions.

This module provides a reusable runner for executing import sessions from CSV files.
It handles:
1. Parsing and validation
2. Dependency path resolution
3. Graph construction
4. Execution planning
5. Execution
6. Reporting and Rollback generation
"""

import hashlib
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm

from ..bam.client import BAMClient
from ..config import ImporterConfig
from ..core.operation_factory import OperationFactory, PendingResources
from ..core.parser import CSVParser
from ..core.resolver import Resolver
from ..dependency.graph import DependencyGraph
from ..dependency.planner import DependencyPlanner
from ..execution.executor import OperationExecutor
from ..execution.planner import ExecutionPlanner
from ..models.operations import Operation, OperationType
from ..persistence.changelog import ChangeLog
from ..persistence.checkpoint import CheckpointManager
from ..rollback.generator import RollbackGenerator

logger = structlog.get_logger(__name__)


class ImportRunner:
    """
    Executes an import session from start to finish.
    """

    def __init__(self, config: ImporterConfig, console: Console) -> None:
        """
        Initialize ImportRunner.

        Args:
            config: Importer configuration
            console: Rich console for output
        """
        self.config = config
        self.console = console

    async def run_session(
        self,
        csv_file: Path,
        dry_run: bool = False,
        allow_dangerous_operations: bool = False,
        generate_rollback: bool = True,
        report: bool = False,
        session_id: str | None = None,
        resume: bool | None = None,
        no_cache: bool = False,
        show_deps: Path | None = None,
        show_plan: bool = False,
    ) -> int:
        """
        Run an import session.

        Args:
            csv_file: Path to CSV file
            dry_run: Whether to simulate execution
            allow_dangerous_operations: Whether to allow dangerous operations (e.g. deletions)
            generate_rollback: Whether to generate a rollback CSV
            report: Whether to generate an HTML report
            session_id: Optional existing session ID (e.g. for resume)
            no_cache: Whether to disable resolver caching
            show_deps: Optional path to output dependency graph as DOT file
            show_plan: Whether to show execution plan and exit without running

        Returns:
            int: Number of failed operations (0 = success)
        """
        start_time = datetime.now()

        # Initialize persistence first to check for resume
        changelog_db = Path(".changelogs/changelog.db")
        checkpoint_dir = Path(".checkpoints")
        checkpoint_dir.mkdir(exist_ok=True)
        checkpoint_db = checkpoint_dir / "checkpoint.db"

        checkpoint_mgr = CheckpointManager(checkpoint_db)
        changelog = ChangeLog(changelog_db)

        # Calculate input hash for resume detection
        input_hash = self._calculate_file_hash(csv_file)
        start_batch_id = 0

        # Track created resources loaded from checkpoint for resume
        initial_created_resources: dict[str, dict[str, int]] | None = None

        # Resume logic
        if not session_id and not dry_run:
            resumable_checkpoint = checkpoint_mgr.find_resumable_session(input_hash)

            if resumable_checkpoint:
                should_resume = False
                if resume is True:
                    should_resume = True
                elif resume is None:
                    # Prompt user
                    self.console.print(
                        f"\n[bold yellow]Found interrupted session[/bold yellow] [cyan]{resumable_checkpoint.session_id}[/cyan] "
                        f"for this file (Batch {resumable_checkpoint.batch_id}, {resumable_checkpoint.completed_operations} ops completed)."
                    )
                    should_resume = Confirm.ask("Resume this session?", console=self.console)

                if should_resume:
                    session_id = resumable_checkpoint.session_id
                    start_batch_id = resumable_checkpoint.batch_id
                    # Load created resources from previous batches for deferred resolution
                    initial_created_resources = checkpoint_mgr.load_created_resources(session_id)
                    self.console.print(
                        f"[green]Resuming session {session_id} from batch {start_batch_id}[/green]"
                    )

        # New session if not resuming
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:8]}"

        self.console.print(f"Session ID: [cyan]{session_id}[/cyan]")
        self.console.print(f"Mode: [yellow]{'DRY RUN' if dry_run else 'LIVE'}[/yellow]")

        # Metrics
        successful = 0
        failed = 0
        skipped = 0
        results = []

        # Persistence initialized above

        # Progress bar configuration
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
        )

        client = BAMClient(self.config.bam)

        with progress:
            try:
                # Step 1: Connect to BAM
                task = progress.add_task("[cyan]Connecting to BAM...", total=None)
                if not dry_run:
                    await client.authenticate()
                progress.update(task, completed=True, description="[green]DONE: Connected to BAM")

                # Step 2: Parse CSV
                task = progress.add_task("[cyan]Parsing CSV...", total=None)
                parser = CSVParser(csv_file)
                rows = parser.parse()
                progress.update(
                    task, completed=True, description=f"[green]DONE: Parsed {len(rows)} rows"
                )

                # Handle empty CSV gracefully
                if not rows:
                    logger.warning(
                        "No operations to execute - CSV is empty or contains only comments/headers",
                        csv_path=str(csv_file),
                    )
                    progress.console.print(
                        "[yellow]Warning: CSV is empty or contains only comments/headers. No operations to execute.[/yellow]"
                    )
                    return {
                        "success": True,
                        "total_operations": 0,
                        "successful_operations": 0,
                        "failed_operations": 0,
                        "skipped_operations": 0,
                        "message": "No operations to execute (empty CSV)",
                    }

                # Step 3: Resolve paths and create operations
                task = progress.add_task("[cyan]Resolving paths...", total=len(rows))
                resolver = Resolver(
                    client, Path(".cache/resolver"), self.config.cache, no_cache=no_cache
                )
                operations = []

                # Pre-scan for pending resources
                pending = PendingResources.from_rows(rows)
                factory = OperationFactory(client, resolver, pending)

                for row in rows:
                    try:
                        operation = await factory.create_from_row(row)
                        operations.append(operation)
                    except Exception as e:
                        tb_str = traceback.format_exc()
                        logger.warning(
                            f"Failed to create operation for row {row.row_id}: {e}",
                            traceback=tb_str,
                        )
                        # Create failed placeholder
                        operations.append(
                            Operation(
                                row_id=row.row_id,
                                operation_type=(
                                    OperationType.CREATE
                                    if row.action == "create"
                                    else (
                                        OperationType.UPDATE
                                        if row.action == "update"
                                        else OperationType.DELETE
                                    )
                                ),
                                object_type=row.object_type,
                                resource_id=getattr(row, "bam_id", None),
                                payload={"error": str(e), "traceback": tb_str},
                                csv_row=row,
                            )
                        )
                    progress.update(task, advance=1)
                progress.update(
                    task, description=f"[green]DONE: Resolved {len(operations)} operations"
                )

                # Step 4: Build dependency graph
                task = progress.add_task("[cyan]Building dependency graph...", total=None)
                graph = DependencyGraph()
                for op in operations:
                    graph.add_operation(op)

                # Wire dependencies
                dependency_planner = DependencyPlanner()
                dependency_planner.build_graph(graph, operations)

                # Apply barriers and validation
                graph._apply_phasing()
                graph.validate()
                graph._calculate_depths()

                progress.update(
                    task, completed=True, description="[green]DONE: Dependency graph built"
                )

                # FEAT-004: Output dependency graph as DOT file if requested
                if show_deps:
                    dot_content = graph.to_dot()
                    with open(show_deps, "w", encoding="utf-8") as f:
                        f.write(dot_content)
                    self.console.print(f"[cyan]Dependency graph written to: {show_deps}[/cyan]")
                    self.console.print(
                        f"[dim]Visualize with: dot -Tpng {show_deps} -o graph.png[/dim]"
                    )

                # Step 5: Execution plan
                task = progress.add_task("[cyan]Creating execution plan...", total=None)
                planner = ExecutionPlanner(self.config.policy)
                plan = planner.create_plan(graph)
                progress.update(
                    task, completed=True, description="[green]DONE: Execution plan created"
                )

                # DX-003: Show execution plan and exit if --show-plan flag is set
                if show_plan:
                    self._display_execution_plan(plan, graph, operations)
                    await client.close()
                    await client.close()
                    return 0

                # Step 6: Execute
                task = progress.add_task(
                    "[cyan]Executing operations...", total=plan.total_operations
                )
                executor = OperationExecutor(
                    bam_client=client,
                    policy=self.config.policy,
                    allow_dangerous_operations=allow_dangerous_operations,
                    dependency_graph=graph,
                    checkpoint_manager=checkpoint_mgr,
                    session_id=session_id,
                    initial_created_resources=initial_created_resources,
                )

                # Hook up changelog recording
                if not dry_run:
                    # We need a way to capture results and write to changelog/checkpoint
                    # The executor returns results, but we might want intermediate saving
                    pass

                results = await executor.execute_plan(
                    plan,
                    dry_run=dry_run,
                    start_batch_id=start_batch_id,
                    input_hash=input_hash,
                )

                # Map operations for quick lookup during results processing
                ops_map = {op.row_id: op for op in operations}

                for result in results:
                    # PERF-001: Cache Coherency - Invalidate resolver cache for ALL mutations
                    #
                    # WHY INVALIDATE ON ALL OPERATIONS:
                    # The resolver caches path→ID mappings (e.g., "Default/10.0.0.0/8" → 123).
                    # When we CREATE/UPDATE/DELETE a resource, the cache may contain stale data:
                    #   - CREATE: New resource exists but cache thinks it doesn't
                    #   - UPDATE: Resource properties changed (name, CIDR normalization)
                    #   - DELETE: Resource gone but cache still returns ID
                    #
                    # Failing to invalidate causes:
                    #   - Deferred resolution failures (can't find newly created parents)
                    #   - Duplicate creation attempts (cache miss on existing resource)
                    #   - Invalid ID references (deleted resource still cached)
                    #
                    # PERFORMANCE TRADE-OFF:
                    # Invalidation on every mutation is conservative but safe. Alternative
                    # (selective invalidation) risks subtle cache bugs that are hard to debug.
                    if result.success and result.operation in (
                        OperationType.CREATE,
                        OperationType.UPDATE,
                        OperationType.DELETE,
                    ):
                        op = ops_map.get(result.row_id)
                        if op and op.payload.get("resource_path"):
                            path = op.payload["resource_path"]

                            # Invalidate the resource's own cache entry
                            await resolver.invalidate(path, op.object_type)

                            # WHY INVALIDATE PARENT: Hierarchical resources (blocks, networks, zones)
                            # affect parent listings. If we create/delete a network, the parent block's
                            # "list networks" cache is now stale.
                            #
                            # EDGE CASE: CIDR Paths vs Hierarchical Paths
                            #
                            # CIDR Path (IPv4/IPv6):
                            #   Format: "Config/IP/Prefix"  e.g., "Default/10.0.0.0/8"
                            #   Parent: Just the config name ("Default")
                            #   WHY: The "/8" is part of CIDR notation, not a path separator
                            #
                            # Hierarchical Path (Zones, UDLs):
                            #   Format: "Parent/Child"  e.g., "RootZone/SubZone"
                            #   Parent: Everything before last "/" ("RootZone")
                            #
                            # DETECTION STRATEGY:
                            #   - If last component is a digit, assume CIDR notation
                            #   - Else, assume hierarchical path and split on "/"
                            #
                            # LIMITATION:
                            #   This heuristic could fail for zones named "123" but that's
                            #   extremely rare and violates DNS naming conventions.
                            if "/" in path:
                                parts = path.split("/")

                                # Check if this looks like a CIDR (ends with digit)
                                if len(parts) >= 3 and parts[-1].isdigit():
                                    # CIDR path like "Default/10.0.0.0/8"
                                    # Parent is everything before the IP/prefix
                                    parent_path = parts[0]  # Just the config name
                                elif len(parts) >= 2:
                                    # Non-CIDR hierarchical path like "view/zone/subzone"
                                    # Parent is everything except last component
                                    parent_path = "/".join(parts[:-1])
                                else:
                                    parent_path = None

                                if parent_path:
                                    # Invalidate parent's cache (affects parent's child listings)
                                    await resolver.invalidate(parent_path, op.object_type)

                    if result.success:

                        successful += 1
                        # Record in changelog
                        if not dry_run:
                            try:
                                op = ops_map.get(result.row_id)
                                changelog.record_operation(
                                    session_id=session_id,
                                    row_id=str(result.row_id),
                                    operation_type=result.operation.value,
                                    object_type=op.object_type if op else "unknown",
                                    resource_id=result.resource_id,
                                    before_state=(
                                        str(result.before_state) if result.before_state else None
                                    ),
                                    after_state=(
                                        str(result.after_state) if result.after_state else None
                                    ),
                                    success=True,
                                )
                            except Exception as e:
                                logger.error("Failed to write to changelog", error=str(e))

                    elif result.metadata.get("skipped"):
                        skipped += 1
                    else:
                        failed += 1
                        if not dry_run:
                            try:
                                op = ops_map.get(result.row_id)
                                changelog.record_operation(
                                    session_id=session_id,
                                    row_id=str(result.row_id),
                                    operation_type=result.operation.value,
                                    object_type=op.object_type if op else "unknown",
                                    resource_id=None,
                                    before_state=None,
                                    after_state=None,
                                    success=False,
                                    error_message=result.error_message,
                                )
                            except Exception:
                                pass
                    progress.update(task, advance=1)

                progress.update(
                    task, description=f"[green]DONE: Executed {len(results)} operations"
                )

            finally:
                if not dry_run:
                    await client.close()

                    # update session status
                    if failed > 0:
                        checkpoint_mgr.mark_session_failed(session_id, "Completed with errors")
                    else:
                        checkpoint_mgr.mark_session_completed(session_id)

                await client.close()
                checkpoint_mgr.close()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Summary
        if failed == 0:
            self.console.print(
                "\n[bold green]SUCCESS: Import completed successfully![/bold green]\n"
            )
        else:
            self.console.print(
                "\n[bold yellow]WARNING: Import completed with errors[/bold yellow]\n"
            )

        self.console.print(f"Duration: {duration:.2f} seconds")
        self.console.print(f"Session ID: [cyan]{session_id}[/cyan]")
        self.console.print(
            f"Operations: [green]{successful} successful[/green], [red]{failed} failed[/red], [yellow]{skipped} skipped[/yellow]"
        )

        # Show failed/skipped (Simplified)
        if failed > 0:
            self.console.print("\n[red]Failed operations:[/red]")
            count = 0
            for result in results:
                if not result.success and not result.metadata.get("skipped"):
                    self.console.print(f"  - Row {result.row_id}: {result.error_message}")
                    count += 1
                    if count >= 10:
                        self.console.print(f"  ... and {failed - 10} more")
                        break

        # Rollback generation
        if generate_rollback and not dry_run and successful > 0:
            try:
                generator = RollbackGenerator(changelog)
                rollback_dir = Path("rollbacks")
                rollback_dir.mkdir(exist_ok=True)
                rollback_path = rollback_dir / f"{session_id}_rollback.csv"
                generator.generate_rollback_csv(session_id, rollback_path)
                self.console.print(f"\nRollback CSV: [cyan]{rollback_path}[/cyan]")
                self.console.print(
                    f"To rollback: [yellow]bluecat-import rollback {rollback_path}[/yellow]"
                )
            except Exception as e:
                logger.error("Failed to generate rollback", error=str(e))
                self.console.print(f"[red]Failed to generate rollback CSV: {e}[/red]")

        # Dry Run Report
        if dry_run and report:
            self._generate_dry_run_report(results, session_id, duration, ops_map)

        return failed

    def _generate_dry_run_report(
        self,
        results: list[Any],
        session_id: str,
        duration: float,
        ops_map: dict[str | int, Operation],
    ) -> None:
        """
        Generate a detailed report for dry run.

        Args:
            results: List of OperationResult objects
            session_id: Session identifier
            duration: Execution duration in seconds
        """
        report_path = Path(f"dry_run_report_{session_id}.md")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Dry Run Report: {session_id}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Duration:** {duration:.2f}s\n\n")

            # Summary stats
            successful = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success and not r.metadata.get("skipped"))
            skipped = sum(1 for r in results if r.metadata.get("skipped"))

            f.write("## Summary\n")
            f.write(f"- **Proposed Changes:** {successful}\n")
            f.write(f"- **Potential Errors:** {failed}\n")
            f.write(f"- **Skipped:** {skipped}\n\n")

            # Detailed Changes
            f.write("## Proposed Changes\n")
            if successful == 0:
                f.write("*No changes proposed.*\n")
            else:
                f.write("| Row | Action | Type | Details |\n")
                f.write("|---|---|---|---|\n")
                for r in results:
                    if r.success:
                        op = ops_map.get(r.row_id)
                        if not op:
                            continue
                        op_type = r.operation.value.upper()
                        obj_type = op.object_type
                        details = self._format_operation_details(op)
                        f.write(f"| {r.row_id} | {op_type} | {obj_type} | {details} |\n")

            f.write("\n")

            # Errors
            if failed > 0:
                f.write("## Potential Errors\n")
                f.write("| Row | Error |\n")
                f.write("|---|---|\n")
                for r in results:
                    if not r.success and not r.metadata.get("skipped"):
                        # Escape pipes in error message
                        error_msg = str(r.error_message).replace("|", "\\|")
                        f.write(f"| {r.row_id} | {error_msg} |\n")

        self.console.print(
            f"\n[bold cyan]Detailed dry-run report written to: {report_path}[/bold cyan]"
        )

    def _format_operation_details(self, operation: Operation) -> str:
        """Format operation details for report."""
        details = []
        row = operation.csv_row

        # Add key identifying info based on type
        if hasattr(row, "name") and row.name:
            details.append(f"Name: {row.name}")
        if hasattr(row, "cidr") and row.cidr:
            details.append(f"CIDR: {row.cidr}")
        if hasattr(row, "ip_address") and row.ip_address:
            details.append(f"IP: {row.ip_address}")
        if hasattr(row, "zone_name") and row.zone_name:
            details.append(f"Zone: {row.zone_name}")

        # Add config/view context
        if hasattr(row, "config") and row.config:
            details.append(f"(Config: {row.config})")

        return ", ".join(details).replace("|", "\\|")

    def _display_execution_plan(self, plan: Any, graph: Any, operations: list[Operation]) -> None:
        """
        DX-003: Display execution plan in a human-readable format.

        Shows operations grouped by phase with dependencies.
        """
        from rich.tree import Tree

        self.console.print("\n")
        self.console.print("[bold cyan]═══ Execution Plan Preview ═══[/bold cyan]\n")
        self.console.print(f"[dim]Total operations: {plan.total_operations}[/dim]\n")

        # Group operations by phase
        phases: dict[int, list[Operation]] = {}
        for op in operations:
            depth = graph.depths.get(op.row_id, 0)
            if depth not in phases:
                phases[depth] = []
            phases[depth].append(op)

        # Create tree visualization
        tree = Tree("[bold]Execution Order[/bold]")

        for phase_num in sorted(phases.keys()):
            phase_ops = phases[phase_num]
            phase_node = tree.add(
                f"[cyan]Phase {phase_num + 1}[/cyan] ({len(phase_ops)} operations)"
            )

            for op in phase_ops[:15]:  # Limit to 15 per phase for readability
                # Format operation description
                op_type = op.operation_type.name
                obj_type = op.object_type

                # Get identifying info
                row = op.csv_row
                name = getattr(row, "name", None) or getattr(row, "zone_name", None) or ""
                cidr = getattr(row, "cidr", None) or ""
                identifier = name or cidr or f"row-{op.row_id}"

                # Color based on operation type
                if op_type == "CREATE":
                    color = "green"
                elif op_type == "UPDATE":
                    color = "yellow"
                elif op_type == "DELETE":
                    color = "red"
                else:
                    color = "dim"

                op_desc = f"[{color}]{op_type}[/{color}] {obj_type}: {identifier}"

                # Show dependencies if any
                deps = graph.get_dependencies(op.row_id)
                if deps:
                    dep_names = [f"row-{d}" for d in list(deps)[:3]]
                    if len(deps) > 3:
                        dep_names.append(f"...+{len(deps)-3} more")
                    op_desc += f" [dim](depends on: {', '.join(dep_names)})[/dim]"

                phase_node.add(op_desc)

            if len(phase_ops) > 15:
                phase_node.add(f"[dim]... and {len(phase_ops) - 15} more operations[/dim]")

        self.console.print(tree)
        self.console.print("\n[bold green]✓ Plan preview complete. No changes made.[/bold green]")
        self.console.print("[dim]Remove --show-plan to execute the import.[/dim]\n")

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file content."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
