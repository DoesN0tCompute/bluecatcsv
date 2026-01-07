"""Unit tests for Diff Engine."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.importer.config import PolicyConfig
from src.importer.core.diff_engine import DiffEngine
from src.importer.models.csv_row import IP4AddressRow, IP4NetworkRow
from src.importer.models.operations import OperationType
from src.importer.models.state import ResourceState


class TestDiffEngine:
    """Test DiffEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.policy = PolicyConfig()
        self.diff_engine = DiffEngine(self.policy)

    # Test compute_diff with create action
    def test_compute_diff_create_resource_not_exists(self):
        """Test CREATE when resource doesn't exist."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            name="server1",
        )
        current = None

        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.CREATE
        assert result.resource_id is None
        assert result.conflict_detected is False
        assert result.field_changes == {}

    def test_compute_diff_create_resource_exists_create_only_mode(self):
        """Test CREATE when resource exists in create_only mode."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            name="server1",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1-old"},
        )

        self.policy.update_mode = "create_only"
        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.NOOP
        assert result.resource_id == 123
        assert "Resource already exists" in result.conflict_reason

    def test_compute_diff_create_resource_exists_with_changes(self):
        """Test CREATE when resource exists with changes in upsert mode."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            name="server1-new",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1-old"},
        )

        self.policy.update_mode = "upsert"
        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.UPDATE
        assert result.resource_id == 123
        assert "name" in result.field_changes
        assert result.field_changes["name"].old_value == "server1-old"
        assert result.field_changes["name"].new_value == "server1-new"

    # Test compute_diff with update action
    def test_compute_diff_update_resource_exists_with_changes(self):
        """Test UPDATE when resource exists with changes."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="update",
            config="Default",
            address="10.1.0.5",
            name="server1-new",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1-old"},
        )

        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.UPDATE
        assert result.resource_id == 123
        assert "name" in result.field_changes
        assert result.field_changes["name"].old_value == "server1-old"
        assert result.field_changes["name"].new_value == "server1-new"

    def test_compute_diff_update_resource_exists_no_changes(self):
        """Test UPDATE when resource exists with no changes."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="update",
            config="Default",
            address="10.1.0.5",
            name="server1",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1"},
        )

        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.NOOP
        assert result.resource_id == 123
        assert "No changes needed" in result.conflict_reason

    def test_compute_diff_update_resource_not_exists_upsert_mode(self):
        """Test UPDATE when resource doesn't exist in upsert mode."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="update",
            config="Default",
            address="10.1.0.5",
            name="server1",
        )
        current = None

        self.policy.update_mode = "upsert"
        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.CREATE
        assert result.resource_id is None
        assert "creating due to upsert mode" in result.conflict_reason

    def test_compute_diff_update_resource_not_exists_strict_mode(self):
        """Test UPDATE when resource doesn't exist in strict mode."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="update",
            config="Default",
            address="10.1.0.5",
            name="server1",
        )
        current = None

        self.policy.update_mode = "strict"
        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.NOOP
        assert result.resource_id is None
        assert result.conflict_detected is True
        assert "resource doesn't exist" in result.conflict_reason

    # Test compute_diff with delete action
    def test_compute_diff_delete_resource_exists(self):
        """Test DELETE when resource exists."""
        # Disable safe mode for this test
        self.policy.safe_mode = False

        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="delete",
            config="Default",
            address="10.1.0.5",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1"},
        )

        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.DELETE
        assert result.resource_id == 123

    def test_compute_diff_delete_resource_exists_safe_mode(self):
        """Test DELETE when resource exists in safe mode."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="delete",
            config="Default",
            address="10.1.0.5",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1"},
        )

        self.policy.safe_mode = True
        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.NOOP
        assert result.resource_id == 123
        assert "Safe mode" in result.conflict_reason
        assert result.metadata["safe_mode_prevented_delete"] is True

    def test_compute_diff_delete_resource_not_exists(self):
        """Test DELETE when resource doesn't exist."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="delete",
            config="Default",
            address="10.1.0.5",
        )
        current = None

        result = self.diff_engine.compute_diff(desired, current)

        assert result.operation == OperationType.NOOP
        assert result.resource_id is None
        assert "Resource doesn't exist" in result.conflict_reason

    # Test error handling
    def test_compute_diff_unknown_action(self):
        """Test error handling for unknown action."""
        # Pydantic validates the action field during object creation
        # This test verifies that invalid actions are rejected
        with pytest.raises(PydanticValidationError) as exc_info:
            IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="invalid_action",
                config="Default",
                address="10.1.0.5",
            )

        assert "Input should be 'create', 'update' or 'delete'" in str(exc_info.value)

    # Test field change detection
    def test_compute_field_changes_multiple_fields(self):
        """Test field change detection with multiple fields."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="update",
            config="Default",
            address="10.1.0.5",
            name="server1-new",
            mac="11:22:33:44:55:66",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={
                "address": "10.1.0.5",
                "name": "server1-old",
                "mac": "00:11:22:33:44:55",
                "extra_field": "value",
            },
        )

        result = self.diff_engine.compute_diff(desired, current)

        assert len(result.field_changes) == 2
        assert "name" in result.field_changes
        assert "mac" in result.field_changes
        assert result.field_changes["name"].old_value == "server1-old"
        assert result.field_changes["name"].new_value == "server1-new"
        assert result.field_changes["mac"].old_value == "00:11:22:33:44:55"
        assert result.field_changes["mac"].new_value == "11:22:33:44:55:66"

    def test_compute_field_changes_none_values_ignored(self):
        """Test that None values in desired fields are ignored."""
        desired = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="update",
            config="Default",
            address="10.1.0.5",
            name=None,  # Should be ignored
            mac="11:22:33:44:55:66",
        )
        current = ResourceState(
            id=123,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1", "mac": "00:11:22:33:44:55"},
        )

        result = self.diff_engine.compute_diff(desired, current)

        assert len(result.field_changes) == 1
        assert "mac" in result.field_changes
        assert "name" not in result.field_changes

    # Test value normalization
    @pytest.mark.parametrize(
        ["input_value", "expected"],
        [
            ("  test  ", "test"),  # Whitespace trimming
            ("", None),  # Empty string
            ("   ", None),  # Whitespace only string
            ("test", "test"),  # Normal string
            (None, None),  # None value
            (123, 123),  # Number
        ],
    )
    def test_normalize_value(self, input_value, expected):
        """Test value normalization."""
        result = self.diff_engine._normalize_value(input_value)
        assert result == expected

    # Test orphan detection
    def test_detect_orphans_disabled(self):
        """Test orphan detection when disabled."""
        desired = [
            IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="10.1.0.5",
            )
        ]
        current = [ResourceState(id=100, type="IP4Address", properties={"address": "10.1.0.6"})]
        scope = {"config": "Default"}

        self.policy.enable_orphan_detection = False
        orphans = self.diff_engine.detect_orphans(desired, current, scope)

        assert len(orphans) == 0

    def test_detect_orphans_enabled(self):
        """Test orphan detection when enabled."""
        desired = [
            IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="10.1.0.5",
            )
        ]
        current = [
            ResourceState(id=100, type="IP4Address", properties={"address": "10.1.0.6"}),
            ResourceState(id=101, type="IP4Address", properties={"address": "10.1.0.7"}),
        ]
        scope = {"config": "Default"}

        self.policy.enable_orphan_detection = True
        self.policy.safe_mode = False
        orphans = self.diff_engine.detect_orphans(desired, current, scope)

        assert len(orphans) == 2
        assert all(orphan.operation == OperationType.ORPHAN for orphan in orphans)
        assert orphans[0].resource_id == 100
        assert orphans[1].resource_id == 101

    def test_detect_orphans_safe_mode(self):
        """Test orphan detection in safe mode."""
        desired = [
            IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="10.1.0.5",
            )
        ]
        current = [ResourceState(id=100, type="IP4Address", properties={"address": "10.1.0.6"})]
        scope = {"config": "Default"}

        self.policy.enable_orphan_detection = True
        self.policy.safe_mode = True
        orphans = self.diff_engine.detect_orphans(desired, current, scope)

        assert len(orphans) == 1
        assert orphans[0].operation == OperationType.NOOP
        assert orphans[0].metadata["orphan_safe_mode"] is True

    def test_detect_orphans_with_matching_ids(self):
        """Test that resources with matching IDs are not considered orphans."""
        desired = [
            IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="10.1.0.5",
                bam_id=100,
            )
        ]
        current = [
            ResourceState(id=100, type="IP4Address", properties={"address": "10.1.0.6"}),
            ResourceState(id=101, type="IP4Address", properties={"address": "10.1.0.7"}),
        ]
        scope = {"config": "Default"}

        self.policy.enable_orphan_detection = True
        self.policy.safe_mode = False
        orphans = self.diff_engine.detect_orphans(desired, current, scope)

        assert len(orphans) == 1
        assert orphans[0].resource_id == 101  # Only the non-matching one

    def test_detect_orphans_with_matching_keys(self):
        """Test that resources with matching unique keys are not considered orphans."""
        desired = [
            IP4AddressRow(
                row_id=1,
                object_type="ip4_address",
                action="create",
                config="Default",
                address="10.1.0.5",
            )
        ]
        current = [
            ResourceState(id=100, type="IP4Address", properties={"address": "10.1.0.5"}),
            ResourceState(id=101, type="IP4Address", properties={"address": "10.1.0.7"}),
        ]
        scope = {"config": "Default"}

        self.policy.enable_orphan_detection = True
        self.policy.safe_mode = False
        orphans = self.diff_engine.detect_orphans(desired, current, scope)

        assert len(orphans) == 1
        assert orphans[0].resource_id == 101  # Only the non-matching one

    # Test unique key extraction
    def test_get_unique_key_from_csv_address(self):
        """Test unique key extraction for address from CSV."""
        row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
        )

        key = self.diff_engine._get_unique_key_from_csv(row)
        assert key == "address:10.1.0.5"

    def test_get_unique_key_from_csv_network(self):
        """Test unique key extraction for network from CSV."""
        row = IP4NetworkRow(
            row_id=1,
            object_type="ip4_network",
            action="create",
            config="Default",
            cidr="10.1.0.0/24",
            name="test_network",  # Fixed
        )

        key = self.diff_engine._get_unique_key_from_csv(row)
        assert key == "cidr:10.1.0.0/24"

    def test_get_unique_key_from_csv_with_bam_id(self):
        """Test unique key extraction fallback to BAM ID."""
        row = IP4AddressRow(
            row_id=1,
            object_type="ip4_address",
            action="create",
            config="Default",
            address="10.1.0.5",
            bam_id=123,
        )

        # Mock the address attribute to not exist
        delattr(row, "address")
        key = self.diff_engine._get_unique_key_from_csv(row)
        assert key == "id:123"

    def test_get_unique_key_from_state_address(self):
        """Test unique key extraction for address from state."""
        state = ResourceState(
            id=100,
            type="IP4Address",
            properties={"address": "10.1.0.5", "name": "server1"},
        )

        key = self.diff_engine._get_unique_key_from_state(state)
        assert key == "address:10.1.0.5"

    def test_get_unique_key_from_state_network(self):
        """Test unique key extraction for network from state."""
        state = ResourceState(
            id=100,
            type="IP4Network",
            properties={"CIDR": "10.1.0.0/24", "name": "network1"},
        )

        key = self.diff_engine._get_unique_key_from_state(state)
        assert key == "cidr:10.1.0.0/24"

    def test_get_unique_key_from_state_fallback_to_id(self):
        """Test unique key extraction fallback to ID."""
        state = ResourceState(
            id=100,
            type="UnknownType",
            properties={"name": "resource1"},
        )

        key = self.diff_engine._get_unique_key_from_state(state)
        assert key == "id:100"
