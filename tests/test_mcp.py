import json
import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.mcp import call_tool, handle_json_rpc, tool_definitions


class MCPAdapterTests(unittest.TestCase):
    def test_tool_definitions_include_report_surface(self) -> None:
        names = {tool["name"] for tool in tool_definitions()}

        self.assertIn("ai_team.run", names)
        self.assertIn("ai_team.status", names)
        self.assertIn("ai_team.providers", names)
        self.assertIn("ai_team.doctor", names)

    def test_json_rpc_tools_list(self) -> None:
        response = handle_json_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        self.assertEqual(response["id"], 1)
        self.assertIn("tools", response["result"])

    def test_ai_team_run_and_status_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.md"
            source.write_text("# Input\nBuild a tiny package.")

            run_result = call_tool(
                "ai_team.run",
                {
                    "prompt": "Build a final package",
                    "paths": [str(source)],
                    "root": str(root / "runs"),
                },
            )
            status = call_tool(
                "ai_team.status",
                {"run_id": run_result["run_id"], "root": str(root / "runs")},
            )

        self.assertTrue(run_result["quality_passed"])
        self.assertEqual(status["run_id"], run_result["run_id"])

    def test_tools_call_returns_text_content(self) -> None:
        response = handle_json_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "ai_team.doctor", "arguments": {}},
            }
        )

        text = response["result"]["content"][0]["text"]
        self.assertIn("python", json.loads(text))


if __name__ == "__main__":
    unittest.main()

