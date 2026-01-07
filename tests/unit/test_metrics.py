import unittest

from src.importer.observability.metrics import LoggerBackend, MetricsCollector, get_global_collector


class TestLoggerBackend(unittest.TestCase):
    def test_increment_counter(self):
        backend = LoggerBackend()
        backend.increment("test_counter", 1)
        backend.increment("test_counter", 2, tags={"status": "ok"})

        summary = backend.get_summary()
        counters = summary["counters"]

        self.assertEqual(counters["test_counter"], 1)
        self.assertEqual(counters["test_counter[status=ok]"], 2)

    def test_gauge(self):
        backend = LoggerBackend()
        backend.gauge("test_gauge", 50.0)
        backend.gauge("test_gauge", 75.0)  # overwrite

        summary = backend.get_summary()
        gauges = summary["gauges"]

        self.assertEqual(gauges["test_gauge"], 75.0)

    def test_timing(self):
        backend = LoggerBackend()
        backend.timing("test_timer", 100)
        backend.timing("test_timer", 200)

        summary = backend.get_summary()
        timings = summary["timings"]

        self.assertEqual(timings["test_timer"]["count"], 2)
        self.assertEqual(timings["test_timer"]["avg"], 150.0)
        self.assertEqual(timings["test_timer"]["max"], 200)


class TestMetricsCollector(unittest.TestCase):
    def test_singleton(self):
        c1 = get_global_collector()
        c2 = get_global_collector()
        self.assertIs(c1, c2)

    def test_count_operation(self):
        # Reset singleton for clean test?
        # Actually better to test instance directly to avoid pollution
        collector = MetricsCollector(backend="logger")
        collector.count_operation("create", "success", "network")

        summary = collector.get_summary()
        counters = summary["counters"]

        # Check formatted key matches implementation
        # Key: import_operation_total[operation=create,status=success,type=network]
        keys = list(counters.keys())
        self.assertTrue(
            any("import_operation_total" in k and "operation=create" in k for k in keys)
        )


if __name__ == "__main__":
    unittest.main()
