"""Command-line interface for the BlueCat CSV Importer."""

import os
import uuid
from datetime import datetime
from pathlib import Path

import structlog
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import ImporterConfig
from .core.parser import CSVParser
from .core.sanitizer import CSVSanitizer

app = typer.Typer(
    name="bluecat-import",
    help="BlueCat CSV Importer - Production-grade bulk import tool",
    add_completion=False,
)

console = Console()
logger = structlog.get_logger(__name__)


@app.command()
def fix(
    csv_file: Path = typer.Argument(..., help="CSV file to clean", exists=True),
    output_file: Path | None = typer.Option(
        None, "--output", "-o", help="Output file (default: overwrite)"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Automatically accept changes"),
) -> None:
    """
    Sanitize CSV file by stripping whitespace and standardizing format.

    Uses smart detection to clean headers and values while preserving comments.
    Displays a diff of changes before applying.

    Examples:
        bluecat-import fix data/dirty.csv
        bluecat-import fix data/dirty.csv -o data/clean.csv
        bluecat-import fix data/dirty.csv --yes
    """
    console.print(f"\n[bold blue]Sanitizing CSV:[/bold blue] {csv_file}\n")

    try:
        sanitizer = CSVSanitizer(csv_file)
        result = sanitizer.sanitize()

        sanitizer.print_diff(result, console)

        if not result.has_changes:
            return

        if output_file:
            target_path = output_file
        else:
            target_path = csv_file

        if not yes:
            if not typer.confirm(f"Write cleaned content to {target_path}?"):
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit()

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(result.cleaned_content)

        console.print(f"[green]Successfully wrote cleaned CSV to {target_path}[/green]")

    except Exception as e:
        console.print(f"\n[red]ERROR: Fix failed:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command()
def validate(
    csv_file: Path = typer.Argument(..., help="CSV file to validate", exists=True),
    strict: bool = typer.Option(False, "--strict", help="Fail on warnings"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Configuration file"),
    auto_fix: bool = typer.Option(
        True, "--auto-fix", help="Check for and fix CSV formatting issues"
    ),
    bulk: bool = typer.Option(
        False, "--bulk", help="Force enable bulk validation (Auto-enabled for >50 rows)"
    ),
    no_bulk: bool = typer.Option(False, "--no-bulk", help="Force disable bulk validation"),
) -> None:
    """
    Validate CSV file without executing.

    Checks:
    - Schema version compatibility
    - Syntax (CIDR, MAC, DNS)
    - Field validation
    - Pydantic model validation

    Examples:
        bluecat-import validate samples/simple_import.csv
        bluecat-import validate samples/complex_import.csv --strict
    """
    console.print(f"\n[bold blue]Validating CSV:[/bold blue] {csv_file}\n")

    try:
        # Check for formatting issues first
        parser_csv_path = csv_file
        if auto_fix:
            sanitizer = CSVSanitizer(csv_file)
            result = sanitizer.sanitize()
            if result.has_changes:
                sanitizer.print_diff(result, console)
                if typer.confirm(
                    "CSV contains formatting issues. Use cleaned data for validation?"
                ):
                    if typer.confirm(f"Save cleaned content to {csv_file}?"):
                        with open(csv_file, "w", encoding="utf-8") as f:
                            f.write(result.cleaned_content)
                        console.print("[green]Saved cleaned CSV.[/green]")
                    else:
                        # Use temp file for validation
                        import os
                        import tempfile

                        fd, temp_path = tempfile.mkstemp(suffix=".csv", text=True)
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(result.cleaned_content)
                        parser_csv_path = Path(temp_path)
                        console.print(
                            f"[yellow]Using temporary file for validation: {temp_path}[/yellow]"
                        )
                else:
                    console.print(
                        "[yellow]Proceeding with original file (internal parser will clean whitespace automatically).[/yellow]"
                    )

        try:
            # Parse CSV
            parser = CSVParser(parser_csv_path)
            rows = parser.parse(strict=strict)
        finally:
            # Cleanup temp file if used
            if parser_csv_path != csv_file and parser_csv_path.exists():
                parser_csv_path.unlink()

        # Display results
        if parser.errors:
            console.print(
                f"[yellow]WARNING: Found {len(parser.errors)} validation errors:[/yellow]\n"
            )
            console.print(parser.get_error_summary())

            if strict:
                console.print("\n[red]ERROR: Validation failed (strict mode)[/red]")
                raise typer.Exit(code=1)
            else:
                console.print(
                    f"\n[yellow]WARNING: Validation completed with {len(parser.errors)} errors"
                    " (non-strict mode)[/yellow]"
                )
        else:
            console.print("[green]PASS: Validation successful![/green]")
            console.print(f"  Total rows: {len(rows)}")

            # Show summary by object type using Counter
            from collections import Counter

            type_counts = Counter(row.object_type for row in rows)

            table = Table(title="Summary by Object Type")
            table.add_column("Object Type", style="cyan")
            table.add_column("Count", justify="right", style="green")

            for obj_type, count in sorted(type_counts.items()):
                table.add_row(obj_type, str(count))

            console.print("\n", table)

            # Bulk Validation Logic
            run_bulk = None
            if bulk:
                run_bulk = True
            elif no_bulk:
                run_bulk = False

            if run_bulk is None:
                # Smart default: Auto-enable if significant row count
                run_bulk = len(rows) > 50
                if run_bulk:
                    console.print(
                        "\n[cyan]Auto-enabling Bulk Pre-flight Validation (>50 rows detected)[/cyan]"
                    )

            if run_bulk:
                console.print(
                    "\n[bold blue]Phase 2: Bulk Pre-flight Validation (Online)[/bold blue]"
                )
                import asyncio

                from .bam.client import BAMClient
                from .config import load_config
                from .validation.validator import BulkValidator

                async def run_online_validation():
                    # Load config (env vars or file)
                    try:
                        cfg = load_config(config_file)
                    except Exception as e:
                        console.print(
                            f"[yellow]Skipping bulk validation: Could not load config ({e})[/yellow]"
                        )
                        return

                    if not cfg.bam:
                        console.print(
                            "[yellow]Skipping bulk validation: No BAM configuration found.[/yellow]"
                        )
                        console.print("(Set BAM_URL/USER/PASS env vars or provide --config)")
                        return

                    console.print("[cyan]Connecting to BAM...[/cyan]")
                    try:
                        async with BAMClient(config=cfg.bam) as client:
                            console.print("[green]Connected. Running checks...[/green]")
                            validator = BulkValidator(client)
                            report = await validator.validate(rows)

                            if report.warnings:
                                console.print(
                                    f"\n[yellow]Bulk Warnings ({len(report.warnings)}):[/yellow]"
                                )
                                for w in report.warnings:
                                    console.print(f"  - Row {w.row_id}: {w.message}")

                            if report.errors:
                                console.print(f"\n[red]Bulk Errors ({len(report.errors)}):[/red]")
                                for e in report.errors:
                                    console.print(f"  - Row {e.row_id} ({e.field}): {e.message}")

                                console.print(
                                    f"\n[bold red]Bulk Validation Failed with {len(report.errors)} errors.[/bold red]"
                                )
                                raise typer.Exit(code=1)
                            else:
                                console.print("[green]Bulk Validation Passed![/green]")
                    except Exception as e:
                        console.print(f"[red]Bulk validation error: {e}[/red]")
                        if strict:
                            raise typer.Exit(code=1) from e

                asyncio.run(run_online_validation())

    except Exception as e:
        console.print(f"\n[red]ERROR: Validation failed:[/red] {e}")
        raise typer.Exit(code=1) from e


@app.command()
def apply(
    csv_file: Path = typer.Argument(..., help="CSV file to import", exists=True),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without executing"),
    generate_rollback: bool = typer.Option(True, "--rollback", help="Generate rollback CSV"),
    config_file: Path | None = typer.Option(None, "--config", "-c", help="Policy config file"),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Resume from checkpoint",
    ),
    no_resume: bool = typer.Option(
        False,
        "--no-resume",
        help="Do not resume from checkpoint",
    ),
    report: bool = typer.Option(True, "--report", help="Generate HTML/JSON report"),
    allow_dangerous_operations: bool = typer.Option(
        False,
        "--allow-dangerous-operations",
        help="DANGEROUS: Allow deletion of configurations and views (protects critical infrastructure)",
    ),
    auto_fix: bool = typer.Option(
        True, "--auto-fix", help="Check for and fix CSV formatting issues"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Disable resolver caching (slower but avoids stale data)"
    ),
    show_deps: Path | None = typer.Option(
        None, "--show-deps", help="Output dependency graph as DOT file (for Graphviz)"
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log verbosity: TRACE, DEBUG, VERBOSE, INFO, WARNING, ERROR",
    ),
    log_filter: str | None = typer.Option(
        None,
        "--log-filter",
        help="Filter logs by component (comma-separated, e.g., 'resolver,executor')",
    ),
    show_plan: bool = typer.Option(
        False,
        "--show-plan",
        help="Preview execution plan and exit without running (DX-003)",
    ),
) -> None:
    """
    Apply changes from CSV to BlueCat Address Manager.

    Full Phase 2 & 3 implementation with:
    - State loading and diff engine
    - Dependency graph with cycle detection
    - Adaptive throttling
    - Checkpointing for resume
    - Rollback CSV generation
    - Rich progress bars
    - JSON/HTML reports
    - Smart CSV Sanitizer

    Examples:
        bluecat-import apply changes.csv --dry-run
        bluecat-import apply changes.csv --config prod.yaml
        bluecat-import apply changes.csv --no-rollback
    """
    import asyncio

    from .observability import configure_logging

    # Metrics Integration
    from .observability.metrics import get_global_collector

    get_global_collector()

    # Simple timer for total duration
    import time

    time.time()

    # DX-002: Configure logging with custom levels and optional filtering
    configure_logging(
        level=log_level or os.environ.get("LOG_LEVEL", "INFO"),
        json_logs=False,
        log_filter=log_filter,
    )

    session_id = str(uuid.uuid4())[:8]

    console.print(
        Panel.fit(
            f"[bold blue]BlueCat CSV Import[/bold blue]\n\n"
            f"Session ID: [cyan]{session_id}[/cyan]\n"
            f"CSV File: {csv_file}\n"
            f"Mode: [yellow]{'DRY RUN' if dry_run else 'EXECUTE'}[/yellow]\n"
            f"Rollback: [green]{'Enabled' if generate_rollback else 'Disabled'}[/green]\n"
            f"Report: [green]{'Enabled' if report else 'Disabled'}[/green]",
            border_style="blue",
        )
    )

    if dry_run:
        console.print("[yellow]WARNING: DRY RUN MODE - No changes will be made to BAM[/yellow]\n")

    # Check for formatting issues first
    if auto_fix:
        try:
            sanitizer = CSVSanitizer(csv_file)
            result = sanitizer.sanitize()
            if result.has_changes:
                sanitizer.print_diff(result, console)
                console.print(
                    "\n[bold yellow]The CSV file contains formatting issues (whitespace, etc).[/bold yellow]"
                )
                console.print("The importer can fix these automatically before proceeding.")

                if typer.confirm(f"Apply fixes to {csv_file} and continue?"):
                    with open(csv_file, "w", encoding="utf-8") as f:
                        f.write(result.cleaned_content)
                    console.print(
                        f"[green]Saved cleaned CSV to {csv_file}. Proceeding...[/green]\n"
                    )
                else:
                    if not typer.confirm(
                        "Continue with original file? (Internal parser will attempt to handle whitespace)"
                    ):
                        raise typer.Exit()
                    console.print("[yellow]Proceeding with original file.[/yellow]\n")
        except Exception as e:
            logger.warning(f"Sanitization check failed: {e}")

    # Load configuration
    if config_file and config_file.exists():
        config = ImporterConfig.from_file(config_file)
        console.print(f"[green]OK:[/green] Configuration loaded from {config_file}\n")
    else:
        config = ImporterConfig.from_env()
        console.print("[green]OK:[/green] Using default configuration\n")

    async def run_apply() -> None:
        """Async implementation of apply command."""
        from .execution.runner import ImportRunner

        runner = ImportRunner(config, console)

        # Allow dangerous operations if flag set
        # For rollback, we might want to default to True or prompt?
        # The user passed flags to apply, so we respect them.

        # Handle resume logic
        should_resume = None
        if resume:
            should_resume = True
        elif no_resume:
            should_resume = False

        exit_code = await runner.run_session(
            csv_file=csv_file,
            dry_run=dry_run,
            allow_dangerous_operations=allow_dangerous_operations,
            generate_rollback=generate_rollback,
            report=report,
            resume=should_resume,
            no_cache=no_cache,
            show_deps=show_deps,
            show_plan=show_plan,
        )

        if exit_code != 0:
            raise typer.Exit(code=1)

    # Run async apply
    try:
        asyncio.run(run_apply())
        # Check if any failures occurred during the run (requires run_apply to return or set state)
        # Since run_apply is a local function, we can't easily access 'failed' count here.
        # Ideally, run_apply should return specific status.
        # But wait, run_apply *prints* the summary.
        # We need a different approach or modify run_apply to raise Exit if failed > 0.
    except typer.Exit:
        raise  # Re-raise Typer exits
    except Exception as e:
        console.print(f"\n[bold red]ERROR:[/bold red] {str(e)}")
        raise typer.Exit(code=1) from e


# Note: The _create_operation_from_row function has been moved to
# src/importer/core/operation_factory.py as part of the OperationFactory class.
# This improves separation of concerns by keeping CLI code focused on user interaction.


@app.command()
def rollback(
    csv_file: Path = typer.Argument(..., help="Rollback CSV file", exists=True),
    dry_run: bool = typer.Option(False, "--dry-run", is_flag=True, help="Simulate rollback"),
    no_verify: bool = typer.Option(
        False, "--no-verify", is_flag=True, help="Skip SSL verification"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", is_flag=True, help="Skip confirmation"),
) -> None:
    """
    Rollback a previous import using a rollback CSV.

    This command executes the inverse operations generated during an import session.
    It functions similarly to 'apply' but is optimized for deletions and restorations.

    Safety:
    - Rollbacks often involve DELETING resources.
    - Dangerous operations are ENABLED by default for rollback but prompt for confirmation.
    """
    import asyncio

    console.print("\n[bold red]Rollback Import[/bold red]\n")
    console.print(f"Rollback CSV: {csv_file}")

    if not yes and not dry_run:
        if not typer.confirm("WARNING: This will DELETE resources to restore state. Are you sure?"):
            raise typer.Abort()

    async def run_rollback() -> None:
        from .execution.runner import ImportRunner

        config = ImporterConfig.from_env()
        # Override SSL verify if requested
        if no_verify and config.bam:
            config.bam.verify_ssl = False

        runner = ImportRunner(config, console)

        # Rollback inherently entails dangerous operations (deletions)
        # We assume the user wants to proceed if they ran 'rollback'
        exit_code = await runner.run_session(
            csv_file=csv_file,
            dry_run=dry_run,
            allow_dangerous_operations=True,  # Explicitly allow dangerous ops for rollback
            generate_rollback=False,  # Don't generate a rollback for a rollback? Or maybe double rollback? usually no.
            report=False,
            session_id=f"rollback_{uuid.uuid4().hex[:8]}",
        )

        if exit_code != 0:
            raise typer.Exit(code=1)

    asyncio.run(run_rollback())


@app.command()
def export(
    output_file: Path = typer.Argument(..., help="Output CSV file path"),
    # Scope options
    network: str | None = typer.Option(None, "--network", help="Network CIDR or ID to export"),
    block: int | None = typer.Option(None, "--block", help="Block ID to export"),
    zone: str | None = typer.Option(None, "--zone", help="Zone FQDN or ID to export"),
    # Configuration options
    config_id: int | None = typer.Option(
        None, "--config-id", help="Configuration ID (required for CIDR)"
    ),
    config_name: str | None = typer.Option(
        None, "--config-name", help="Configuration name (required for CIDR)"
    ),
    view_id: int | None = typer.Option(None, "--view-id", help="View ID (required for FQDN)"),
    # Export options
    include_children: bool = typer.Option(True, "--children", help="Include child resources"),
    include_addresses: bool = typer.Option(
        True, "--addresses", help="Include IP addresses (for networks)"
    ),
    include_records: bool = typer.Option(True, "--records", help="Include DNS records (for zones)"),
    action: str = typer.Option("update", "--action", help="Default action (create or update)"),
    # Config file
    config_file: Path | None = typer.Option(None, "--config", "-c", help="BAM config file"),
    # Security options
    allow_formulas: bool = typer.Option(
        False, "--allow-formulas", help="Allow CSV formulas (security risk)"
    ),
    # Advanced Filtering
    filter_str: str | None = typer.Option(
        None, "--filter", help="BAM filter string (e.g. \"name:'Test*'\")"
    ),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated list of fields to fetch"
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Maximum number of results to export per query"
    ),
    order_by: str | None = typer.Option(None, "--order-by", help='Sort order (e.g. "name desc")'),
) -> None:
    """
    Export BlueCat resources to CSV format.

    Exports scoped resources from BAM to a CSV file for editing and re-import.
    You must specify ONE of: --network, --block, or --zone.

    Examples:
        # Export a specific network and its children
        bluecat-import export network.csv --network 10.1.0.0/16 --config-name Default

        # Export a block and all child networks/addresses
        bluecat-import export block.csv --block 12345

        # Export a DNS zone and all records
        bluecat-import export zone.csv --zone example.com --view-id 100

        # Export without children or addresses (just the network itself)
        bluecat-import export single.csv --network 192.168.1.0/24 --config-id 100 --no-children --no-addresses
    """
    import asyncio

    from .bam.client import BAMClient
    from .config import load_config
    from .core.exporter import BlueCatExporter

    # Validate that exactly one scope is specified
    scopes = [network, block, zone]
    if sum(s is not None for s in scopes) != 1:
        console.print(
            "[bold red]ERROR:[/bold red] You must specify exactly ONE of: --network, --block, or --zone"
        )
        raise typer.Exit(code=1)

    # Display configuration
    scope_type = "Network" if network else "Block" if block else "Zone"
    scope_value = network or block or zone

    console.print(
        Panel.fit(
            f"[bold blue]Export BlueCat Resources to CSV[/bold blue]\n\n"
            f"Scope: [cyan]{scope_type}[/cyan] = [yellow]{scope_value}[/yellow]\n"
            f"Output: [cyan]{output_file}[/cyan]\n"
            f"Include Children: {include_children}\n"
            f"Action: {action}",
            border_style="blue",
        )
    )

    async def run_export():
        # Load configuration
        console.print("\n[cyan]Loading configuration...[/cyan]")
        config = load_config(config_file)

        # Validate BAM configuration
        if not config.bam:
            console.print("\n[bold red]ERROR:[/bold red] BAM configuration required")
            console.print(
                "Set BAM_URL, BAM_USERNAME, BAM_PASSWORD environment variables or use --config"
            )
            raise typer.Exit(code=1)

        # Create BAM client
        console.print("[cyan]Connecting to BAM...[/cyan]")
        async with BAMClient(
            config=config.bam,
        ) as client:
            console.print("[green]Connected successfully![/green]\n")

            # Create exporter
            exporter = BlueCatExporter(client, allow_formulas=allow_formulas)

            # Determine configuration ID if needed
            resolved_config_id = config_id
            if network and not resolved_config_id:
                if config_name:
                    console.print(f"[cyan]Resolving configuration '{config_name}'...[/cyan]")
                    cfg = await client.get_configuration_by_name(config_name)
                    resolved_config_id = cfg.get("id")
                    if not resolved_config_id:
                        console.print(
                            f"[bold red]ERROR:[/bold red] Configuration '{config_name}' found but has no ID"
                        )
                        raise typer.Exit(code=1)
                else:
                    console.print(
                        "[bold red]ERROR:[/bold red] Either --config-id or --config-name is required when using --network with CIDR"
                    )
                    raise typer.Exit(code=1)

            # Parse fields from string to list if present
            fields_list = fields.split(",") if fields else None

            # Export based on scope
            if network:
                console.print(f"[cyan]Exporting network {network}...[/cyan]")

                # Check if network is ID or CIDR
                try:
                    network_id = int(network)
                    await exporter.export_network(
                        network_identifier=network_id,
                        include_children=include_children,
                        include_addresses=include_addresses,
                        action=action,
                        filter_str=filter_str,
                        fields=fields_list,
                        limit=limit,
                        order_by=order_by,
                    )
                except ValueError:
                    # It's a CIDR
                    await exporter.export_network(
                        network_identifier=network,
                        config_id=resolved_config_id,
                        include_children=include_children,
                        include_addresses=include_addresses,
                        action=action,
                        filter_str=filter_str,
                        fields=fields_list,
                        limit=limit,
                        order_by=order_by,
                    )

            elif block:
                console.print(f"[cyan]Exporting block {block}...[/cyan]")
                await exporter.export_block(
                    block_id=block,
                    include_children=include_children,
                    include_addresses=include_addresses,
                    action=action,
                    filter_str=filter_str,
                    fields=fields_list,
                    limit=limit,
                    order_by=order_by,
                )

            elif zone:
                console.print(f"[cyan]Exporting zone {zone}...[/cyan]")
                # Check if zone is ID or FQDN
                try:
                    zone_id = int(zone)
                    await exporter.export_zone(
                        zone_identifier=zone_id,
                        include_children=include_children,
                        include_records=include_records,
                        action=action,
                        filter_str=filter_str,
                        fields=fields_list,
                        limit=limit,
                        order_by=order_by,
                    )
                except ValueError:
                    # It's an FQDN
                    if not view_id:
                        console.print(
                            "[bold red]ERROR:[/bold red] --view-id is required when using --zone with FQDN"
                        )
                        raise typer.Exit(code=1) from None
                    await exporter.export_zone(
                        zone_identifier=zone,
                        view_id=view_id,
                        include_children=include_children,
                        include_records=include_records,
                        action=action,
                        filter_str=filter_str,
                        fields=fields_list,
                        limit=limit,
                        order_by=order_by,
                    )

            # Write CSV
            console.print(f"\n[cyan]Writing CSV to {output_file}...[/cyan]")
            await exporter.write_csv(output_file)

            # Display results
            resource_count = len(exporter.exported_resources)
            udf_count = len(exporter.discovered_udfs)

            console.print("\n[bold green]SUCCESS: Export completed![/bold green]\n")
            console.print(f"Resources exported: [cyan]{resource_count}[/cyan]")
            console.print(f"UDFs discovered: [cyan]{udf_count}[/cyan]")
            if udf_count > 0:
                console.print(
                    f"UDF columns: [dim]{', '.join(sorted(exporter.discovered_udfs))}[/dim]"
                )
            console.print(f"Output file: [cyan]{output_file}[/cyan]")
            console.print("\n[dim]You can now edit this CSV and import it back with:[/dim]")
            console.print(f"[dim]  bluecat-import apply {output_file}[/dim]")

    # Run async export
    try:
        asyncio.run(run_export())
    except Exception as e:
        console.print(f"\n[bold red]ERROR:[/bold red] {str(e)}")
        raise typer.Exit(code=1) from e


@app.command()
def status(
    session_id: str = typer.Argument(..., help="Session ID to check"),
    checkpoint_db: Path = typer.Option(
        Path(".checkpoints/checkpoints.db"),
        help="Checkpoint database path",
    ),
) -> None:
    """
    Check status of running or completed import session.

    Shows checkpoint information and progress.

    Examples:
        bluecat-import status abc12345
        bluecat-import status abc12345 --checkpoint-db custom/path.db
    """
    from .persistence import CheckpointManager

    console.print(f"\n[bold blue]Session Status:[/bold blue] [cyan]{session_id}[/cyan]\n")

    if not checkpoint_db.exists():
        console.print("[yellow]WARNING: No checkpoint database found[/yellow]")
        console.print(f"Path: {checkpoint_db}")
        return

    with CheckpointManager(checkpoint_db) as manager:
        checkpoint = manager.get_last_checkpoint(session_id)

        if not checkpoint:
            console.print(f"[yellow]WARNING: No checkpoint found for session {session_id}[/yellow]")
            return

        # Create status table
        table = Table(title=f"Session {session_id}")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Status", checkpoint.status.upper())
        table.add_row("Timestamp", checkpoint.timestamp)
        table.add_row("Batch ID", str(checkpoint.batch_id))
        table.add_row("Operation Index", str(checkpoint.operation_index))
        table.add_row(
            "Progress",
            f"{checkpoint.completed_operations}/{checkpoint.total_operations} operations",
        )

        if checkpoint.total_operations > 0:
            pct = (checkpoint.completed_operations / checkpoint.total_operations) * 100
            table.add_row("Completion", f"{pct:.1f}%")

        console.print(table)

        if checkpoint.status == "in_progress":
            console.print("\n[yellow]INFO: Session is still in progress[/yellow]")
            console.print("To resume: [cyan]bluecat-import apply <csv_file> --resume[/cyan]")
        elif checkpoint.status == "completed":
            console.print("\n[green]SUCCESS: Session completed successfully[/green]")
        elif checkpoint.status == "failed":
            console.print("\n[red]ERROR: Session failed[/red]")
            import json

            if checkpoint.metadata:
                metadata = json.loads(checkpoint.metadata)
                if "error" in metadata:
                    console.print(f"Error: {metadata['error']}")


@app.command()
def history(
    limit: int = typer.Option(10, help="Number of recent imports to show"),
    changelog_db: Path = typer.Option(
        Path(".changelogs/changelog.db"),
        help="Changelog database path",
    ),
) -> None:
    """
    List recent import sessions from changelog.

    Shows session summaries with statistics.

    Examples:
        bluecat-import history
        bluecat-import history --limit 20
        bluecat-import history --changelog-db custom/path.db
    """
    from .persistence import ChangeLog

    console.print(f"\n[bold blue]Recent Import Sessions[/bold blue] (last {limit})\n")

    if not changelog_db.exists():
        console.print("[yellow]WARNING: No changelog database found[/yellow]")
        console.print(f"Path: {changelog_db}")
        return

    with ChangeLog(changelog_db) as changelog:
        sessions = changelog.get_sessions(limit=limit)

        if not sessions:
            console.print("[yellow]No import sessions found[/yellow]")
            return

        # Create history table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Session ID", style="cyan")
        table.add_column("Start Time")
        table.add_column("Duration")
        table.add_column("Total Ops", justify="right")
        table.add_column("Success", justify="right", style="green")
        table.add_column("Failed", justify="right", style="red")
        table.add_column("Success Rate", justify="right")

        for session in sessions:
            # Calculate duration
            from datetime import datetime

            try:
                start = datetime.fromisoformat(session["start_time"])
                end = datetime.fromisoformat(session["end_time"])
                duration = (end - start).total_seconds()
                duration_str = f"{duration:.1f}s"
            except (ValueError, KeyError, TypeError):
                duration_str = "N/A"

            # Calculate success rate
            total = session["total_operations"]
            successful = session["successful"]
            success_rate = (successful / total * 100) if total > 0 else 100.0

            # Color code success rate
            if success_rate == 100:
                rate_style = "green"
            elif success_rate >= 90:
                rate_style = "yellow"
            else:
                rate_style = "red"

            table.add_row(
                session["session_id"],
                session["start_time"][:19],  # Trim milliseconds
                duration_str,
                str(total),
                str(successful),
                str(session["failed"]),
                f"[{rate_style}]{success_rate:.1f}%[/{rate_style}]",
            )

        console.print(table)
        console.print("\n[dim]To see details: bluecat-import status <session_id>[/dim]")


@app.command()
def version() -> None:
    """Show version information and features."""
    console.print(
        Panel.fit(
            "[bold]BlueCat CSV Importer[/bold]\n\n"
            "Version: [cyan]0.3.0[/cyan]\n"
            "Python: 3.11+\n\n"
            "[bold]Core Features:[/bold]\n"
            "- CSV validation and parsing\n"
            "- BAM REST API v2 client\n"
            "- State management and diff engine\n"
            "- Dependency graph with cycle detection\n"
            "- Adaptive throttling and execution\n"
            "- Checkpoint-based resume support\n"
            "- SQLite-based changelog\n"
            "- Automatic rollback generation\n"
            "- Metrics, logging, and reporting\n"
            "- Progress tracking and CLI\n\n"
            "[dim]Official BlueCat REST API v2 compliant[/dim]",
            title="About",
            border_style="blue",
        )
    )


@app.command()
def self_test(
    bam_url: str = typer.Option(..., "--url", help="BlueCat Address Manager URL"),
    username: str = typer.Option(..., "--username", help="BAM username"),
    password: str = typer.Option(..., "--password", help="BAM password", hide_input=True),
    config_name: str = typer.Option(
        "Default", "--config", help="Original configuration name used in sample CSVs"
    ),
    view_name: str = typer.Option(
        "Internal", "--view", help="Original view name used in sample CSVs"
    ),
    test_config_prefix: str = typer.Option(
        "bluecat-csv-test", "--test-prefix", help="Prefix for test configuration"
    ),
    cleanup: bool = typer.Option(
        False, "--cleanup", help="Force cleanup of test configuration (even on failure)"
    ),
    auto_cleanup: bool = typer.Option(
        False, "--auto-cleanup", help="Automatically cleanup test configuration on success only"
    ),
    report_file: Path | None = typer.Option(
        None, "--report", help="Save detailed test report to file"
    ),
    csv_tests: bool = typer.Option(
        False, "--csv-tests", help="Run CSV file tests from samples directory"
    ),
    samples_dir: Path | None = typer.Option(
        None, "--samples-dir", help="Directory containing CSV files to test"
    ),
    csv_files: list[str] | None = typer.Option(
        None, "--csv-file", help="Specific CSV files to test (can be used multiple times)"
    ),
    csv_execute: bool = typer.Option(
        False, "--csv-execute", help="Execute CSV operations (default is dry-run)"
    ),
) -> None:
    """
    Run comprehensive self-test against BlueCat Address Manager.

    ISOLATED TEST ENVIRONMENT:
    Creates a temporary configuration and view for isolated testing.
    Sample CSV paths are dynamically substituted to use the temp environment.
    This ensures tests don't interfere with production data.

    DEFAULT MODE (Comprehensive Test):
    Creates a dedicated test configuration and validates ALL functionality:
    - Connection and authentication
    - IP Management (blocks, networks, addresses)
    - DNS Management (zones, host records)
    - DHCP Management (ranges, client classes, deployment roles)
    - CSV Import Workflow (parsing, dependency resolution, planning, validation, dry-run)
    - Export/Import workflows
    - Safety and validation features
    - Error handling and recovery

    CSV TEST MODE (--csv-tests):
    Tests CSV files from the samples directory against a live BAM instance:
    - Creates isolated temp configuration and view
    - Dynamically substitutes config/view paths in CSV rows
    - Validates CSV parsing and schema
    - Runs through the complete import pipeline
    - Reports success/failure for each CSV file
    - Default is dry-run mode, use --csv-execute for actual changes

    CLEANUP BEHAVIOR:
    - By default: Test environment is preserved for debugging/validation
    - --auto-cleanup: Cleanup only if ALL tests pass (recommended for CI/CD)
    - --cleanup: Force cleanup regardless of test results

    Examples:
        # Comprehensive test (preserves test config)
        bluecat-import self-test --url https://bam.example.com --username admin

        # CSV tests with auto-cleanup on success
        bluecat-import self-test --url https://bam.example.com --username admin --csv-tests --auto-cleanup

        # CSV tests with custom config/view names and report
        bluecat-import self-test --url https://bam.example.com --username admin --csv-tests \\
            --config Default --view Internal --report test_report.json

        # Force cleanup even on failure
        bluecat-import self-test --url https://bam.example.com --username admin --csv-tests --cleanup
    """
    import asyncio
    import json
    import uuid

    from .config import ImporterConfig
    from .self_test import BlueCatSelfTest

    # Determine test mode
    test_mode = "CSV Tests" if csv_tests else "Comprehensive Test"

    # Determine cleanup mode description
    if cleanup:
        cleanup_desc = "Force (always cleanup)"
    elif auto_cleanup:
        cleanup_desc = "Auto (cleanup on success)"
    else:
        cleanup_desc = "Disabled (preserve for debugging)"

    console.print(
        Panel.fit(
            f"[bold blue]BlueCat CSV Self-Test[/bold blue]\n\n"
            f"Mode: [cyan]{test_mode}[/cyan]\n"
            f"BAM URL: [cyan]{bam_url}[/cyan]\n"
            f"Username: [cyan]{username}[/cyan]\n"
            f"Original Config: [cyan]{config_name}[/cyan]\n"
            f"Original View: [cyan]{view_name}[/cyan]"
            + (
                f"\nSamples Dir: [cyan]{samples_dir or './samples'}[/cyan]"
                if csv_tests
                else f"\nTest Prefix: [cyan]{test_config_prefix}[/cyan]"
            )
            + f"\nCleanup: [yellow]{cleanup_desc}[/yellow]"
            + (
                f"\nCSV Execute: [red]{'Enabled' if csv_execute else 'Disabled (Dry-run)'}[/red]"
                if csv_tests
                else ""
            )
            + f"\nReport: [green]{'Enabled' if report_file else 'Disabled'}[/green]",
            border_style="blue",
        )
    )

    if csv_tests:
        console.print(
            "\n[cyan]INFO: A temporary configuration and view will be created for isolated testing.[/cyan]"
        )
        console.print(
            "[dim]CSV paths will be dynamically substituted to use the temp environment.[/dim]\n"
        )

    if not cleanup and not auto_cleanup:
        console.print(
            "[yellow]INFO: Test environment will be preserved for manual validation.[/yellow]"
        )
        console.print("[dim]Use --auto-cleanup for CI/CD or --cleanup to force removal.[/dim]\n")

    if csv_tests and not csv_execute:
        console.print(
            "[yellow]INFO: Running CSV tests in DRY-RUN mode (no changes will be made).[/yellow]"
        )
        console.print("[dim]Use --csv-execute to apply changes to BAM.[/dim]\n")

    async def run_self_test():
        start_time = datetime.now()
        test_id = str(uuid.uuid4())[:8]

        # Create temporary configuration for testing
        from .config import BAMConfig

        config = ImporterConfig()
        config.bam = BAMConfig(
            base_url=bam_url,
            username=username,
            password=password,
            api_version="v2",
            timeout=60,
            verify_ssl=False,  # Disable SSL verification for testing
        )

        # Initialize self-test
        self_test = BlueCatSelfTest(config)

        if csv_tests:
            # Run CSV file tests with temp environment
            test_report = await self_test.run_csv_tests(
                samples_dir=samples_dir,
                config_name=config_name,
                view_name=view_name,
                dry_run=not csv_execute,
                selected_files=csv_files,
                create_temp_environment=True,
            )
        else:
            # Run comprehensive self-test
            test_report = await self_test.run_comprehensive_test(
                config_name=config_name, test_config_prefix=test_config_prefix, test_id=test_id
            )

        # Generate final report
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        console.print("\n[bold green]Self-Test completed![/bold green]\n")
        console.print(f"Duration: {duration:.2f} seconds")
        if not csv_tests:
            console.print(f"Test ID: [cyan]{test_id}[/cyan]")

        # Handle CSV test reports differently
        if csv_tests:
            # Generate and display CSV test report
            csv_report = self_test.generate_csv_test_report(test_report)
            console.print(csv_report)

            # Save JSON report if requested
            if report_file:
                self_test.save_csv_test_report(test_report, report_file)
                console.print(f"\n[green]Detailed JSON report saved to: {report_file}[/green]")
        else:
            # Summary table for comprehensive tests
            table = Table(title="Test Summary")
            table.add_column("Category", style="cyan")
            table.add_column("Passed", justify="right", style="green")
            table.add_column("Failed", justify="right", style="red")
            table.add_column("Success Rate", justify="right")

            for category, results in test_report["categories"].items():
                passed = results["passed"]
                failed = results["failed"]
                total = passed + failed
                success_rate = (passed / total * 100) if total > 0 else 0
                table.add_row(category, str(passed), str(failed), f"{success_rate:.1f}%")

            console.print(table)

        # Overall results
        total_passed = test_report["summary"]["total_passed"]
        total_failed = test_report["summary"]["total_failed"]
        total_tests = total_passed + total_failed
        overall_success = (total_passed / total_tests * 100) if total_tests > 0 else 0

        if csv_tests:
            # Show CSV test summary from report
            csv_summary = test_report.get("details", {}).get("csv_test_summary", {})
            if csv_summary:
                console.print("\n[bold]Overall Results:[/bold]")
                console.print(f"Total Files: {csv_summary.get('total_files', 0)}")
                console.print(
                    f"Successful Files: [green]{csv_summary.get('successful_files', 0)}[/green]"
                )
                console.print(f"Failed Files: [red]{csv_summary.get('failed_files', 0)}[/red]")
                console.print(f"Total Operations: {csv_summary.get('total_operations', 0)}")
                console.print(
                    f"Successful Ops: [green]{csv_summary.get('successful_operations', 0)}[/green]"
                )
                console.print(f"Failed Ops: [red]{csv_summary.get('failed_operations', 0)}[/red]")
        else:
            # Show comprehensive test results
            console.print("\n[bold]Overall Results:[/bold]")
            console.print(f"Total Tests: {total_tests}")
            console.print(f"Passed: [green]{total_passed}[/green]")
            console.print(f"Failed: [red]{total_failed}[/red]")
            console.print(f"Success Rate: {overall_success:.1f}%")

        if not csv_tests and test_report.get("test_config"):
            console.print("\n[cyan]Test Configuration Created:[/cyan]")
            console.print(f"Name: [yellow]{test_report['test_config']['name']}[/yellow]")
            console.print(f"ID: {test_report['test_config']['id']}")
            console.print(f"View ID: {test_report['test_config']['view_id']}")

        if not csv_tests and total_failed > 0:
            console.print("\n[red]Failed Tests:[/red]")
            for failure in test_report["failures"]:
                console.print(f"  • {failure}")

        # Save detailed report if requested
        if report_file:
            report_data = {
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": duration,
                "bam_url": bam_url,
                "config_name": config_name,
            }

            if not csv_tests:
                report_data.update(
                    {
                        "test_id": test_id,
                        "test_config": test_report.get("test_config"),
                        "summary": test_report["summary"],
                        "categories": test_report["categories"],
                        "failures": test_report["failures"],
                        "details": test_report.get("details", {}),
                    }
                )
            else:
                # CSV tests specific data
                report_data.update(
                    {
                        "csv_test_summary": test_report.get("details", {}).get(
                            "csv_test_summary", {}
                        ),
                        "csv_test_results": test_report.get("details", {}).get(
                            "csv_test_results", {}
                        ),
                    }
                )

            with open(report_file, "w") as f:
                json.dump(report_data, f, indent=2)
            console.print(f"\n[detailed report saved to: [cyan]{report_file}[/cyan]]")

        # Handle cleanup based on flags
        test_env_info = test_report.get("test_environment", {})
        should_cleanup = False
        cleanup_reason = ""

        if cleanup:
            # Force cleanup regardless of test results
            should_cleanup = True
            cleanup_reason = "forced cleanup requested"
        elif auto_cleanup:
            # Auto cleanup only on success
            if test_report.get("overall_success", False):
                should_cleanup = True
                cleanup_reason = "auto-cleanup on success"
            else:
                console.print("\n[yellow]Skipping auto-cleanup due to test failures.[/yellow]")
                if test_env_info:
                    console.print(
                        f"[dim]Test environment preserved: {test_env_info.get('config_name', 'unknown')}[/dim]"
                    )

        if should_cleanup and test_env_info:
            console.print(f"\n[yellow]Cleaning up test environment ({cleanup_reason})...[/yellow]")
            try:
                if cleanup:
                    cleanup_success = await self_test.force_cleanup()
                else:
                    cleanup_success = await self_test.cleanup_if_successful()

                if cleanup_success:
                    console.print(
                        "[green]SUCCESS: Test environment cleaned up successfully[/green]"
                    )
                else:
                    console.print("[red]FAILED: Failed to clean up test environment[/red]")
            except Exception as e:
                console.print(f"[red]ERROR: Cleanup error: {e}[/red]")

        elif not should_cleanup and test_env_info:
            console.print("\n[cyan]Test Environment Preserved:[/cyan]")
            console.print(
                f"  Configuration: [yellow]{test_env_info.get('config_name', 'N/A')}[/yellow]"
            )
            console.print(f"  Config ID: {test_env_info.get('config_id', 'N/A')}")
            console.print(f"  View: {test_env_info.get('view_name', 'N/A')}")
            console.print(f"  View ID: {test_env_info.get('view_id', 'N/A')}")

        # Also handle comprehensive test cleanup for backwards compatibility
        if not csv_tests and test_report.get("test_config") and (cleanup or auto_cleanup):
            config_id = test_report["test_config"].get("id")
            if config_id and not test_env_info:  # Only if not already handled above
                console.print("\n[yellow]Cleaning up comprehensive test resources...[/yellow]")
                try:
                    cleanup_success = await self_test.cleanup_test_config(config_id)
                    if cleanup_success:
                        console.print("[green]SUCCESS: Test resources cleaned up[/green]")
                except Exception as e:
                    console.print(f"[red]ERROR: Cleanup error: {e}[/red]")

        return test_report

    # Run the self-test
    try:
        asyncio.run(run_self_test())
    except Exception as e:
        console.print(f"\n[bold red]SELF-TEST FAILED:[/bold red] {str(e)}")
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    app()
