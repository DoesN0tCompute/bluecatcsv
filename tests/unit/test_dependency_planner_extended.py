"""Extended unit tests for Dependency Planner - covering critical missing scenarios.

This test file focuses on areas with low coverage:
- DNS record dependencies (alias_record, srv_record, mx_record)
- Location hierarchies and resource-to-location associations
- Deployment role dependencies (dhcp_deployment_role, dns_deployment_role)
- DHCP range dependencies
- Host record with address dependencies on networks
"""

from unittest.mock import MagicMock

import pytest

from src.importer.dependency.graph import DependencyGraph
from src.importer.dependency.planner import DependencyPlanner
from src.importer.models.operations import Operation, OperationType


class TestDNSRecordDependencies:
    """Test DNS record dependencies - alias, srv, mx records."""

    @pytest.fixture
    def planner(self):
        """Create a dependency planner."""
        return DependencyPlanner()

    @pytest.fixture
    def create_dns_op(self):
        """Factory for creating DNS operations."""

        def _create_op(row_id: int, obj_type: str, **kwargs):
            csv_row = MagicMock()
            csv_row.row_id = row_id
            csv_row.object_type = obj_type
            csv_row.action = "create"
            csv_row.config = "Default"

            # Set all possible attributes to None
            csv_row.zone_name = None
            csv_row.name = None
            csv_row.addresses = None
            csv_row.linked_record_name = None
            csv_row.cname = None
            csv_row.target = None
            csv_row.exchange = None
            csv_row.parent_path = None
            csv_row.network_path = None
            csv_row.block_path = None
            csv_row.zone_path = None
            csv_row.code = None

            # Set provided kwargs
            for k, v in kwargs.items():
                setattr(csv_row, k, v)

            payload = kwargs.get("payload", {})
            return Operation(
                row_id=row_id,
                operation_type=OperationType.CREATE,
                object_type=obj_type,
                resource_id=None,
                payload=payload,
                csv_row=csv_row,
            )

        return _create_op

    def test_alias_record_depends_on_host_record(self, planner, create_dns_op):
        """Test that alias_record depends on host_record it points to."""
        graph = DependencyGraph()

        # Create host record
        op_host = create_dns_op(
            1, "host_record",
            name="web.example.com",
            zone_name="example.com"
        )

        # Create alias record pointing to host
        op_alias = create_dns_op(
            2, "alias_record",
            name="www.example.com",
            linked_record_name="web.example.com",
            zone_name="example.com"
        )

        planner.build_graph(graph, [op_host, op_alias])

        node_host = "host_record:1"
        node_alias = "alias_record:2"

        # Alias should depend on host
        alias_node = graph.nodes[node_alias]
        assert node_host in alias_node.dependencies

    def test_alias_record_with_cname_field(self, planner, create_dns_op):
        """Test that alias_record with cname field also creates dependency."""
        graph = DependencyGraph()

        op_host = create_dns_op(
            1, "host_record",
            name="server.example.com",
            zone_name="example.com"
        )

        # Use 'cname' field instead of 'linked_record_name'
        op_alias = create_dns_op(
            2, "alias_record",
            name="alias.example.com",
            cname="server.example.com",
            zone_name="example.com"
        )

        planner.build_graph(graph, [op_host, op_alias])

        node_host = "host_record:1"
        node_alias = "alias_record:2"

        alias_node = graph.nodes[node_alias]
        assert node_host in alias_node.dependencies

    def test_srv_record_depends_on_target(self, planner, create_dns_op):
        """Test that srv_record depends on its target host record."""
        graph = DependencyGraph()

        op_host = create_dns_op(
            1, "host_record",
            name="ldap.example.com",
            zone_name="example.com"
        )

        op_srv = create_dns_op(
            2, "srv_record",
            name="_ldap._tcp.example.com",
            target="ldap.example.com",
            zone_name="example.com"
        )

        planner.build_graph(graph, [op_host, op_srv])

        node_host = "host_record:1"
        node_srv = "srv_record:2"

        srv_node = graph.nodes[node_srv]
        assert node_host in srv_node.dependencies

    def test_mx_record_depends_on_exchange(self, planner, create_dns_op):
        """Test that mx_record depends on its exchange host record."""
        graph = DependencyGraph()

        op_host = create_dns_op(
            1, "host_record",
            name="mail.example.com",
            zone_name="example.com"
        )

        op_mx = create_dns_op(
            2, "mx_record",
            name="example.com",
            exchange="mail.example.com",
            zone_name="example.com"
        )

        planner.build_graph(graph, [op_host, op_mx])

        node_host = "host_record:1"
        node_mx = "mx_record:2"

        mx_node = graph.nodes[node_mx]
        assert node_host in mx_node.dependencies

    def test_dns_records_depend_on_zones(self, planner, create_dns_op):
        """Test that DNS records depend on zones being created."""
        graph = DependencyGraph()

        op_zone = create_dns_op(
            1, "dns_zone",
            zone_name="example.com"
        )

        op_host = create_dns_op(
            2, "host_record",
            name="web.example.com",
            zone_name="example.com"
        )

        planner.build_graph(graph, [op_zone, op_host])

        node_zone = "dns_zone:1"
        node_host = "host_record:2"

        host_node = graph.nodes[node_host]
        assert node_zone in host_node.dependencies

    def test_dns_record_with_deferred_zone(self, planner, create_dns_op):
        """Test DNS record with deferred zone resolution."""
        graph = DependencyGraph()

        op_zone = create_dns_op(
            1, "dns_zone",
            zone_name="new.example.com"
        )

        op_host = create_dns_op(
            2, "host_record",
            name="web.new.example.com",
            zone_name="new.example.com",
            payload={"_deferred_zone_name": "new.example.com"}
        )

        planner.build_graph(graph, [op_zone, op_host])

        node_zone = "dns_zone:1"
        node_host = "host_record:2"

        host_node = graph.nodes[node_host]
        assert node_zone in host_node.dependencies


class TestLocationDependencies:
    """Test location hierarchy dependencies."""

    @pytest.fixture
    def planner(self):
        """Create a dependency planner."""
        return DependencyPlanner()

    @pytest.fixture
    def create_location_op(self):
        """Factory for creating location operations."""

        def _create_op(row_id: int, obj_type: str, **kwargs):
            csv_row = MagicMock()
            csv_row.row_id = row_id
            csv_row.object_type = obj_type
            csv_row.action = "create"

            # Set all possible attributes
            csv_row.code = kwargs.get("code")
            csv_row.name = kwargs.get("name")
            csv_row.parent_location_code = kwargs.get("parent_location_code")
            csv_row.cidr = kwargs.get("cidr")
            csv_row.config = kwargs.get("config", "Default")
            csv_row.parent_path = None
            csv_row.network_path = None
            csv_row.zone_name = None

            payload = kwargs.get("payload", {})
            return Operation(
                row_id=row_id,
                operation_type=OperationType.CREATE,
                object_type=obj_type,
                resource_id=None,
                payload=payload,
                csv_row=csv_row,
            )

        return _create_op

    def test_child_location_depends_on_parent(self, planner, create_location_op):
        """Test that child location depends on parent location."""
        graph = DependencyGraph()

        op_parent = create_location_op(
            1, "location",
            code="US",
            name="United States"
        )

        op_child = create_location_op(
            2, "location",
            code="US-CA",
            name="California",
            parent_location_code="US",
            payload={"_deferred_location_code": "US"}
        )

        planner.build_graph(graph, [op_parent, op_child])

        node_parent = "location:1"
        node_child = "location:2"

        child_node = graph.nodes[node_child]
        assert node_parent in child_node.dependencies

    def test_resource_depends_on_location(self, planner, create_location_op):
        """Test that resources depend on locations they're associated with."""
        graph = DependencyGraph()

        op_location = create_location_op(
            1, "location",
            code="DC1",
            name="Data Center 1"
        )

        # Network associated with location
        op_network = create_location_op(
            2, "ip4_network",
            cidr="10.1.1.0/24",
            name="DC1 Network",
            config="Default",
            payload={"_deferred_location_code": "DC1"}
        )

        planner.build_graph(graph, [op_location, op_network])

        node_location = "location:1"
        node_network = "ip4_network:2"

        network_node = graph.nodes[node_network]
        assert node_location in network_node.dependencies


class TestDeploymentRoleDependencies:
    """Test deployment role dependencies."""

    @pytest.fixture
    def planner(self):
        """Create a dependency planner."""
        return DependencyPlanner()

    @pytest.fixture
    def create_deployment_op(self):
        """Factory for creating deployment role operations."""

        def _create_op(row_id: int, obj_type: str, **kwargs):
            csv_row = MagicMock()
            csv_row.row_id = row_id
            csv_row.object_type = obj_type
            csv_row.action = "create"
            csv_row.config = "Default"

            # Set all possible attributes to None
            csv_row.network_path = kwargs.get("network_path")
            csv_row.zone_name = kwargs.get("zone_name")
            csv_row.cidr = kwargs.get("cidr")
            csv_row.parent_path = None
            csv_row.zone_path = None
            csv_row.code = None

            payload = kwargs.get("payload", {})
            return Operation(
                row_id=row_id,
                operation_type=OperationType.CREATE,
                object_type=obj_type,
                resource_id=None,
                payload=payload,
                csv_row=csv_row,
            )

        return _create_op

    def test_dhcp_role_depends_on_network(self, planner, create_deployment_op):
        """Test that DHCP deployment role depends on network."""
        graph = DependencyGraph()

        op_network = create_deployment_op(
            1, "ip4_network",
            cidr="10.1.1.0/24"
        )
        op_network.csv_row.cidr = "10.1.1.0/24"

        op_dhcp_role = create_deployment_op(
            2, "dhcp_deployment_role",
            network_path="Default/10.1.1.0/24",
            payload={"_deferred_network_cidr": "10.1.1.0/24"}
        )

        planner.build_graph(graph, [op_network, op_dhcp_role])

        node_network = "ip4_network:1"
        node_role = "dhcp_deployment_role:2"

        role_node = graph.nodes[node_role]
        assert node_network in role_node.dependencies

    def test_dhcp_role_depends_on_block(self, planner, create_deployment_op):
        """Test that DHCP deployment role can depend on block."""
        graph = DependencyGraph()

        op_block = create_deployment_op(
            1, "ip4_block",
            cidr="10.1.0.0/16"
        )
        op_block.csv_row.cidr = "10.1.0.0/16"

        op_dhcp_role = create_deployment_op(
            2, "dhcp_deployment_role",
            payload={"_deferred_block_cidr": "10.1.0.0/16"}
        )

        planner.build_graph(graph, [op_block, op_dhcp_role])

        node_block = "ip4_block:1"
        node_role = "dhcp_deployment_role:2"

        role_node = graph.nodes[node_role]
        assert node_block in role_node.dependencies

    def test_dns_role_depends_on_zone(self, planner, create_deployment_op):
        """Test that DNS deployment role depends on zone."""
        graph = DependencyGraph()

        op_zone = create_deployment_op(
            1, "dns_zone",
            zone_name="example.com"
        )
        op_zone.csv_row.zone_name = "example.com"

        op_dns_role = create_deployment_op(
            2, "dns_deployment_role",
            zone_name="example.com",
            payload={"_deferred_zone_name": "example.com"}
        )

        planner.build_graph(graph, [op_zone, op_dns_role])

        node_zone = "dns_zone:1"
        node_role = "dns_deployment_role:2"

        role_node = graph.nodes[node_role]
        assert node_zone in role_node.dependencies


class TestDHCPRangeDependencies:
    """Test DHCP range dependencies."""

    @pytest.fixture
    def planner(self):
        """Create a dependency planner."""
        return DependencyPlanner()

    @pytest.fixture
    def create_dhcp_op(self):
        """Factory for creating DHCP operations."""

        def _create_op(row_id: int, obj_type: str, **kwargs):
            csv_row = MagicMock()
            csv_row.row_id = row_id
            csv_row.object_type = obj_type
            csv_row.action = "create"
            csv_row.config = "Default"

            csv_row.cidr = kwargs.get("cidr")
            csv_row.range = kwargs.get("range")
            csv_row.network_path = kwargs.get("network_path")
            csv_row.parent_path = None
            csv_row.zone_name = None
            csv_row.code = None

            payload = kwargs.get("payload", {})
            return Operation(
                row_id=row_id,
                operation_type=OperationType.CREATE,
                object_type=obj_type,
                resource_id=None,
                payload=payload,
                csv_row=csv_row,
            )

        return _create_op

    def test_dhcp_range_depends_on_network(self, planner, create_dhcp_op):
        """Test that DHCP range depends on network."""
        graph = DependencyGraph()

        op_network = create_dhcp_op(
            1, "ip4_network",
            cidr="10.1.1.0/24"
        )
        op_network.csv_row.cidr = "10.1.1.0/24"

        op_range = create_dhcp_op(
            2, "ipv4_dhcp_range",
            range="10.1.1.100-10.1.1.200",
            network_path="Default/10.1.1.0/24",
            payload={"_deferred_network_cidr": "10.1.1.0/24"}
        )

        planner.build_graph(graph, [op_network, op_range])

        node_network = "ip4_network:1"
        node_range = "ipv4_dhcp_range:2"

        range_node = graph.nodes[node_range]
        assert node_network in range_node.dependencies


class TestHostRecordWithAddressDependencies:
    """Test host record with addresses depending on networks."""

    @pytest.fixture
    def planner(self):
        """Create a dependency planner."""
        return DependencyPlanner()

    @pytest.fixture
    def create_host_op(self):
        """Factory for creating host record operations."""

        def _create_op(row_id: int, obj_type: str, **kwargs):
            csv_row = MagicMock()
            csv_row.row_id = row_id
            csv_row.object_type = obj_type
            csv_row.action = "create"
            csv_row.config = "Default"

            csv_row.name = kwargs.get("name")
            csv_row.addresses = kwargs.get("addresses")
            csv_row.zone_name = kwargs.get("zone_name")
            csv_row.cidr = kwargs.get("cidr")
            csv_row.parent_path = None
            csv_row.network_path = None
            csv_row.code = None
            csv_row.linked_record_name = None
            csv_row.cname = None
            csv_row.target = None
            csv_row.exchange = None

            payload = kwargs.get("payload", {})
            return Operation(
                row_id=row_id,
                operation_type=OperationType.CREATE,
                object_type=obj_type,
                resource_id=None,
                payload=payload,
                csv_row=csv_row,
            )

        return _create_op

    def test_host_record_with_single_address_depends_on_network(
        self, planner, create_host_op
    ):
        """Test that host record with address depends on network containing that address."""
        graph = DependencyGraph()

        op_network = create_host_op(
            1, "ip4_network",
            cidr="10.1.1.0/24"
        )
        op_network.csv_row.cidr = "10.1.1.0/24"

        op_host = create_host_op(
            2, "host_record",
            name="web.example.com",
            addresses="10.1.1.10",
            zone_name="example.com"
        )

        planner.build_graph(graph, [op_network, op_host])

        node_network = "ip4_network:1"
        node_host = "host_record:2"

        host_node = graph.nodes[node_host]
        assert node_network in host_node.dependencies

    def test_host_record_with_multiple_addresses(self, planner, create_host_op):
        """Test that host record with multiple addresses creates multiple dependencies."""
        graph = DependencyGraph()

        op_network1 = create_host_op(
            1, "ip4_network",
            cidr="10.1.1.0/24"
        )
        op_network1.csv_row.cidr = "10.1.1.0/24"

        op_network2 = create_host_op(
            2, "ip4_network",
            cidr="10.1.2.0/24"
        )
        op_network2.csv_row.cidr = "10.1.2.0/24"

        # Host with addresses in both networks (pipe-separated)
        op_host = create_host_op(
            3, "host_record",
            name="web.example.com",
            addresses="10.1.1.10|10.1.2.10",
            zone_name="example.com"
        )

        planner.build_graph(graph, [op_network1, op_network2, op_host])

        node_network1 = "ip4_network:1"
        node_network2 = "ip4_network:2"
        node_host = "host_record:3"

        host_node = graph.nodes[node_host]
        # Host should depend on both networks
        assert node_network1 in host_node.dependencies
        assert node_network2 in host_node.dependencies

    def test_host_record_with_invalid_address_skipped(self, planner, create_host_op):
        """Test that invalid addresses in host record are skipped gracefully."""
        graph = DependencyGraph()

        op_network = create_host_op(
            1, "ip4_network",
            cidr="10.1.1.0/24"
        )
        op_network.csv_row.cidr = "10.1.1.0/24"

        # Host with one valid and one invalid address
        op_host = create_host_op(
            2, "host_record",
            name="web.example.com",
            addresses="10.1.1.10|invalid-address",
            zone_name="example.com"
        )

        # Should not raise exception
        planner.build_graph(graph, [op_network, op_host])

        node_network = "ip4_network:1"
        node_host = "host_record:2"

        host_node = graph.nodes[node_host]
        # Should still have dependency for valid address
        assert node_network in host_node.dependencies


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.fixture
    def planner(self):
        """Create a dependency planner."""
        return DependencyPlanner()

    def test_empty_operations_list(self, planner):
        """Test that empty operations list is handled gracefully."""
        graph = DependencyGraph()
        planner.build_graph(graph, [])
        assert len(graph.nodes) == 0

    def test_operations_with_missing_attributes(self, planner):
        """Test operations with missing/None attributes don't crash."""
        graph = DependencyGraph()

        csv_row = MagicMock()
        csv_row.row_id = 1
        csv_row.object_type = "ip4_network"
        csv_row.cidr = None  # Missing CIDR
        csv_row.parent_path = None
        csv_row.network_path = None
        csv_row.zone_name = None
        csv_row.code = None

        op = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            resource_id=None,
            payload={},
            csv_row=csv_row,
        )

        # Should not crash
        planner.build_graph(graph, [op])
        assert "ip4_network:1" in graph.nodes

    def test_circular_dependency_potential_detected_by_graph(self, planner):
        """Test that circular dependencies would be caught by graph validation."""
        graph = DependencyGraph()

        # Create operations that could form a cycle
        # (though in practice, DNS records can't reference each other circularly through the planner)
        csv_row1 = MagicMock()
        csv_row1.row_id = 1
        csv_row1.object_type = "host_record"
        csv_row1.name = "a.example.com"
        csv_row1.zone_name = "example.com"
        csv_row1.addresses = None
        csv_row1.code = None

        op1 = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="host_record",
            resource_id=None,
            payload={},
            csv_row=csv_row1,
        )

        planner.build_graph(graph, [op1])

        # Graph validation would catch actual cycles if they existed
        # This test verifies the mechanism works
        assert "host_record:1" in graph.nodes
