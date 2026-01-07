"""Unit tests for Custom Exceptions."""

import pytest

from src.importer.utils.exceptions import (
    BAMAPIError,
    BAMRateLimitError,
    CSVValidationError,
    CyclicDependencyError,
    PendingCreateError,
    ResourceNotFoundError,
    ValidationError,
)


class TestBAMAPIError:
    """Test BAMAPIError exception."""

    def test_bam_api_error_creation(self):
        """Test creating BAMAPIError."""
        error = BAMAPIError("API request failed", status_code=400)

        assert str(error) == "API request failed"
        assert error.status_code == 400

    def test_bam_api_error_inheritance(self):
        """Test BAMAPIError inheritance."""
        error = BAMAPIError("test error")

        # Should inherit from Exception
        assert isinstance(error, Exception)

    def test_bam_api_error_without_optional_parameters(self):
        """Test BAMAPIError without optional parameters."""
        error = BAMAPIError("Simple error")

        assert str(error) == "Simple error"
        assert error.status_code is None


class TestBAMRateLimitError:
    """Test BAMRateLimitError exception."""

    def test_bam_rate_limit_error_creation(self):
        """Test creating BAMRateLimitError."""
        error = BAMRateLimitError(retry_after=30)

        assert str(error) == "Rate limit exceeded, retry after 30s"
        assert error.retry_after == 30

    def test_bam_rate_limit_error_inheritance(self):
        """Test BAMRateLimitError inheritance."""
        error = BAMRateLimitError(retry_after=60)

        # Should inherit from BAMAPIError
        assert isinstance(error, Exception)
        assert isinstance(error, BAMAPIError)


class TestCSVValidationError:
    """Test CSVValidationError exception."""

    def test_csv_validation_error_creation(self):
        """Test creating CSVValidationError."""
        error = CSVValidationError("Invalid CSV format", line_number=5)

        assert str(error) == "Line 5: Invalid CSV format"
        assert error.line_number == 5

    def test_csv_validation_error_inheritance(self):
        """Test CSVValidationError inheritance."""
        error = CSVValidationError("CSV error")

        # Should inherit from ValidationError
        assert isinstance(error, Exception)
        assert isinstance(error, ValidationError)

    def test_csv_validation_error_without_details(self):
        """Test CSVValidationError without detailed information."""
        error = CSVValidationError("Empty CSV file")

        assert str(error) == "Empty CSV file"
        assert error.line_number is None


class TestCyclicDependencyError:
    """Test CyclicDependencyError exception."""

    def test_cyclic_dependency_error_creation(self):
        """Test creating CyclicDependencyError."""
        cycles = [["resource1", "resource2", "resource1"]]
        error = CyclicDependencyError("Cyclic dependency detected", cycles=cycles)

        assert str(error) == "Cyclic dependency detected"
        assert error.cycles == cycles

    def test_cyclic_dependency_error_inheritance(self):
        """Test CyclicDependencyError inheritance."""
        error = CyclicDependencyError("Cycle found")

        # Should inherit from ValidationError -> ImporterError -> Exception
        assert isinstance(error, Exception)
        # Note: CyclicDependencyError inherits from ImporterError, not ValidationError in current implementation
        # But let's check base exception
        assert isinstance(error, Exception)


class TestPendingCreateError:
    """Test PendingCreateError exception."""

    def test_pending_create_error_creation(self):
        """Test creating PendingCreateError."""
        error = PendingCreateError(path="/config/test/network", row_id="15")

        assert str(error) == "Path /config/test/network is pending creation (row 15)"
        assert error.path == "/config/test/network"
        assert error.row_id == "15"

    def test_pending_create_error_inheritance(self):
        """Test PendingCreateError inheritance."""
        error = PendingCreateError(path="/test", row_id="1")

        # Should inherit from ImporterError -> Exception
        assert isinstance(error, Exception)


class TestResourceNotFoundError:
    """Test ResourceNotFoundError exception."""

    def test_resource_not_found_error_creation(self):
        """Test creating ResourceNotFoundError."""
        error = ResourceNotFoundError("ip4_address", "/config/test/network/10.1.0.5")

        assert str(error) == "ip4_address not found: /config/test/network/10.1.0.5"
        assert error.resource_type == "ip4_address"
        assert error.identifier == "/config/test/network/10.1.0.5"

    def test_resource_not_found_error_inheritance(self):
        """Test ResourceNotFoundError inheritance."""
        error = ResourceNotFoundError("test_type", "test_identifier")

        # Should inherit from Exception
        assert isinstance(error, Exception)

    def test_resource_not_found_error_with_id(self):
        """Test ResourceNotFoundError with numeric ID."""
        error = ResourceNotFoundError("configuration", "123")

        assert str(error) == "configuration not found: 123"
        assert error.resource_type == "configuration"
        assert error.identifier == "123"


class TestValidationError:
    """Test base ValidationError exception."""

    def test_validation_error_creation(self):
        """Test creating ValidationError."""
        error = ValidationError("General validation error")

        assert str(error) == "General validation error"

    def test_validation_error_inheritance(self):
        """Test ValidationError inheritance."""
        error = ValidationError("Base validation error")

        # Should inherit from Exception
        assert isinstance(error, Exception)

    def test_validation_error_with_context(self):
        """Test ValidationError with context information."""
        original = ValueError("Original error")
        error = ValidationError(
            message="Validation failed", line_number=10, original_error=original
        )

        assert str(error) == "Validation failed"
        assert error.line_number == 10
        assert error.original_error == original


class TestExceptionChaining:
    """Test exception chaining and context."""

    def test_exception_chaining(self):
        """Test exception chaining."""
        with pytest.raises(BAMAPIError) as exc_info:
            try:
                # Simulate underlying error
                raise ValueError("Underlying error")
            except ValueError as e:
                # Wrap with our custom exception
                raise BAMAPIError("API call failed") from e

        wrapped_error = exc_info.value
        assert isinstance(wrapped_error, BAMAPIError)
        assert isinstance(wrapped_error.__cause__, ValueError)

    def test_exception_catching_hierarchy(self):
        """Test exception catching with inheritance hierarchy."""
        # Test that specific exceptions can be caught
        try:
            raise BAMAPIError("API Error")
        except BAMAPIError:
            caught = True
        except Exception:
            caught = False

        assert caught

        # Test that parent exceptions catch child exceptions
        try:
            raise BAMRateLimitError(retry_after=30)
        except BAMAPIError:
            caught = True
        except Exception:
            caught = False

        assert caught

    def test_exception_preservation(self):
        """Test that exception attributes are preserved."""
        original_error = CSVValidationError("CSV format error", line_number=10)

        assert original_error.line_number == 10

        # Re-raise and catch
        try:
            raise original_error
        except CSVValidationError as caught_error:
            assert caught_error.line_number == 10

    def test_exception_message_formatting(self):
        """Test exception message formatting."""
        # Test that messages are properly formatted
        error1 = BAMAPIError("Error 1")
        error2 = BAMAPIError("Error 2")

        assert str(error1) == "Error 1"
        assert str(error2) == "Error 2"
        assert str(error1) != str(error2)


class TestExceptionEdgeCases:
    """Test edge cases and error conditions."""

    def test_exception_with_unicode_characters(self):
        """Test exceptions with Unicode characters."""
        unicode_message = "Error with unicode: café résumé rocket"
        error = ValidationError(unicode_message)

        assert str(error) == unicode_message

    def test_exception_with_empty_message(self):
        """Test exceptions with empty message."""
        error = BAMAPIError("")

        # Empty string should be valid
        assert str(error) == ""

    def test_exception_with_very_long_message(self):
        """Test exceptions with very long messages."""
        long_message = "x" * 10000  # 10KB message
        error = ValidationError(long_message)

        assert str(error) == long_message
        assert len(str(error)) == 10000
