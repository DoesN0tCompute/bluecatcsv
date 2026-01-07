"""Unit tests for access right functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.importer.execution.handlers import (
    AccessRightHandler,
    get_handler,
)
from src.importer.models.csv_row import AccessRightRow
from src.importer.models.payloads import (
    AccessOverride,
    AccessRightPayload,
    AccessRightUpdatePayload,
    ResourceRef,
    UserScopeRef,
)


class TestAccessRightRow:
    """Test AccessRightRow model validation."""

    def test_basic_user_access_right(self):
        """Test basic user access right creation."""
        row = AccessRightRow(
            row_id=1,
            object_type="access_right",
            action="create",
            user_type="user",
            user_name="operator",
            default_access_level="VIEW",
        )

        assert row.row_id == 1
        assert row.object_type == "access_right"
        assert row.user_type == "user"
        assert row.user_name == "operator"
        assert row.default_access_level == "VIEW"
        assert row.deployments_allowed is False
        assert row.workflow_level == "NONE"

    def test_group_access_right_with_resource(self):
        """Test group access right with resource specification."""
        row = AccessRightRow(
            row_id=2,
            object_type="access_right",
            action="create",
            user_type="group",
            user_name="NetworkAdmins",
            resource_type="Configuration",
            resource_path="Production",
            default_access_level="ADD",
            deployments_allowed=True,
            workflow_level="APPROVE",
        )

        assert row.user_type == "group"
        assert row.user_name == "NetworkAdmins"
        assert row.resource_type == "Configuration"
        assert row.resource_path == "Production"
        assert row.default_access_level == "ADD"
        assert row.deployments_allowed is True
        assert row.workflow_level == "APPROVE"

    def test_access_right_with_overrides(self):
        """Test access right with access overrides."""
        row = AccessRightRow(
            row_id=3,
            object_type="access_right",
            action="create",
            user_type="user",
            user_name="developer",
            default_access_level="VIEW",
            access_overrides="IPv4Address:FULL|HostRecord:ADD",
        )

        overrides = row.get_access_overrides_list()
        assert len(overrides) == 2
        assert overrides[0] == {"resourceType": "IPv4Address", "accessLevel": "FULL"}
        assert overrides[1] == {"resourceType": "HostRecord", "accessLevel": "ADD"}

    def test_access_right_all_deployment_options(self):
        """Test access right with all deployment options enabled."""
        row = AccessRightRow(
            row_id=4,
            object_type="access_right",
            action="create",
            user_type="user",
            user_name="admin",
            default_access_level="FULL",
            deployments_allowed=True,
            quick_deployments_allowed=True,
            selective_deployments_allowed=True,
            workflow_level="APPROVE",
        )

        assert row.deployments_allowed is True
        assert row.quick_deployments_allowed is True
        assert row.selective_deployments_allowed is True

    def test_access_level_case_normalization(self):
        """Test that access level is normalized to uppercase."""
        row = AccessRightRow(
            row_id=1,
            object_type="access_right",
            action="create",
            user_type="user",
            user_name="test",
            default_access_level="view",  # lowercase
        )

        assert row.default_access_level == "VIEW"

    def test_user_type_case_normalization(self):
        """Test that user type is normalized to lowercase."""
        row = AccessRightRow(
            row_id=1,
            object_type="access_right",
            action="create",
            user_type="USER",  # uppercase
            user_name="test",
            default_access_level="VIEW",
        )

        assert row.user_type == "user"

    def test_workflow_level_case_normalization(self):
        """Test that workflow level is normalized to uppercase."""
        row = AccessRightRow(
            row_id=1,
            object_type="access_right",
            action="create",
            user_type="user",
            user_name="test",
            default_access_level="VIEW",
            workflow_level="approve",  # lowercase
        )

        assert row.workflow_level == "APPROVE"

    def test_invalid_user_type(self):
        """Test that invalid user type is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AccessRightRow(
                row_id=1,
                object_type="access_right",
                action="create",
                user_type="invalid",
                user_name="test",
                default_access_level="VIEW",
            )

        assert "user_type" in str(exc_info.value)

    def test_invalid_access_level(self):
        """Test that invalid access level is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AccessRightRow(
                row_id=1,
                object_type="access_right",
                action="create",
                user_type="user",
                user_name="test",
                default_access_level="INVALID",
            )

        assert "default_access_level" in str(exc_info.value)

    def test_invalid_workflow_level(self):
        """Test that invalid workflow level is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            AccessRightRow(
                row_id=1,
                object_type="access_right",
                action="create",
                user_type="user",
                user_name="test",
                default_access_level="VIEW",
                workflow_level="INVALID",
            )

        assert "workflow_level" in str(exc_info.value)

    def test_empty_access_overrides(self):
        """Test that empty access overrides returns empty list."""
        row = AccessRightRow(
            row_id=1,
            object_type="access_right",
            action="create",
            user_type="user",
            user_name="test",
            default_access_level="VIEW",
            access_overrides=None,
        )

        assert row.get_access_overrides_list() == []

    def test_whitespace_handling(self):
        """Test that whitespace is properly stripped."""
        row = AccessRightRow(
            row_id=1,
            object_type="access_right",
            action="create",
            user_type="  user  ",
            user_name="  operator  ",
            default_access_level="  VIEW  ",
        )

        assert row.user_type == "user"
        assert row.user_name == "operator"
        assert row.default_access_level == "VIEW"


class TestAccessRightPayloads:
    """Test access right payload models."""

    def test_user_scope_ref_user(self):
        """Test UserScopeRef for user."""
        ref = UserScopeRef(type="User", id=123)
        assert ref.type == "User"
        assert ref.id == 123

    def test_user_scope_ref_group(self):
        """Test UserScopeRef for group."""
        ref = UserScopeRef(type="UserGroup", id=456)
        assert ref.type == "UserGroup"
        assert ref.id == 456

    def test_resource_ref(self):
        """Test ResourceRef model."""
        ref = ResourceRef(type="Configuration", id=789)
        assert ref.type == "Configuration"
        assert ref.id == 789

    def test_access_override(self):
        """Test AccessOverride model."""
        override = AccessOverride(resourceType="IPv4Address", accessLevel="FULL")
        assert override.resourceType == "IPv4Address"
        assert override.accessLevel == "FULL"

    def test_access_right_payload_minimal(self):
        """Test minimal AccessRightPayload."""
        payload = AccessRightPayload(
            userScope=UserScopeRef(type="User", id=123),
            defaultAccessLevel="VIEW",
        )

        assert payload.type == "AccessRight"
        assert payload.userScope.id == 123
        assert payload.defaultAccessLevel == "VIEW"
        assert payload.deploymentsAllowed is False
        assert payload.resource is None
        assert payload.accessOverrides == []

    def test_access_right_payload_full(self):
        """Test full AccessRightPayload with all fields."""
        payload = AccessRightPayload(
            userScope=UserScopeRef(type="UserGroup", id=456),
            resource=ResourceRef(type="Configuration", id=789),
            defaultAccessLevel="ADD",
            deploymentsAllowed=True,
            quickDeploymentsAllowed=True,
            selectiveDeploymentsAllowed=True,
            workflowLevel="APPROVE",
            accessOverrides=[AccessOverride(resourceType="IPv4Address", accessLevel="FULL")],
        )

        assert payload.resource.id == 789
        assert payload.deploymentsAllowed is True
        assert payload.workflowLevel == "APPROVE"
        assert len(payload.accessOverrides) == 1

    def test_access_right_update_payload(self):
        """Test AccessRightUpdatePayload."""
        payload = AccessRightUpdatePayload(
            defaultAccessLevel="CHANGE",
            deploymentsAllowed=True,
            quickDeploymentsAllowed=False,
            selectiveDeploymentsAllowed=True,
            workflowLevel="RECOMMEND",
            accessOverrides=[],
        )

        assert payload.defaultAccessLevel == "CHANGE"
        assert payload.workflowLevel == "RECOMMEND"


class TestAccessRightHandler:
    """Test AccessRightHandler functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock BAM client."""
        client = AsyncMock()
        client.get_user_by_name = AsyncMock(return_value={"id": 100, "name": "operator"})
        client.get_group_by_name = AsyncMock(return_value={"id": 200, "name": "Admins"})
        client.create_access_right = AsyncMock(return_value={"id": 999})
        client.update_access_right = AsyncMock(return_value={"id": 999})
        client.delete_access_right = AsyncMock(return_value=None)
        return client

    @pytest.fixture
    def user_operation(self):
        """Create a mock operation for user access right."""
        operation = MagicMock()
        operation.row_id = 1
        operation.object_type = "access_right"
        operation.payload = {}
        operation.csv_row = MagicMock()
        operation.csv_row.user_type = "user"
        operation.csv_row.user_name = "operator"
        operation.csv_row.default_access_level = "VIEW"
        operation.csv_row.deployments_allowed = False
        operation.csv_row.quick_deployments_allowed = False
        operation.csv_row.selective_deployments_allowed = False
        operation.csv_row.workflow_level = "NONE"
        operation.csv_row.get_access_overrides_list = MagicMock(return_value=[])
        return operation

    @pytest.fixture
    def group_operation(self):
        """Create a mock operation for group access right."""
        operation = MagicMock()
        operation.row_id = 2
        operation.object_type = "access_right"
        operation.payload = {"resource_type": "Configuration", "resource_id": 500}
        operation.csv_row = MagicMock()
        operation.csv_row.user_type = "group"
        operation.csv_row.user_name = "Admins"
        operation.csv_row.default_access_level = "ADD"
        operation.csv_row.deployments_allowed = True
        operation.csv_row.quick_deployments_allowed = True
        operation.csv_row.selective_deployments_allowed = False
        operation.csv_row.workflow_level = "APPROVE"
        operation.csv_row.get_access_overrides_list = MagicMock(return_value=[])
        return operation

    @pytest.mark.asyncio
    async def test_create_user_access_right(self, mock_client, user_operation):
        """Test creating access right for a user."""
        handler = AccessRightHandler()

        result = await handler.create(mock_client, user_operation)

        assert result["id"] == 999
        mock_client.get_user_by_name.assert_called_once_with("operator")
        mock_client.create_access_right.assert_called_once_with(
            user_scope_type="User",
            user_scope_id=100,
            default_access_level="VIEW",
            resource_type=None,
            resource_id=None,
            deployments_allowed=False,
            quick_deployments_allowed=False,
            selective_deployments_allowed=False,
            workflow_level="NONE",
            access_overrides=[],
        )

    @pytest.mark.asyncio
    async def test_create_group_access_right(self, mock_client, group_operation):
        """Test creating access right for a group."""
        handler = AccessRightHandler()

        result = await handler.create(mock_client, group_operation)

        assert result["id"] == 999
        mock_client.get_group_by_name.assert_called_once_with("Admins")
        mock_client.create_access_right.assert_called_once_with(
            user_scope_type="UserGroup",
            user_scope_id=200,
            default_access_level="ADD",
            resource_type="Configuration",
            resource_id=500,
            deployments_allowed=True,
            quick_deployments_allowed=True,
            selective_deployments_allowed=False,
            workflow_level="APPROVE",
            access_overrides=[],
        )

    @pytest.mark.asyncio
    async def test_create_user_not_found(self, mock_client, user_operation):
        """Test error when user is not found."""
        mock_client.get_user_by_name.return_value = None
        handler = AccessRightHandler()

        with pytest.raises(ValueError, match="User 'operator' not found"):
            await handler.create(mock_client, user_operation)

    @pytest.mark.asyncio
    async def test_create_group_not_found(self, mock_client, group_operation):
        """Test error when group is not found."""
        mock_client.get_group_by_name.return_value = None
        handler = AccessRightHandler()

        with pytest.raises(ValueError, match="Group 'Admins' not found"):
            await handler.create(mock_client, group_operation)

    @pytest.mark.asyncio
    async def test_create_missing_user_type(self, mock_client, user_operation):
        """Test error when user_type is missing."""
        user_operation.csv_row.user_type = None
        handler = AccessRightHandler()

        with pytest.raises(ValueError, match="user_type and user_name are required"):
            await handler.create(mock_client, user_operation)

    @pytest.mark.asyncio
    async def test_create_invalid_user_type(self, mock_client, user_operation):
        """Test error when user_type is invalid."""
        user_operation.csv_row.user_type = "invalid"
        handler = AccessRightHandler()

        with pytest.raises(ValueError, match="Invalid user_type"):
            await handler.create(mock_client, user_operation)

    @pytest.mark.asyncio
    async def test_update_access_right(self, mock_client, user_operation):
        """Test updating access right."""
        user_operation.payload = {"access_right_id": 999}
        handler = AccessRightHandler()

        result = await handler.update(mock_client, user_operation)

        assert result["id"] == 999
        mock_client.update_access_right.assert_called_once_with(
            access_right_id=999,
            default_access_level="VIEW",
            deployments_allowed=False,
            quick_deployments_allowed=False,
            selective_deployments_allowed=False,
            workflow_level="NONE",
            access_overrides=[],
        )

    @pytest.mark.asyncio
    async def test_delete_access_right(self, mock_client, user_operation):
        """Test deleting access right."""
        user_operation.payload = {"access_right_id": 999}
        handler = AccessRightHandler()

        await handler.delete(mock_client, user_operation)

        mock_client.delete_access_right.assert_called_once_with(999)


class TestAccessRightHandlerRegistry:
    """Test access right handler registration."""

    def test_handler_registered(self):
        """Test that access_right handler is registered."""
        handler = get_handler("access_right")
        assert isinstance(handler, AccessRightHandler)
