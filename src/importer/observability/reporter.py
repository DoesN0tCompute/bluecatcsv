"""Import Report Generator.

Generates JSON and HTML reports for import sessions.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from ..persistence.changelog import ChangeLog

logger = structlog.get_logger(__name__)


@dataclass
class ImportReport:
    """
    Structured report data for an import session.

    Attributes:
        session_id: Session identifier
        status: Final status (completed, failed, partial)
        start_time: Start timestamp
        end_time: End timestamp
        duration_seconds: Total duration
        csv_file: Path to CSV file
        dry_run: Whether it was a dry run
        total_operations: Total operations
        successful_operations: Count of successful ops
        failed_operations: Count of failed ops
        skipped_operations: Count of skipped ops
        operations_per_second: Throughput metric
        avg_operation_duration_ms: Average latency
        max_operation_duration_ms: Max latency
        initial_concurrency: Starting concurrency
        final_concurrency: Ending concurrency
        rate_limit_hits: Number of rate limit errors
        rollback_csv_generated: Whether rollback CSV was created
        rollback_csv_path: Path to rollback CSV
        errors: List of error details
        creates: Count of CREATE operations
        updates: Count of UPDATE operations
        deletes: Count of DELETE operations
        noops: Count of NOOP operations
    """

    session_id: str
    status: str
    start_time: str
    end_time: str
    duration_seconds: float
    csv_file: str
    dry_run: bool
    total_operations: int
    successful_operations: int
    failed_operations: int
    skipped_operations: int
    operations_per_second: float
    avg_operation_duration_ms: float
    max_operation_duration_ms: float
    initial_concurrency: int
    final_concurrency: int
    rate_limit_hits: int
    rollback_csv_generated: bool
    rollback_csv_path: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)
    creates: int = 0
    updates: int = 0
    deletes: int = 0
    noops: int = 0


class ReportGenerator:
    """
    Generate comprehensive reports for import sessions.

    Features:
    - JSON report generation (machine readable)
    - HTML report generation (human readable with visualizations)
    - Aggregates data from logs, metrics, and changelog
    """

    def __init__(self, changelog: ChangeLog | None = None) -> None:
        """
        Initialize Report Generator.

        Args:
            changelog: Optional ChangeLog instance for historical data lookup
        """
        self.changelog = changelog

    def generate_report(
        self,
        session_id: str,
        start_time: datetime,
        end_time: datetime,
        csv_file: Path,
        dry_run: bool,
        results: list[Any],  # List[OperationResult]
        metrics: dict[str, Any],
        rollback_path: Path | None = None,
    ) -> ImportReport:
        """
        Generate report object from execution data.

        Args:
            session_id: Session identifier
            start_time: Start timestamp
            end_time: End timestamp
            csv_file: CSV file path
            dry_run: Dry run mode
            results: List of operation results
            metrics: Execution metrics
            rollback_path: Path to rollback CSV (if any)

        Returns:
            ImportReport object
        """
        duration = (end_time - start_time).total_seconds()
        total_ops = len(results)
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        # Assuming no explicit skipped status in result object yet, but could be added
        skipped = 0

        # Calculate breakdown
        creates = sum(1 for r in results if r.operation == "create")
        updates = sum(1 for r in results if r.operation == "update")
        deletes = sum(1 for r in results if r.operation == "delete")
        noops = sum(1 for r in results if r.operation == "noop")

        # Calculate performance
        ops_per_sec = total_ops / duration if duration > 0 else 0
        durations = [r.duration_ms for r in results if r.duration_ms is not None]
        avg_latency = sum(durations) / len(durations) if durations else 0
        max_latency = max(durations) if durations else 0

        # Collect errors
        errors = [
            {
                "row_id": r.row_id,
                "operation_type": r.operation,
                "error": r.error_message,
                "object_type": getattr(r, "object_type", None),  # Might not be on result
            }
            for r in results
            if not r.success
        ]

        status = "completed"
        if failed > 0:
            status = "partial" if successful > 0 else "failed"

        return ImportReport(
            session_id=session_id,
            status=status,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_seconds=duration,
            csv_file=str(csv_file),
            dry_run=dry_run,
            total_operations=total_ops,
            successful_operations=successful,
            failed_operations=failed,
            skipped_operations=skipped,
            operations_per_second=ops_per_sec,
            avg_operation_duration_ms=avg_latency,
            max_operation_duration_ms=max_latency,
            initial_concurrency=metrics.get("initial_concurrency", 0),
            final_concurrency=metrics.get("current_concurrency", 0),
            rate_limit_hits=metrics.get("rate_limit_errors", 0),
            rollback_csv_generated=rollback_path is not None,
            rollback_csv_path=str(rollback_path) if rollback_path else None,
            errors=errors,
            creates=creates,
            updates=updates,
            deletes=deletes,
            noops=noops,
        )

    def write_json_report(self, report: ImportReport, output_path: Path) -> None:
        """
        Write report as JSON.

        Args:
            report: Import report
            output_path: Output file path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(asdict(report), f, indent=2)

        logger.info("JSON report written", path=str(output_path))

    def write_html_report(self, report: ImportReport, output_path: Path) -> None:
        """
        Write report as HTML with visualizations.

        Args:
            report: Import report
            output_path: Output file path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        html = self._generate_html(report)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("HTML report written", path=str(output_path))

    def _generate_html(self, report: ImportReport) -> str:
        """
        Generate HTML report.

        Args:
            report: Import report

        Returns:
            HTML content string
        """
        status_color = {
            "completed": "#28a745",
            "failed": "#dc3545",
            "partial": "#ffc107",
        }

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>BlueCat Import Report - {report.session_id}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .status {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            color: white;
            font-weight: bold;
            background: {status_color.get(report.status, '#6c757d')};
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }}
        .stat-label {{
            color: #666;
            font-size: 14px;
            text-transform: uppercase;
        }}
        .section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section-title {{
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 15px;
            color: #333;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .error-row {{
            background: #fff3cd;
        }}
        .success-rate {{
            font-size: 48px;
            font-weight: bold;
            text-align: center;
            color: {status_color.get(report.status, '#6c757d')};
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>BlueCat Import Report</h1>
        <p><strong>Session:</strong> {report.session_id}</p>
        <p><strong>Status:</strong> <span class="status">{report.status.upper()}</span></p>
        <p><strong>Duration:</strong> {report.duration_seconds:.2f} seconds</p>
        <p><strong>CSV File:</strong> {report.csv_file}</p>
        {'<p><strong>Dry Run:</strong> Yes</p>' if report.dry_run else ''}
    </div>

    <div class="section">
        <div class="success-rate">
            {(report.successful_operations / report.total_operations * 100) if report.total_operations > 0 else 0:.1f}%
        </div>
        <p style="text-align: center; color: #666;">Success Rate</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{report.total_operations}</div>
            <div class="stat-label">Total Operations</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #28a745;">{report.successful_operations}</div>
            <div class="stat-label">Successful</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color: #dc3545;">{report.failed_operations}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{report.operations_per_second:.1f}</div>
            <div class="stat-label">Ops/Second</div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">Operation Breakdown</div>
        <table>
            <tr>
                <th>Operation Type</th>
                <th>Count</th>
                <th>Percentage</th>
            </tr>
            <tr>
                <td>CREATE</td>
                <td>{report.creates}</td>
                <td>{(report.creates / report.total_operations * 100) if report.total_operations > 0 else 0:.1f}%</td>
            </tr>
            <tr>
                <td>UPDATE</td>
                <td>{report.updates}</td>
                <td>{(report.updates / report.total_operations * 100) if report.total_operations > 0 else 0:.1f}%</td>
            </tr>
            <tr>
                <td>DELETE</td>
                <td>{report.deletes}</td>
                <td>{(report.deletes / report.total_operations * 100) if report.total_operations > 0 else 0:.1f}%</td>
            </tr>
            <tr>
                <td>NOOP</td>
                <td>{report.noops}</td>
                <td>{(report.noops / report.total_operations * 100) if report.total_operations > 0 else 0:.1f}%</td>
            </tr>
        </table>
    </div>

    <div class="section">
        <div class="section-title">Performance</div>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Average Operation Duration</td>
                <td>{report.avg_operation_duration_ms:.2f} ms</td>
            </tr>
            <tr>
                <td>Max Operation Duration</td>
                <td>{report.max_operation_duration_ms:.2f} ms</td>
            </tr>
            <tr>
                <td>Initial Concurrency</td>
                <td>{report.initial_concurrency}</td>
            </tr>
            <tr>
                <td>Final Concurrency</td>
                <td>{report.final_concurrency}</td>
            </tr>
            <tr>
                <td>Rate Limit Hits</td>
                <td>{report.rate_limit_hits}</td>
            </tr>
        </table>
    </div>

    {self._generate_errors_section(report.errors) if report.errors else ''}

    {self._generate_rollback_section(report) if report.rollback_csv_generated else ''}

    <div class="section">
        <p style="color: #666; font-size: 12px;">
            Generated: {datetime.now().isoformat()}<br>
            Start: {report.start_time}<br>
            End: {report.end_time}
        </p>
    </div>
</body>
</html>
"""
        return html

    def _generate_errors_section(self, errors: list[dict[str, Any]]) -> str:
        """
        Generate HTML errors section.

        Args:
            errors: List of error dictionaries

        Returns:
            HTML string for errors section
        """
        rows = "\n".join(
            f"""
            <tr class="error-row">
                <td>{error['row_id']}</td>
                <td>{error.get('object_type', 'N/A')}</td>
                <td>{error['operation_type']}</td>
                <td>{error['error']}</td>
            </tr>
            """
            for error in errors
        )

        return f"""
    <div class="section">
        <div class="section-title">Errors ({len(errors)})</div>
        <table>
            <tr>
                <th>Row ID</th>
                <th>Object Type</th>
                <th>Operation</th>
                <th>Error</th>
            </tr>
            {rows}
        </table>
    </div>
"""

    def _generate_rollback_section(self, report: ImportReport) -> str:
        """
        Generate HTML rollback section.

        Args:
            report: Import report

        Returns:
            HTML string for rollback section
        """
        return f"""
    <div class="section">
        <div class="section-title">Rollback</div>
        <p>Rollback CSV has been generated for this import session.</p>
        <p><strong>Path:</strong> <code>{report.rollback_csv_path}</code></p>
        <p>To rollback this import, run:</p>
        <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px;">
python import.py apply {report.rollback_csv_path}
        </pre>
    </div>
"""

    def get_session_summary(self, session_id: str) -> dict[str, Any] | None:
        """
        Get summary for a specific session from changelog.

        Args:
            session_id: Session identifier

        Returns:
            Summary dictionary or None
        """
        if not self.changelog:
            return None

        entries = self.changelog.get_session_entries(session_id)

        if not entries:
            return None

        successful = sum(1 for e in entries if e.success)
        failed = sum(1 for e in entries if not e.success)

        return {
            "session_id": session_id,
            "total_operations": len(entries),
            "successful": successful,
            "failed": failed,
            "start_time": entries[0].timestamp if entries else None,
            "end_time": entries[-1].timestamp if entries else None,
        }
