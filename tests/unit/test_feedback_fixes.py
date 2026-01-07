import copy
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.importer.bam.client import BAMClient
from src.importer.config import BAMConfig, PolicyConfig
from src.importer.core.parser import CSVParser
from src.importer.execution.executor import OperationExecutor
from src.importer.models.operations import Operation, OperationType


class TestFeedbackFixes:

    @pytest.mark.asyncio
    async def test_parser_bom_handling(self, tmp_path):
        """Test that CSVParser correctly handles files with BOM (utf-8-sig)."""
        csv_path = tmp_path / "test_bom.csv"
        # Create file with BOM and some content
        content = "\ufeffrow_id,object_type,cidr,name\n1,ip4_block,10.0.0.0/8,TestBlock"
        csv_path.write_text(
            content, encoding="utf-8"
        )  # write as utf-8 but include char explicitly or use encoding

        # Actually easier to verify encoding handle:
        # If we write with utf-8-sig, python adds BOM.
        csv_path.write_text(
            "row_id,object_type,action,config,cidr,name\n1,ip4_block,create,TestConfig,10.0.0.0/8,TestBlock",
            encoding="utf-8-sig",
        )

        parser = CSVParser(csv_path)
        rows = parser.parse(strict=True)

        assert len(rows) == 1
        # If BOM wasn't handled, the first key would be "\ufeffrow_id" and validation might fail
        # (or just key mismatch if strict=False).
        # Since strict=True, it would fail if "row_id" wasn't found in headers if we relied on it.
        # But CSVParser checks row_list[0] == "row_id". With BOM, row_list[0] would be "\ufeffrow_id".
        assert rows[0].row_id == "1"
        assert rows[0].cidr == "10.0.0.0/8"

    @pytest.mark.asyncio
    async def test_executor_payload_immutability_on_failure(self):
        """Test that OperationExecutor does not modify original operation on failure."""

        # Setup
        MagicMock(spec=BAMConfig)
        policy = MagicMock(spec=PolicyConfig)
        # Mock throttle
        throttle = MagicMock()
        throttle.__aenter__ = AsyncMock()
        throttle.__aexit__ = AsyncMock()

        executor = OperationExecutor(bam_client=MagicMock(), policy=policy, throttle=throttle)

        # Pre-seed deferred resolution map
        executor.created_blocks["10.0.0.0/8"] = 12345

        # Create operations
        payload = {"name": "TestNetwork", "_deferred_block_cidr": "10.0.0.0/8"}
        copy.deepcopy(payload)

        op = Operation(
            row_id=1,
            operation_type=OperationType.CREATE,
            object_type="ip4_network",
            resource_id=None,
            payload=payload,
            csv_row=MagicMock(),
        )

        # Mock _execute_create to fail
        executor._execute_create = AsyncMock(side_effect=Exception("Simulation Failure"))

        # Execute
        result = await executor._execute_operation(op)

        # Verify result is failure
        assert result.success is False
        assert result.error_message == "Simulation Failure"

        # Verify ORIGINAL payload is UNCHANGED (still has deferred key)
        assert "_deferred_block_cidr" in op.payload
        assert op.payload["_deferred_block_cidr"] == "10.0.0.0/8"
        assert "block_id" not in op.payload

        # Verify that if it succeeds, it IS updated
        executor._execute_create = AsyncMock(return_value=MagicMock(success=True, resource_id=999))
        result_success = await executor._execute_operation(op)

        assert result_success.success is True
        # Now original payload SHOULD be updated with resolved ID
        assert "_deferred_block_cidr" not in op.payload
        assert op.payload["block_id"] == 12345

    def test_client_filter_escaping(self):
        """Test that BAMClient escapes filter values correctly."""
        config = MagicMock(spec=BAMConfig)
        config.base_url = "https://example.com"
        config.api_version = "v2"
        client = BAMClient(config)

        # Test cases
        assert client._escape_filter_value("normal") == "normal"
        assert client._escape_filter_value("o'reilly") == "o\\'reilly"
        assert client._escape_filter_value("'start") == "\\'start"
        assert client._escape_filter_value("end'") == "end\\'"
        assert client._escape_filter_value("mixed ' and normal") == "mixed \\' and normal"

        # Test non-string
        assert client._escape_filter_value(123) == "123"

    @pytest.mark.asyncio
    async def test_client_ipv6_interface_parsing(self):
        """Test robust parsing of interface strings including IPv6."""
        config = MagicMock(spec=BAMConfig)
        config.base_url = "https://example.com"
        config.api_version = "v2"
        client = BAMClient(config)

        # Mock dependencies
        client.get_server_by_name = AsyncMock(return_value={"id": 100})
        client.get_server_interfaces = AsyncMock(return_value=[{"id": 5, "name": "eth0"}])

        # Test 1: Standard IPv4-style (server:interface)
        res = await client.resolve_interface_string("server1:eth0")
        assert res == 5
        client.get_server_by_name.assert_called_with("server1")

        # Test 2: Unbracketed IPv6 - Should NOT split at first colon if ambiguous
        # "fe80::1:eth0" -> "fe80::1" and "eth0" (with rsplit fix)
        # Note: If we use unbracketed IPv6 as server name, it has colons.
        # Our fix used rsplit(":", 1).
        # Let's verify "fe80::1:eth0" splits to server="fe80::1", interface="eth0"

        client.get_server_by_name.reset_mock()
        res = await client.resolve_interface_string("fe80::1:eth0")
        client.get_server_by_name.assert_called_with("fe80::1")
        assert res == 5

        # Test 3: Bracketed IPv6 (Standard correct way)
        client.get_server_by_name.reset_mock()
        res = await client.resolve_interface_string("[fe80::1]:eth0")
        client.get_server_by_name.assert_called_with("fe80::1")
        assert res == 5

    @pytest.mark.asyncio
    async def test_client_pagination_loop_detection(self):
        """Test that pagination detects loops."""
        config = MagicMock(spec=BAMConfig)
        config.base_url = "https://example.com"
        config.api_version = "v2"
        client = BAMClient(config)

        # Mock get to return sequence A -> B -> B (Loop)
        # Response A
        resp_a = {
            "data": [{"id": 1}],
            "_links": {"next": "https://example.com/api/v2/items?page=2"},
        }
        # Response B
        resp_b = {
            "data": [{"id": 2}],
            "_links": {
                "next": "https://example.com/api/v2/items?page=2"
            },  # Points back to B (Self-loop)
        }

        client.get = AsyncMock(side_effect=[resp_a, resp_b, resp_b])

        # Run
        items = await client.get_all_pages("items")

        # Should collect 1 and 2, then stop when seeing page 2 again
        assert len(items) == 2
        assert items[0]["id"] == 1
        assert items[1]["id"] == 2
        # It should call get 2 times (A, B) and then STOP before 3rd fetch (B again) because key is in seen set?
        # Check logic:
        # 1. Start. Key A. Fetch A. Next=B.
        # 2. Key B. Fetch B. Next=B.
        # 3. Key B. SEEN! Break.
        # So get called 2 times.
        # Wait, get_all_pages might call get 2 times.
        assert client.get.call_count == 2
