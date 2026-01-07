"""Extended unit tests for Bulk Validator - covering critical missing scenarios.

This test file focuses on areas with low coverage:
- Block duplicate checking
- Zone duplicate checking
- View resolution
- Error handling edge cases
- Multiple config/view scenarios
"""

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.importer.models.csv_row import DNSZoneRow, IP4BlockRow, IP4NetworkRow
from src.importer.validation.validator import BulkValidator, ValidationReport


class TestBlockDuplicateChecking(unittest.IsolatedAsyncioTestCase):
    """Test block duplicate checking functionality."""

    def setUp(self):
        self.client = AsyncMock()
        self.validator = BulkValidator(self.client)

    async def test_duplicate_block_found(self):
        """Test detection of duplicate block."""
        row = IP4BlockRow(
            row_id="1",
            object_type="ip4_block",
            action="create",
            config="TestConfig",
            cidr="10.0.0.0/8",
            name="TestBlock",
        )

        # Mocks
        self.client.get_configuration_by_name.return_value = {"id": 100, "name": "TestConfig"}
        self.client.get.return_value = {
            "data": [{"id": 777, "range": "10.0.0.0/8"}]  # Block exists
        }

        report = await self.validator.validate([row])

        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.errors[0].field, "cidr")
        self.assertIn("already exists", report.errors[0].message)

    async def test_duplicate_block_not_found(self):
        """Test when block doesn't exist (valid case)."""
        row = IP4BlockRow(
            row_id="1",
            object_type="ip4_block",
            action="create",
            config="TestConfig",
            cidr="10.0.0.0/8",
            name="NewBlock",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get.return_value = {"data": []}

        report = await self.validator.validate([row])

        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.errors), 0)

    async def test_multiple_blocks_bulk_check(self):
        """Test bulk checking of multiple blocks in same config."""
        row1 = IP4BlockRow(
            row_id="1",
            object_type="ip4_block",
            action="create",
            config="TestConfig",
            cidr="10.0.0.0/8",
            name="Block1",
        )
        row2 = IP4BlockRow(
            row_id="2",
            object_type="ip4_block",
            action="create",
            config="TestConfig",
            cidr="172.16.0.0/12",
            name="Block2",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        # One block exists, one doesn't
        self.client.get.return_value = {
            "data": [{"id": 777, "range": "10.0.0.0/8"}]
        }

        report = await self.validator.validate([row1, row2])

        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.errors[0].row_id, "1")

    async def test_blocks_in_different_configs(self):
        """Test blocks in different configurations are checked separately."""
        row1 = IP4BlockRow(
            row_id="1",
            object_type="ip4_block",
            action="create",
            config="Config1",
            cidr="10.0.0.0/8",
            name="Block1",
        )
        row2 = IP4BlockRow(
            row_id="2",
            object_type="ip4_block",
            action="create",
            config="Config2",
            cidr="10.0.0.0/8",
            name="Block2",
        )

        # Different configs
        async def get_config(name):
            if name == "Config1":
                return {"id": 100, "name": "Config1"}
            return {"id": 200, "name": "Config2"}

        self.client.get_configuration_by_name.side_effect = get_config
        self.client.get.return_value = {"data": []}

        report = await self.validator.validate([row1, row2])

        self.assertTrue(report.is_valid)
        # Should make separate calls for each config
        self.assertEqual(self.client.get.call_count, 2)


class TestZoneDuplicateChecking(unittest.IsolatedAsyncioTestCase):
    """Test zone duplicate checking functionality."""

    def setUp(self):
        self.client = AsyncMock()
        self.validator = BulkValidator(self.client)

    async def test_duplicate_zone_found(self):
        """Test detection of duplicate zone."""
        row = DNSZoneRow(
            row_id="1",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="Internal",
            zone_name="example.com",
        )

        # Mocks
        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = {"id": 500}
        self.client.get.return_value = {
            "data": [{"id": 999, "name": "example.com"}]  # Zone exists
        }

        report = await self.validator.validate([row])

        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.errors[0].field, "zone_name")
        self.assertIn("already exists", report.errors[0].message)

    async def test_duplicate_zone_not_found(self):
        """Test when zone doesn't exist (valid case)."""
        row = DNSZoneRow(
            row_id="1",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="Internal",
            zone_name="newzone.com",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = {"id": 500}
        self.client.get.return_value = {"data": []}

        report = await self.validator.validate([row])

        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.errors), 0)

    async def test_multiple_zones_same_view(self):
        """Test bulk checking of multiple zones in same view."""
        row1 = DNSZoneRow(
            row_id="1",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="Internal",
            zone_name="example.com",
        )
        row2 = DNSZoneRow(
            row_id="2",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="Internal",
            zone_name="test.com",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = {"id": 500}
        # One zone exists
        self.client.get.return_value = {
            "data": [{"id": 999, "name": "example.com"}]
        }

        report = await self.validator.validate([row1, row2])

        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.errors[0].row_id, "1")

    async def test_zones_in_different_views(self):
        """Test zones in different views are checked separately."""
        row1 = DNSZoneRow(
            row_id="1",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="Internal",
            zone_name="example.com",
        )
        row2 = DNSZoneRow(
            row_id="2",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="External",
            zone_name="example.com",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}

        # Different views
        async def get_view(config_id, view_path):
            if view_path == "Internal":
                return {"id": 500}
            return {"id": 600}

        self.client.get_view_by_name_in_config.side_effect = get_view
        self.client.get.return_value = {"data": []}

        report = await self.validator.validate([row1, row2])

        self.assertTrue(report.is_valid)
        # Should make separate calls for each view
        self.assertEqual(self.client.get.call_count, 2)

    async def test_zone_with_missing_view(self):
        """Test zone validation when view doesn't exist."""
        row = DNSZoneRow(
            row_id="1",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="NonExistentView",
            zone_name="example.com",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = None

        report = await self.validator.validate([row])

        # Should be valid (view check is skipped, will be caught during import)
        self.assertTrue(report.is_valid)


class TestViewResolution(unittest.IsolatedAsyncioTestCase):
    """Test view resolution functionality."""

    def setUp(self):
        self.client = AsyncMock()
        self.validator = BulkValidator(self.client)

    async def test_view_resolution_success(self):
        """Test successful view resolution."""
        rows = [
            DNSZoneRow(
                row_id="1",
                object_type="dns_zone",
                action="create",
                config="TestConfig",
                view_path="Internal",
                zone_name="zone1.com",
            )
        ]

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = {"id": 500}
        self.client.get.return_value = {"data": []}

        await self.validator.validate(rows)

        # Verify view was resolved
        self.client.get_view_by_name_in_config.assert_called_once_with(100, "Internal")

    async def test_view_resolution_failure(self):
        """Test view resolution when view doesn't exist."""
        rows = [
            DNSZoneRow(
                row_id="1",
                object_type="dns_zone",
                action="create",
                config="TestConfig",
                view_path="NonExistent",
                zone_name="zone1.com",
            )
        ]

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.side_effect = Exception("Not found")

        # Should not crash
        report = await self.validator.validate(rows)
        self.assertTrue(report.is_valid)

    async def test_view_resolution_missing_config(self):
        """Test view resolution when config doesn't exist."""
        rows = [
            DNSZoneRow(
                row_id="1",
                object_type="dns_zone",
                action="create",
                config="NonExistent",
                view_path="Internal",
                zone_name="zone1.com",
            )
        ]

        self.client.get_configuration_by_name.side_effect = Exception("Not found")

        report = await self.validator.validate(rows)
        # Should be valid (no errors, view lookup skipped)
        self.assertTrue(report.is_valid)


class TestErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling and edge cases."""

    def setUp(self):
        self.client = AsyncMock()
        self.validator = BulkValidator(self.client)

    async def test_api_error_during_network_check(self):
        """Test graceful handling of API errors during network check."""
        row = IP4NetworkRow(
            row_id="1",
            object_type="ip4_network",
            action="create",
            config="TestConfig",
            cidr="10.0.0.0/24",
            name="TestNet",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get.side_effect = Exception("API Error")

        # Should not crash
        report = await self.validator.validate([row])
        # Error is logged but doesn't fail validation (graceful degradation)
        self.assertTrue(report.is_valid)

    async def test_api_error_during_block_check(self):
        """Test graceful handling of API errors during block check."""
        row = IP4BlockRow(
            row_id="1",
            object_type="ip4_block",
            action="create",
            config="TestConfig",
            cidr="10.0.0.0/8",
            name="TestBlock",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get.side_effect = Exception("API Error")

        report = await self.validator.validate([row])
        self.assertTrue(report.is_valid)

    async def test_zone_check_fallback_to_individual(self):
        """Test fallback to individual zone checks when bulk check fails."""
        row = DNSZoneRow(
            row_id="1",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="Internal",
            zone_name="example.com",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = {"id": 500}
        # Bulk check fails, fallback to individual
        self.client.get.side_effect = Exception("Bulk filter not supported")
        self.client.get_zone_by_fqdn.return_value = {"id": 999}  # Zone exists

        report = await self.validator.validate([row])

        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.errors), 1)
        self.client.get_zone_by_fqdn.assert_called_once()

    async def test_zone_check_fallback_zone_not_found(self):
        """Test fallback when zone check raises exception (zone doesn't exist)."""
        row = DNSZoneRow(
            row_id="1",
            object_type="dns_zone",
            action="create",
            config="TestConfig",
            view_path="Internal",
            zone_name="newzone.com",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = {"id": 500}
        self.client.get.side_effect = Exception("Bulk filter not supported")
        self.client.get_zone_by_fqdn.side_effect = Exception("404 Not Found")

        report = await self.validator.validate([row])

        # Should be valid (zone doesn't exist, which is good for create)
        self.assertTrue(report.is_valid)

    async def test_mixed_row_types(self):
        """Test validation with mixed row types."""
        rows = [
            IP4NetworkRow(
                row_id="1",
                object_type="ip4_network",
                action="create",
                config="TestConfig",
                cidr="10.0.0.0/24",
                name="Net1",
            ),
            IP4BlockRow(
                row_id="2",
                object_type="ip4_block",
                action="create",
                config="TestConfig",
                cidr="10.0.0.0/8",
                name="Block1",
            ),
            DNSZoneRow(
                row_id="3",
                object_type="dns_zone",
                action="create",
                config="TestConfig",
                view_path="Internal",
                zone_name="example.com",
            ),
        ]

        self.client.get_configuration_by_name.return_value = {"id": 100}
        self.client.get_view_by_name_in_config.return_value = {"id": 500}
        self.client.get.return_value = {"data": []}

        report = await self.validator.validate(rows)

        self.assertTrue(report.is_valid)
        # Should check both CIDR and zone
        self.assertGreaterEqual(self.client.get.call_count, 2)


class TestValidationReport(unittest.TestCase):
    """Test ValidationReport class."""

    def test_validation_report_is_valid(self):
        """Test is_valid property."""
        report = ValidationReport()
        self.assertTrue(report.is_valid)

        report.add_error("1", "cidr", "Duplicate")
        self.assertFalse(report.is_valid)

    def test_validation_report_add_error(self):
        """Test adding errors."""
        report = ValidationReport()
        report.add_error("1", "cidr", "Duplicate CIDR")

        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.summary["errors"], 1)
        self.assertEqual(report.errors[0].row_id, "1")
        self.assertEqual(report.errors[0].field, "cidr")

    def test_validation_report_add_warning(self):
        """Test adding warnings."""
        report = ValidationReport()
        report.add_warning("1", "config", "Config not found")

        self.assertEqual(len(report.warnings), 1)
        self.assertEqual(report.summary["warnings"], 1)
        self.assertTrue(report.is_valid)  # Warnings don't affect validity

    def test_validation_error_str(self):
        """Test ValidationError string representation."""
        from src.importer.validation.validator import ValidationError

        error = ValidationError("1", "cidr", "Duplicate", "ERROR")
        str_repr = str(error)

        self.assertIn("ERROR", str_repr)
        self.assertIn("Row 1", str_repr)
        self.assertIn("cidr", str_repr)
        self.assertIn("Duplicate", str_repr)


if __name__ == "__main__":
    unittest.main()
