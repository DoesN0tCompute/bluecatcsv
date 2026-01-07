"""Advanced tests for metrics collection system.

This module tests the metrics system comprehensively:
- LoggerBackend functionality
- MetricsCollector API
- Tag handling and key formatting
- Summary generation
- Global collector singleton
"""

import pytest

from importer.observability.metrics import (
    LoggerBackend,
    MetricsBackend,
    MetricsCollector,
    get_global_collector,
)


class TestMetricsBackend:
    """Test MetricsBackend abstract base class."""

    def test_metrics_backend_is_abstract(self):
        """Test that MetricsBackend cannot be instantiated directly."""
        with pytest.raises(TypeError):
            MetricsBackend()  # Should raise TypeError for abstract class

    def test_metrics_backend_has_abstract_methods(self):
        """Test that MetricsBackend defines abstract methods."""
        assert hasattr(MetricsBackend, "increment")
        assert hasattr(MetricsBackend, "gauge")
        assert hasattr(MetricsBackend, "timing")


class TestLoggerBackend:
    """Test LoggerBackend implementation."""

    def test_logger_backend_initialization(self):
        """Test LoggerBackend initializes with empty data structures."""
        backend = LoggerBackend()
        assert len(backend.counters) == 0
        assert len(backend.gauges) == 0
        assert len(backend.timings) == 0

    def test_increment_simple(self):
        """Test basic counter increment."""
        backend = LoggerBackend()
        backend.increment("test_counter")
        assert backend.counters["test_counter"] == 1

    def test_increment_multiple_times(self):
        """Test counter increments accumulate."""
        backend = LoggerBackend()
        backend.increment("test_counter")
        backend.increment("test_counter")
        backend.increment("test_counter")
        assert backend.counters["test_counter"] == 3

    def test_increment_with_value(self):
        """Test counter increment with custom value."""
        backend = LoggerBackend()
        backend.increment("test_counter", value=5)
        assert backend.counters["test_counter"] == 5
        backend.increment("test_counter", value=3)
        assert backend.counters["test_counter"] == 8

    def test_increment_with_tags(self):
        """Test counter increment with tags."""
        backend = LoggerBackend()
        backend.increment("operations", tags={"type": "create", "status": "success"})
        backend.increment("operations", tags={"type": "update", "status": "success"})

        # Different tags should create different keys
        assert len(backend.counters) == 2
        assert backend.counters["operations[status=success,type=create]"] == 1
        assert backend.counters["operations[status=success,type=update]"] == 1

    def test_gauge_simple(self):
        """Test basic gauge setting."""
        backend = LoggerBackend()
        backend.gauge("concurrency", 10.5)
        assert backend.gauges["concurrency"] == 10.5

    def test_gauge_overwrite(self):
        """Test that gauge overwrites previous value."""
        backend = LoggerBackend()
        backend.gauge("concurrency", 10)
        backend.gauge("concurrency", 20)
        backend.gauge("concurrency", 15)
        assert backend.gauges["concurrency"] == 15

    def test_gauge_with_tags(self):
        """Test gauge with tags."""
        backend = LoggerBackend()
        backend.gauge("queue_size", 100, tags={"queue": "high_priority"})
        backend.gauge("queue_size", 50, tags={"queue": "low_priority"})

        assert backend.gauges["queue_size[queue=high_priority]"] == 100
        assert backend.gauges["queue_size[queue=low_priority]"] == 50

    def test_timing_simple(self):
        """Test basic timing recording."""
        backend = LoggerBackend()
        backend.timing("operation_duration", 123.45)
        assert "operation_duration" in backend.timings
        assert len(backend.timings["operation_duration"]) == 1
        assert backend.timings["operation_duration"][0] == 123.45

    def test_timing_multiple_values(self):
        """Test timing records multiple values."""
        backend = LoggerBackend()
        backend.timing("operation_duration", 100.0)
        backend.timing("operation_duration", 200.0)
        backend.timing("operation_duration", 150.0)

        assert len(backend.timings["operation_duration"]) == 3
        assert backend.timings["operation_duration"] == [100.0, 200.0, 150.0]

    def test_timing_with_tags(self):
        """Test timing with tags."""
        backend = LoggerBackend()
        backend.timing("api_latency", 50.0, tags={"endpoint": "networks"})
        backend.timing("api_latency", 75.0, tags={"endpoint": "zones"})

        assert len(backend.timings["api_latency[endpoint=networks]"]) == 1
        assert len(backend.timings["api_latency[endpoint=zones]"]) == 1

    def test_format_key_no_tags(self):
        """Test _format_key with no tags."""
        backend = LoggerBackend()
        key = backend._format_key("metric_name", None)
        assert key == "metric_name"

    def test_format_key_with_tags(self):
        """Test _format_key with tags."""
        backend = LoggerBackend()
        key = backend._format_key("metric_name", {"tag1": "value1", "tag2": "value2"})
        # Tags should be sorted alphabetically
        assert key == "metric_name[tag1=value1,tag2=value2]"

    def test_format_key_tags_sorted(self):
        """Test that _format_key sorts tags alphabetically."""
        backend = LoggerBackend()
        key = backend._format_key("metric", {"z": "last", "a": "first", "m": "middle"})
        assert key == "metric[a=first,m=middle,z=last]"

    def test_get_summary_empty(self):
        """Test get_summary with no metrics."""
        backend = LoggerBackend()
        summary = backend.get_summary()

        assert summary["counters"] == {}
        assert summary["gauges"] == {}
        assert summary["timings"] == {}

    def test_get_summary_with_counters(self):
        """Test get_summary includes counters."""
        backend = LoggerBackend()
        backend.increment("counter1", value=5)
        backend.increment("counter2", value=10)

        summary = backend.get_summary()
        assert summary["counters"]["counter1"] == 5
        assert summary["counters"]["counter2"] == 10

    def test_get_summary_with_gauges(self):
        """Test get_summary includes gauges."""
        backend = LoggerBackend()
        backend.gauge("gauge1", 123.45)
        backend.gauge("gauge2", 678.90)

        summary = backend.get_summary()
        assert summary["gauges"]["gauge1"] == 123.45
        assert summary["gauges"]["gauge2"] == 678.90

    def test_get_summary_with_timings(self):
        """Test get_summary includes timing statistics."""
        backend = LoggerBackend()
        backend.timing("api_latency", 100.0)
        backend.timing("api_latency", 200.0)
        backend.timing("api_latency", 150.0)

        summary = backend.get_summary()
        timing_stats = summary["timings"]["api_latency"]

        assert timing_stats["count"] == 3
        assert timing_stats["avg"] == 150.0  # (100 + 200 + 150) / 3
        assert timing_stats["min"] == 100.0
        assert timing_stats["max"] == 200.0

    def test_get_summary_timing_empty_list(self):
        """Test get_summary handles empty timing lists."""
        backend = LoggerBackend()
        # Manually create empty timing list
        backend.timings["empty_timing"] = []

        summary = backend.get_summary()
        # Empty timing should not appear in summary
        assert "empty_timing" not in summary["timings"]


class TestMetricsCollector:
    """Test MetricsCollector class."""

    def test_metrics_collector_default_backend(self):
        """Test MetricsCollector uses logger backend by default."""
        collector = MetricsCollector()
        assert isinstance(collector.backend, LoggerBackend)

    def test_metrics_collector_explicit_logger_backend(self):
        """Test MetricsCollector with explicit logger backend."""
        collector = MetricsCollector(backend="logger")
        assert isinstance(collector.backend, LoggerBackend)

    def test_metrics_collector_unknown_backend_defaults_to_logger(self):
        """Test MetricsCollector defaults to logger for unknown backends."""
        collector = MetricsCollector(backend="unknown")
        assert isinstance(collector.backend, LoggerBackend)

    def test_count_operation(self):
        """Test count_operation method."""
        collector = MetricsCollector()
        collector.count_operation("create", "success", "ip4_network")

        # Verify backend received the increment
        backend = collector.backend
        key = "import_operation_total[operation=create,status=success,type=ip4_network]"
        assert backend.counters[key] == 1

    def test_count_operation_multiple(self):
        """Test multiple count_operation calls."""
        collector = MetricsCollector()
        collector.count_operation("create", "success", "ip4_network")
        collector.count_operation("create", "success", "ip4_network")
        collector.count_operation("update", "success", "ip4_address")

        backend = collector.backend
        assert (
            backend.counters[
                "import_operation_total[operation=create,status=success,type=ip4_network]"
            ]
            == 2
        )
        assert (
            backend.counters[
                "import_operation_total[operation=update,status=success,type=ip4_address]"
            ]
            == 1
        )

    def test_record_latency(self):
        """Test record_latency method."""
        collector = MetricsCollector()
        collector.record_latency("create", 123.45)

        backend = collector.backend
        key = "import_operation_duration_ms[operation=create]"
        assert key in backend.timings
        assert backend.timings[key][0] == 123.45

    def test_record_latency_multiple(self):
        """Test multiple record_latency calls."""
        collector = MetricsCollector()
        collector.record_latency("create", 100.0)
        collector.record_latency("create", 200.0)
        collector.record_latency("update", 150.0)

        backend = collector.backend
        create_key = "import_operation_duration_ms[operation=create]"
        update_key = "import_operation_duration_ms[operation=update]"

        assert len(backend.timings[create_key]) == 2
        assert backend.timings[create_key] == [100.0, 200.0]
        assert len(backend.timings[update_key]) == 1
        assert backend.timings[update_key][0] == 150.0

    def test_update_concurrency(self):
        """Test update_concurrency method."""
        collector = MetricsCollector()
        collector.update_concurrency(5)

        backend = collector.backend
        assert backend.gauges["import_concurrency_current"] == 5.0

    def test_update_concurrency_overwrites(self):
        """Test that update_concurrency overwrites previous value."""
        collector = MetricsCollector()
        collector.update_concurrency(5)
        collector.update_concurrency(10)
        collector.update_concurrency(7)

        backend = collector.backend
        assert backend.gauges["import_concurrency_current"] == 7.0

    def test_get_summary(self):
        """Test get_summary method."""
        collector = MetricsCollector()
        collector.count_operation("create", "success", "ip4_network")
        collector.record_latency("create", 150.0)
        collector.update_concurrency(5)

        summary = collector.get_summary()

        assert "counters" in summary
        assert "gauges" in summary
        assert "timings" in summary
        assert summary["gauges"]["import_concurrency_current"] == 5.0


class TestGlobalCollector:
    """Test global collector singleton."""

    def test_get_global_collector_returns_instance(self):
        """Test get_global_collector returns MetricsCollector."""
        collector = get_global_collector()
        assert isinstance(collector, MetricsCollector)

    def test_get_global_collector_is_singleton(self):
        """Test get_global_collector returns same instance."""
        collector1 = get_global_collector()
        collector2 = get_global_collector()
        assert collector1 is collector2

    def test_global_collector_persists_data(self):
        """Test that global collector persists data across calls."""
        collector1 = get_global_collector()
        collector1.count_operation("create", "success", "test")

        collector2 = get_global_collector()
        summary = collector2.get_summary()

        # Should have the counter from collector1
        assert len(summary["counters"]) > 0


class TestMetricsIntegration:
    """Integration tests for metrics system."""

    def test_full_workflow(self):
        """Test complete metrics collection workflow."""
        collector = MetricsCollector()

        # Simulate import operations
        collector.count_operation("create", "success", "ip4_network")
        collector.count_operation("create", "success", "ip4_address")
        collector.count_operation("update", "success", "ip4_address")
        collector.count_operation("delete", "failed", "ip4_network")

        collector.record_latency("create", 100.0)
        collector.record_latency("create", 150.0)
        collector.record_latency("update", 75.0)

        collector.update_concurrency(3)
        collector.update_concurrency(5)
        collector.update_concurrency(4)

        # Get summary
        summary = collector.get_summary()

        # Verify counters
        assert len(summary["counters"]) == 4

        # Verify gauges
        assert summary["gauges"]["import_concurrency_current"] == 4.0

        # Verify timings
        assert "import_operation_duration_ms[operation=create]" in summary["timings"]
        create_stats = summary["timings"]["import_operation_duration_ms[operation=create]"]
        assert create_stats["count"] == 2
        assert create_stats["avg"] == 125.0
        assert create_stats["min"] == 100.0
        assert create_stats["max"] == 150.0

    def test_metrics_with_special_characters_in_tags(self):
        """Test metrics with special characters in tag values."""
        collector = MetricsCollector()
        # Tag values with spaces, dashes, underscores
        collector.count_operation("create", "success", "ip4-network")
        collector.count_operation("create", "partial success", "ip4_address")

        summary = collector.get_summary()
        assert len(summary["counters"]) == 2

    def test_empty_collector_summary(self):
        """Test summary from empty collector."""
        collector = MetricsCollector()
        summary = collector.get_summary()

        assert summary["counters"] == {}
        assert summary["gauges"] == {}
        assert summary["timings"] == {}
