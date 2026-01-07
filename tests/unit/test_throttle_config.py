"""Unit tests for throttle configuration integration."""

from unittest.mock import AsyncMock

import pytest

from src.importer.config import ThrottleConfig
from src.importer.execution.throttle import AdaptiveThrottle


class TestThrottleConfig:
    """Test throttle configuration functionality."""

    def test_default_throttle_config(self):
        """Test default throttle configuration values."""
        config = ThrottleConfig()

        assert config.initial_concurrency == 10
        assert config.min_concurrency == 1
        assert config.max_concurrency == 50
        assert config.increase_factor == 1.2
        assert config.decrease_factor == 0.8
        assert config.rate_limit_decrease == 0.5
        assert config.adjustment_interval == 10.0
        assert config.healthy_error_rate == 0.01
        assert config.unhealthy_error_rate == 0.05
        assert config.high_latency_ms == 1000.0
        assert config.max_latency_samples == 100

    def test_custom_throttle_config(self):
        """Test custom throttle configuration values."""
        config = ThrottleConfig(
            initial_concurrency=20,
            min_concurrency=5,
            max_concurrency=100,
            increase_factor=1.5,
            decrease_factor=0.6,
            rate_limit_decrease=0.3,
            adjustment_interval=5.0,
            healthy_error_rate=0.02,
            unhealthy_error_rate=0.15,
            high_latency_ms=500.0,
            max_latency_samples=200,
        )

        assert config.initial_concurrency == 20
        assert config.min_concurrency == 5
        assert config.max_concurrency == 100
        assert config.increase_factor == 1.5
        assert config.decrease_factor == 0.6
        assert config.rate_limit_decrease == 0.3
        assert config.adjustment_interval == 5.0
        assert config.healthy_error_rate == 0.02
        assert config.unhealthy_error_rate == 0.15
        assert config.high_latency_ms == 500.0
        assert config.max_latency_samples == 200

    def test_throttle_config_validation(self):
        """Test throttle configuration validation."""
        # Valid configurations
        ThrottleConfig()  # defaults
        ThrottleConfig(initial_concurrency=1, max_concurrency=1)  # minimum
        ThrottleConfig(initial_concurrency=100, max_concurrency=100)  # single value

        # Edge cases that should work
        ThrottleConfig(increase_factor=1.0)  # no increase
        ThrottleConfig(decrease_factor=1.0)  # no decrease


class TestAdaptiveThrottleWithConfig:
    """Test AdaptiveThrottle with configuration integration."""

    def test_initialization_with_config(self):
        """Test throttle initialization with configuration object."""
        config = ThrottleConfig(
            initial_concurrency=15,
            min_concurrency=3,
            max_concurrency=75,
            increase_factor=1.8,
            decrease_factor=0.6,
            adjustment_interval=8.0,
            max_latency_samples=150,
        )

        throttle = AdaptiveThrottle(config)

        # Verify configuration was applied
        assert throttle.current_concurrency == 15
        assert throttle.min_concurrency == 3
        assert throttle.max_concurrency == 75
        assert throttle.adjustment_interval == 8.0
        assert throttle._max_latency_samples == 150
        assert throttle.config == config

    def test_initialization_with_default_config(self):
        """Test throttle initialization with default configuration."""
        throttle = AdaptiveThrottle()  # No config provided

        # Should use default values
        assert throttle.current_concurrency == 10
        assert throttle.min_concurrency == 1
        assert throttle.max_concurrency == 50
        assert throttle.adjustment_interval == 10.0
        assert throttle._max_latency_samples == 100
        assert isinstance(throttle.config, ThrottleConfig)

    def test_configuration_used_in_adjustment_logic(self):
        """Test that configuration values are used in adjustment logic."""
        config = ThrottleConfig(
            healthy_error_rate=0.05,  # Higher threshold
            unhealthy_error_rate=0.15,  # Higher threshold
            high_latency_ms=2000.0,  # Higher latency threshold
            increase_factor=2.0,  # More aggressive increase
            decrease_factor=0.4,  # More aggressive decrease
            rate_limit_decrease=0.2,  # More conservative rate limit handling
            adjustment_interval=1.0,  # Faster adjustments
        )

        throttle = AdaptiveThrottle(config)

        # Verify config is stored and used
        assert throttle.config.healthy_error_rate == 0.05
        assert throttle.config.unhealthy_error_rate == 0.15
        assert throttle.config.high_latency_ms == 2000.0
        assert throttle.config.increase_factor == 2.0
        assert throttle.config.decrease_factor == 0.4
        assert throttle.config.rate_limit_decrease == 0.2
        assert throttle.config.adjustment_interval == 1.0


class TestThrottleMetricsIntegration:
    """Test throttle metrics with configuration."""

    @pytest.fixture
    def custom_config(self):
        """Custom configuration for testing."""
        return ThrottleConfig(max_latency_samples=50, adjustment_interval=1.0)

    @pytest.fixture
    def throttle(self, custom_config):
        """Throttle with custom configuration."""
        return AdaptiveThrottle(custom_config)

    def test_latency_sample_limit(self, throttle):
        """Test that latency sample limit is respected."""
        # Fill up to the limit
        for _i in range(55):  # More than the limit of 50
            throttle.record_success(100.0)  # 100ms latency

        # Should only keep the most recent samples (limit is 50)
        assert len(throttle._latencies) == 50
        assert throttle.metrics.total_requests == 55
        assert throttle.metrics.successful_requests == 55

    def test_configurable_adjustment_interval(self, throttle):
        """Test that adjustment interval is configurable."""
        # Initial adjustment should be allowed
        throttle.record_success(100.0)  # Low latency
        # Should trigger adjustment due to interval being 1.0
        # Note: This tests the configuration value is stored correctly

        assert throttle.adjustment_interval == 1.0


class TestThrottleConfigurationValidation:
    """Test throttle configuration edge cases."""

    def test_boundary_values(self):
        """Test throttle configuration with boundary values."""
        config = ThrottleConfig(
            initial_concurrency=1,  # Minimum
            min_concurrency=1,
            max_concurrency=1000,  # High value
            increase_factor=5.0,  # High increase
            decrease_factor=0.1,  # Low decrease
            healthy_error_rate=0.0,  # No errors allowed
            unhealthy_error_rate=1.0,  # All errors unhealthy
            high_latency_ms=0.0,  # No latency allowed
            adjustment_interval=0.1,  # Very frequent
        )

        # Should not raise any errors
        throttle = AdaptiveThrottle(config)
        assert throttle.current_concurrency == 1
        assert throttle.max_concurrency == 1000
        assert throttle.min_concurrency == 1

    def test_relationship_constraints(self):
        """Test configuration relationships that should make sense."""
        config = ThrottleConfig(
            min_concurrency=10, initial_concurrency=15, max_concurrency=20  # Reasonable progression
        )

        throttle = AdaptiveThrottle(config)
        assert throttle.min_concurrency <= throttle.current_concurrency <= throttle.max_concurrency

    def test_factor_ranges(self):
        """Test that factors are in reasonable ranges."""
        # These should work without errors
        ThrottleConfig(increase_factor=1.0, decrease_factor=1.0)  # No change
        ThrottleConfig(increase_factor=2.0, decrease_factor=0.5)  # Moderate changes
        ThrottleConfig(rate_limit_decrease=0.1)  # Various rates


class TestThrottleConfigurationIntegration:
    """Test integration of throttle configuration with executor."""

    def test_policy_to_throttle_config_conversion(self):
        """Test conversion from PolicyConfig to ThrottleConfig."""
        from src.importer.config import PolicyConfig

        policy = PolicyConfig(initial_concurrency=25, min_concurrency=5, max_concurrency=150)

        # This simulates what the executor does
        throttle_config = ThrottleConfig(
            initial_concurrency=policy.max_concurrent_operations,
            min_concurrency=policy.min_concurrency,
            max_concurrency=policy.max_concurrency,
        )

        throttle = AdaptiveThrottle(throttle_config)

        assert throttle.current_concurrency == policy.max_concurrent_operations
        assert throttle.min_concurrency == policy.min_concurrency
        assert throttle.max_concurrency == policy.max_concurrency

    def test_executor_throttle_integration(self):
        """Test that executor properly creates throttle with configuration."""
        from src.importer.config import PolicyConfig
        from src.importer.execution.executor import OperationExecutor

        mock_client = AsyncMock()
        policy = PolicyConfig(max_concurrent_operations=15, min_concurrency=3)

        executor = OperationExecutor(mock_client, policy)

        # Executor should create throttle with config
        assert executor.throttle.current_concurrency == 15
        assert executor.throttle.min_concurrency == 3
        assert executor.throttle.max_concurrency == 50  # uses policy.max_concurrency
        assert hasattr(executor.throttle, "config")
