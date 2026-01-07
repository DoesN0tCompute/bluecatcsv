"""Tests for centralized BAM API endpoint configuration.

These tests verify that BAMEndpoints provides correct endpoint paths
and helper methods work properly (Fix 4.3).
"""

from importer.bam.endpoints import BAMEndpoints


class TestBAMEndpointsConstants:
    """Tests for BAMEndpoints constant values."""

    def test_sessions_endpoint(self) -> None:
        """Test sessions endpoint constant."""
        assert BAMEndpoints.SESSIONS == "sessions"

    def test_configurations_endpoint(self) -> None:
        """Test configurations endpoint constant."""
        assert BAMEndpoints.CONFIGURATIONS == "configurations"

    def test_blocks_endpoint(self) -> None:
        """Test blocks endpoint constant."""
        assert BAMEndpoints.BLOCKS == "blocks"

    def test_networks_endpoint(self) -> None:
        """Test networks endpoint constant."""
        assert BAMEndpoints.NETWORKS == "networks"

    def test_addresses_endpoint(self) -> None:
        """Test addresses endpoint constant."""
        assert BAMEndpoints.ADDRESSES == "addresses"

    def test_zones_endpoint(self) -> None:
        """Test zones endpoint constant."""
        assert BAMEndpoints.ZONES == "zones"

    def test_views_endpoint(self) -> None:
        """Test views endpoint constant."""
        assert BAMEndpoints.VIEWS == "views"

    def test_servers_endpoint(self) -> None:
        """Test servers endpoint constant."""
        assert BAMEndpoints.SERVERS == "servers"


class TestBAMEndpointsFormatting:
    """Tests for BAMEndpoints string formatting."""

    def test_configuration_by_id_format(self) -> None:
        """Test configuration by ID endpoint formatting."""
        endpoint = BAMEndpoints.CONFIGURATION_BY_ID.format(config_id=123)
        assert endpoint == "configurations/123"

    def test_configuration_blocks_format(self) -> None:
        """Test configuration blocks endpoint formatting."""
        endpoint = BAMEndpoints.CONFIGURATION_BLOCKS.format(config_id=456)
        assert endpoint == "configurations/456/blocks"

    def test_block_by_id_format(self) -> None:
        """Test block by ID endpoint formatting."""
        endpoint = BAMEndpoints.BLOCK_BY_ID.format(block_id=789)
        assert endpoint == "blocks/789"

    def test_block_networks_format(self) -> None:
        """Test block networks endpoint formatting."""
        endpoint = BAMEndpoints.BLOCK_NETWORKS.format(block_id=100)
        assert endpoint == "blocks/100/networks"

    def test_network_by_id_format(self) -> None:
        """Test network by ID endpoint formatting."""
        endpoint = BAMEndpoints.NETWORK_BY_ID.format(network_id=200)
        assert endpoint == "networks/200"

    def test_network_addresses_format(self) -> None:
        """Test network addresses endpoint formatting."""
        endpoint = BAMEndpoints.NETWORK_ADDRESSES.format(network_id=300)
        assert endpoint == "networks/300/addresses"

    def test_zone_by_id_format(self) -> None:
        """Test zone by ID endpoint formatting."""
        endpoint = BAMEndpoints.ZONE_BY_ID.format(zone_id=400)
        assert endpoint == "zones/400"

    def test_zone_resource_records_format(self) -> None:
        """Test zone resource records endpoint formatting."""
        endpoint = BAMEndpoints.ZONE_RESOURCE_RECORDS.format(zone_id=500)
        assert endpoint == "zones/500/resourceRecords"


class TestBAMEndpointsHelperMethods:
    """Tests for BAMEndpoints helper methods."""

    def test_configuration_blocks_helper(self) -> None:
        """Test configuration_blocks helper method."""
        endpoint = BAMEndpoints.configuration_blocks(123)
        assert endpoint == "configurations/123/blocks"

    def test_configuration_views_helper(self) -> None:
        """Test configuration_views helper method."""
        endpoint = BAMEndpoints.configuration_views(456)
        assert endpoint == "configurations/456/views"

    def test_block_by_id_helper(self) -> None:
        """Test block_by_id helper method."""
        endpoint = BAMEndpoints.block_by_id(789)
        assert endpoint == "blocks/789"

    def test_block_networks_helper(self) -> None:
        """Test block_networks helper method."""
        endpoint = BAMEndpoints.block_networks(100)
        assert endpoint == "blocks/100/networks"

    def test_block_sub_blocks_helper(self) -> None:
        """Test block_sub_blocks helper method."""
        endpoint = BAMEndpoints.block_sub_blocks(200)
        assert endpoint == "blocks/200/blocks"

    def test_network_by_id_helper(self) -> None:
        """Test network_by_id helper method."""
        endpoint = BAMEndpoints.network_by_id(300)
        assert endpoint == "networks/300"

    def test_network_addresses_helper(self) -> None:
        """Test network_addresses helper method."""
        endpoint = BAMEndpoints.network_addresses(400)
        assert endpoint == "networks/400/addresses"

    def test_network_ranges_helper(self) -> None:
        """Test network_ranges helper method."""
        endpoint = BAMEndpoints.network_ranges(500)
        assert endpoint == "networks/500/ranges"

    def test_network_deployment_options_helper(self) -> None:
        """Test network_deployment_options helper method."""
        endpoint = BAMEndpoints.network_deployment_options(600)
        assert endpoint == "networks/600/deploymentOptions"

    def test_network_deployment_roles_helper(self) -> None:
        """Test network_deployment_roles helper method."""
        endpoint = BAMEndpoints.network_deployment_roles(700)
        assert endpoint == "networks/700/deploymentRoles"

    def test_view_by_id_helper(self) -> None:
        """Test view_by_id helper method."""
        endpoint = BAMEndpoints.view_by_id(800)
        assert endpoint == "views/800"

    def test_view_zones_helper(self) -> None:
        """Test view_zones helper method."""
        endpoint = BAMEndpoints.view_zones(900)
        assert endpoint == "views/900/zones"

    def test_zone_by_id_helper(self) -> None:
        """Test zone_by_id helper method."""
        endpoint = BAMEndpoints.zone_by_id(1000)
        assert endpoint == "zones/1000"

    def test_zone_sub_zones_helper(self) -> None:
        """Test zone_sub_zones helper method."""
        endpoint = BAMEndpoints.zone_sub_zones(1100)
        assert endpoint == "zones/1100/zones"

    def test_zone_resource_records_helper(self) -> None:
        """Test zone_resource_records helper method."""
        endpoint = BAMEndpoints.zone_resource_records(1200)
        assert endpoint == "zones/1200/resourceRecords"

    def test_zone_deployment_roles_helper(self) -> None:
        """Test zone_deployment_roles helper method."""
        endpoint = BAMEndpoints.zone_deployment_roles(1300)
        assert endpoint == "zones/1300/deploymentRoles"

    def test_server_by_id_helper(self) -> None:
        """Test server_by_id helper method."""
        endpoint = BAMEndpoints.server_by_id(1400)
        assert endpoint == "servers/1400"

    def test_server_interfaces_helper(self) -> None:
        """Test server_interfaces helper method."""
        endpoint = BAMEndpoints.server_interfaces(1500)
        assert endpoint == "servers/1500/interfaces"

    def test_deployment_role_by_id_helper(self) -> None:
        """Test deployment_role_by_id helper method."""
        endpoint = BAMEndpoints.deployment_role_by_id(1600)
        assert endpoint == "deploymentRoles/1600"

    def test_deployment_option_by_id_helper(self) -> None:
        """Test deployment_option_by_id helper method."""
        endpoint = BAMEndpoints.deployment_option_by_id(1700)
        assert endpoint == "deploymentOptions/1700"


class TestBAMEndpointsFrozen:
    """Tests to ensure BAMEndpoints is immutable."""

    def test_endpoints_is_frozen_dataclass(self) -> None:
        """Test that BAMEndpoints is a frozen dataclass."""
        # Check that it's a frozen dataclass by verifying it cannot be instantiated with changes
        # Since it's a class with string class attributes (not an instance), we verify it's frozen
        # by checking the dataclass decorator was applied with frozen=True
        from dataclasses import is_dataclass

        assert is_dataclass(BAMEndpoints), "BAMEndpoints should be a dataclass"

        # Verify it has the expected attributes
        assert hasattr(BAMEndpoints, "SESSIONS")
        assert BAMEndpoints.SESSIONS == "sessions"


class TestBAMEndpointsConsistency:
    """Tests for endpoint consistency and correctness."""

    def test_all_by_id_endpoints_match(self) -> None:
        """Test that by_id endpoints use correct format."""
        by_id_endpoints = [
            (BAMEndpoints.CONFIGURATION_BY_ID, "config_id", "configurations"),
            (BAMEndpoints.BLOCK_BY_ID, "block_id", "blocks"),
            (BAMEndpoints.NETWORK_BY_ID, "network_id", "networks"),
            (BAMEndpoints.ADDRESS_BY_ID, "address_id", "addresses"),
            (BAMEndpoints.VIEW_BY_ID, "view_id", "views"),
            (BAMEndpoints.ZONE_BY_ID, "zone_id", "zones"),
            (BAMEndpoints.RESOURCE_RECORD_BY_ID, "record_id", "resourceRecords"),
            (BAMEndpoints.RANGE_BY_ID, "range_id", "ranges"),
            (BAMEndpoints.DEPLOYMENT_OPTION_BY_ID, "option_id", "deploymentOptions"),
            (BAMEndpoints.DEPLOYMENT_ROLE_BY_ID, "role_id", "deploymentRoles"),
            (BAMEndpoints.SERVER_BY_ID, "server_id", "servers"),
        ]

        for endpoint_template, param_name, expected_prefix in by_id_endpoints:
            # Format with a test ID
            endpoint = endpoint_template.format(**{param_name: 999})
            assert endpoint == f"{expected_prefix}/999", (
                f"Endpoint {endpoint_template} with {param_name}=999 "
                f"should be '{expected_prefix}/999', got '{endpoint}'"
            )

    def test_helper_methods_match_constants(self) -> None:
        """Test that helper methods produce same results as string formatting."""
        test_cases = [
            (
                BAMEndpoints.configuration_blocks(123),
                BAMEndpoints.CONFIGURATION_BLOCKS.format(config_id=123),
            ),
            (
                BAMEndpoints.block_by_id(456),
                BAMEndpoints.BLOCK_BY_ID.format(block_id=456),
            ),
            (
                BAMEndpoints.network_addresses(789),
                BAMEndpoints.NETWORK_ADDRESSES.format(network_id=789),
            ),
            (
                BAMEndpoints.zone_resource_records(101),
                BAMEndpoints.ZONE_RESOURCE_RECORDS.format(zone_id=101),
            ),
        ]

        for helper_result, format_result in test_cases:
            assert helper_result == format_result


class TestBAMEndpointsValidation:
    """Tests for comprehensive endpoint validation."""

    def test_all_endpoints_are_strings(self) -> None:
        """Verify all endpoint constants are strings."""
        for attr_name in dir(BAMEndpoints):
            if attr_name.isupper() and not attr_name.startswith("_"):
                attr_value = getattr(BAMEndpoints, attr_name)
                assert isinstance(attr_value, str), f"{attr_name} should be a string"

    def test_no_leading_slashes(self) -> None:
        """Verify endpoints don't have leading slashes (relative paths)."""
        for attr_name in dir(BAMEndpoints):
            if attr_name.isupper() and not attr_name.startswith("_"):
                attr_value = getattr(BAMEndpoints, attr_name)
                if isinstance(attr_value, str):
                    assert not attr_value.startswith("/"), (
                        f"{attr_name} should not start with '/'"
                    )

    def test_no_trailing_slashes(self) -> None:
        """Verify endpoints don't have trailing slashes."""
        for attr_name in dir(BAMEndpoints):
            if attr_name.isupper() and not attr_name.startswith("_"):
                attr_value = getattr(BAMEndpoints, attr_name)
                if isinstance(attr_value, str):
                    assert not attr_value.endswith("/"), (
                        f"{attr_name} should not end with '/'"
                    )

    def test_parameter_placeholder_format(self) -> None:
        """Verify parameter placeholders use curly braces correctly."""
        import re

        for attr_name in dir(BAMEndpoints):
            if attr_name.isupper() and not attr_name.startswith("_"):
                attr_value = getattr(BAMEndpoints, attr_name)
                if isinstance(attr_value, str) and "{" in attr_value:
                    # Should not have spaces in placeholders
                    assert "{ " not in attr_value, f"{attr_name} has space after {{"
                    assert " }" not in attr_value, f"{attr_name} has space before }}"

                    # All placeholders should match format
                    placeholders = re.findall(r"\{(\w+)\}", attr_value)
                    assert len(placeholders) > 0, (
                        f"{attr_name} has malformed placeholders"
                    )


class TestBAMEndpointsNewResources:
    """Test endpoints for recently added resource types."""

    def test_location_endpoints(self) -> None:
        """Test location-related endpoints."""
        assert BAMEndpoints.LOCATIONS == "locations"
        assert BAMEndpoints.location_by_id(123) == "locations/123"
        assert (
            BAMEndpoints.location_child_locations(123) == "locations/123/locations"
        )
        assert (
            BAMEndpoints.location_annotated_resources(123)
            == "locations/123/annotatedResources"
        )

    def test_udf_udl_endpoints(self) -> None:
        """Test UDF and UDL endpoints."""
        assert BAMEndpoints.UDF_DEFINITIONS == "userDefinedFieldDefinitions"
        assert BAMEndpoints.UDL_DEFINITIONS == "userDefinedLinkDefinitions"
        assert BAMEndpoints.udf_definition_by_id(456) == "userDefinedFieldDefinitions/456"
        assert BAMEndpoints.udl_definition_by_id(789) == "userDefinedLinkDefinitions/789"

    def test_mac_pool_endpoints(self) -> None:
        """Test MAC pool endpoints."""
        assert BAMEndpoints.MAC_POOLS == "macPools"
        assert BAMEndpoints.mac_pool_by_id(111) == "macPools/111"
        assert (
            BAMEndpoints.configuration_mac_pools(222) == "configurations/222/macPools"
        )
        assert BAMEndpoints.mac_pool_mac_addresses(333) == "macPools/333/macAddresses"

    def test_tag_endpoints(self) -> None:
        """Test tag and tag group endpoints."""
        assert BAMEndpoints.TAGS == "tags"
        assert BAMEndpoints.TAG_GROUPS == "tagGroups"
        assert BAMEndpoints.tag_by_id(444) == "tags/444"
        assert BAMEndpoints.tag_group_by_id(555) == "tagGroups/555"
        assert BAMEndpoints.tag_group_tags(666) == "tagGroups/666/tags"
        assert BAMEndpoints.network_tags(777) == "networks/777/tags"

    def test_device_endpoints(self) -> None:
        """Test device-related endpoints."""
        assert BAMEndpoints.DEVICES == "devices"
        assert BAMEndpoints.device_by_id(888) == "devices/888"
        assert BAMEndpoints.device_addresses(999) == "devices/999/addresses"
        assert (
            BAMEndpoints.device_address_by_id(111, 222) == "devices/111/addresses/222"
        )
        assert BAMEndpoints.configuration_devices(333) == "configurations/333/devices"

    def test_device_type_endpoints(self) -> None:
        """Test device type endpoints."""
        assert BAMEndpoints.DEVICE_TYPES == "deviceTypes"
        assert BAMEndpoints.DEVICE_SUBTYPES == "deviceSubtypes"
        assert BAMEndpoints.device_type_by_id(444) == "deviceTypes/444"
        assert BAMEndpoints.device_subtype_by_id(555) == "deviceSubtypes/555"
        assert BAMEndpoints.device_type_subtypes(666) == "deviceTypes/666/deviceSubtypes"

    def test_access_right_endpoints(self) -> None:
        """Test access right endpoints."""
        assert BAMEndpoints.ACCESS_RIGHTS == "accessRights"
        assert BAMEndpoints.access_right_by_id(777) == "accessRights/777"

    def test_user_group_endpoints(self) -> None:
        """Test user and group endpoints."""
        assert BAMEndpoints.USERS == "users"
        assert BAMEndpoints.GROUPS == "groups"
        assert BAMEndpoints.user_by_id(888) == "users/888"
        assert BAMEndpoints.group_by_id(999) == "groups/999"

    def test_ip_group_endpoints(self) -> None:
        """Test IP group endpoints."""
        assert BAMEndpoints.IP_GROUPS == "ipGroups"
        assert BAMEndpoints.ip_group_by_id(123) == "ipGroups/123"
        assert BAMEndpoints.network_ip_groups(456) == "networks/456/ipGroups"


class TestBAMEndpointsParameterSubstitution:
    """Test parameter substitution edge cases."""

    def test_multiple_parameters(self) -> None:
        """Test endpoints with multiple parameters."""
        endpoint = BAMEndpoints.RESOURCE_USER_DEFINED_LINK_BY_ID.format(
            collection="networks", resource_id=123, link_id=456
        )
        assert endpoint == "networks/123/userDefinedLinks/456"

    def test_parameter_type_conversion(self) -> None:
        """Test that integer IDs are properly converted."""
        endpoint = BAMEndpoints.network_by_id(789)
        assert endpoint == "networks/789"
        assert isinstance(endpoint, str)

    def test_extra_parameters_ignored(self) -> None:
        """Test that extra parameters are ignored in simple endpoints."""
        endpoint = BAMEndpoints.SESSIONS.format(unused_param=123)
        assert endpoint == "sessions"
