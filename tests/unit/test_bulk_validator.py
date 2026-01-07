import unittest
from unittest.mock import AsyncMock

from src.importer.models.csv_row import IP4NetworkRow
from src.importer.validation.validator import BulkValidator


class TestBulkValidator(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.validator = BulkValidator(self.client)

    async def test_validate_empty(self):
        report = await self.validator.validate([])
        self.assertTrue(report.is_valid)
        self.assertEqual(report.summary["checked"], 0)

    async def test_duplicate_cidr_found(self):
        # Setup row for creation
        row = IP4NetworkRow(
            row_id="1",
            object_type="ip4_network",
            action="create",
            config="TestConfig",
            cidr="10.0.0.0/24",
            name="TestNet",
        )

        # Mocks
        # 1. Config resolution
        self.client.get_configuration_by_name.return_value = {"id": 100, "name": "TestConfig"}
        # 2. Bulk network check (new pattern - uses client.get with filter)
        self.client.get.return_value = {
            "data": [{"id": 555, "range": "10.0.0.0/24"}]  # Network exists
        }

        # Run validation
        report = await self.validator.validate([row])

        # Verify
        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.errors[0].field, "cidr")
        self.assertIn("already exists", report.errors[0].message)

        # Verify config lookup was called
        self.client.get_configuration_by_name.assert_called_with("TestConfig")

    async def test_duplicate_cidr_not_found(self):
        # Setup row
        row = IP4NetworkRow(
            row_id="1",
            object_type="ip4_network",
            action="create",
            config="TestConfig",
            cidr="10.0.0.0/24",
            name="NewNet",
        )

        self.client.get_configuration_by_name.return_value = {"id": 100}
        # Bulk check returns empty (no matching networks)
        self.client.get.return_value = {"data": []}

        report = await self.validator.validate([row])

        self.assertTrue(report.is_valid)
        self.assertEqual(len(report.errors), 0)

    async def test_update_action_skipped(self):
        # Update action should NOT trigger duplicate check
        row = IP4NetworkRow(
            row_id="1",
            object_type="ip4_network",
            action="update",
            config="TestConfig",
            cidr="10.0.0.0/24",
            name="UpdateNet",
        )

        report = await self.validator.validate([row])

        self.assertTrue(report.is_valid)
        # Bulk check should not be called for update action
        self.client.get.assert_not_called()

    async def test_missing_config_warning(self):
        row = IP4NetworkRow(
            row_id="1",
            object_type="ip4_network",
            action="create",
            config="MissingConfig",
            cidr="10.0.0.0/24",
            name="TestNet",
        )
        # Simulate config not found
        self.client.get_configuration_by_name.side_effect = Exception("Not Found")

        report = await self.validator.validate([row])

        self.assertTrue(report.is_valid)  # Weights as Valid if no Errors (warnings don't fail)
        self.assertEqual(len(report.warnings), 1)
        self.assertIn("not found", report.warnings[0].message)


if __name__ == "__main__":
    unittest.main()
