"""Metrics collection for monitoring import performance."""

from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class MetricsBackend(ABC):
    """Abstract base class for metrics backends."""

    @abstractmethod
    def increment(self, name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        pass

    @abstractmethod
    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        pass

    @abstractmethod
    def timing(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        pass


class LoggerBackend(MetricsBackend):
    """
    Simple in-memory metrics backend that aggregates stats for logging.
    """

    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()
        self.gauges: dict[str, float] = {}
        self.timings: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter."""
        key = self._format_key(name, tags)
        self.counters[key] += value

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge value."""
        # Logger backend keeps the last value for gauge.
        key = self._format_key(name, tags)
        self.gauges[key] = value

    def timing(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing."""
        key = self._format_key(name, tags)
        self.timings[key].append(value)

    def _format_key(self, name: str, tags: dict[str, str] | None) -> str:
        if not tags:
            return name
        sorted_tags = sorted(tags.items())
        tag_str = ",".join(f"{k}={v}" for k, v in sorted_tags)
        return f"{name}[{tag_str}]"

    def get_summary(self) -> dict[str, Any]:
        """Return a summary of collected metrics."""
        summary: dict[str, Any] = {
            "counters": dict(self.counters),
            "gauges": self.gauges,
            "timings": {},
        }

        for name, values in self.timings.items():
            if values:
                summary["timings"][name] = {
                    "count": len(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }
        return summary


class MetricsCollector:
    """
    Central collector for application metrics.
    """

    def __init__(self, backend: str = "logger") -> None:
        """
        Initialize Metrics Collector.

        Args:
            backend: Backend type to use. Currently only "logger" is supported.
                     Future implementations could support "prometheus" or "statsd".
        """
        self.backend: MetricsBackend

        if backend == "logger":
            self.backend = LoggerBackend()
        else:
            logger.warning(f"Unknown metrics backend '{backend}', defaulting to 'logger'")
            self.backend = LoggerBackend()

    def count_operation(self, operation_type: str, status: str, object_type: str) -> None:
        """Record an operation outcome."""
        self.backend.increment(
            "import_operation_total",
            tags={
                "operation": operation_type,
                "status": status,
                "type": object_type,
            },
        )

    def record_latency(self, operation_type: str, duration_ms: float) -> None:
        """Record operation latency."""
        self.backend.timing(
            "import_operation_duration_ms",
            duration_ms,
            tags={"operation": operation_type},
        )

    def update_concurrency(self, current_concurrency: int) -> None:
        """Update current concurrency gauge."""
        self.backend.gauge(
            "import_concurrency_current",
            float(current_concurrency),
        )

    def get_summary(self) -> dict[str, Any]:
        """Get summary from backend if supported."""
        if hasattr(self.backend, "get_summary"):
            return self.backend.get_summary()  # type: ignore
        return {}


# Singleton instance
_GLOBAL_COLLECTOR: MetricsCollector | None = None


def get_global_collector() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _GLOBAL_COLLECTOR
    if _GLOBAL_COLLECTOR is None:
        _GLOBAL_COLLECTOR = MetricsCollector()
    return _GLOBAL_COLLECTOR
