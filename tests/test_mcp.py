import json
import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.mcp import _invocation_from_args, call_tool, handle_json_rpc, tool_definitions
from universal_orchestrator.models import PrivacyMode


class MCPAdapterTests(unittest.TestCase):
    def test_tool_definitions_include_report_surface(self) -> None:
        names = {tool["name"] for tool in tool_definitions()}

        self.assertIn("ai_team.run", names)
        self.assertIn("ai_team.run_start", names)
        self.assertIn("ai_team.status", names)
        self.assertIn("ai_team.providers", names)
        self.assertIn("ai_team.capacity", names)
        self.assertIn("ai_team.events", names)
        self.assertIn("ai_team.doctor", names)
        self.assertIn("ai_team.evals", names)

    def test_json_rpc_tools_list(self) -> None:
        response = handle_json_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

        self.assertEqual(response["id"], 1)
        self.assertIn("tools", response["result"])

    def test_mcp_invocation_preserves_policy_budget_and_artifact_controls(self) -> None:
        invocation = _invocation_from_args(
            {
                "prompt": "Create a report",
                "paths": ["source.md"],
                "quality": "max",
                "budget": "premium",
                "cost_ceiling": 0.25,
                "artifact_types": ["pdf"],
                "allow_internet": True,
                "allowed_url_hosts": ["example.com"],
                "allow_cloud": True,
                "allow_repo_writes": True,
                "allow_shell": True,
                "privacy_mode": "explicit_approval",
            },
            "mcp.test",
        )

        self.assertEqual(invocation.user_options.quality, "max")
        self.assertEqual(invocation.user_options.budget_profile, "premium")
        self.assertEqual(invocation.user_options.cost_ceiling_usd, 0.25)
        self.assertEqual(invocation.user_options.artifact_types, ["pdf"])
        self.assertEqual(invocation.user_options.allowed_url_hosts, ["example.com"])
        self.assertEqual(invocation.user_options.privacy_mode, PrivacyMode.EXPLICIT_APPROVAL)
        self.assertTrue(invocation.user_options.allow_repo_writes)
        self.assertTrue(invocation.user_options.allow_shell)

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
        self.assertIn("runtime_snapshot", status)

    def test_ai_team_cancel_rejects_terminal_run(self) -> None:
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
            cancel = call_tool(
                "ai_team.cancel",
                {"run_id": run_result["run_id"], "root": str(root / "runs")},
            )

        self.assertFalse(cancel["accepted"])
        self.assertFalse(cancel["cancelled"])

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

    def test_capacity_and_events_tools_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runs"
            capacity = call_tool("ai_team.capacity", {"root": str(root)})
            events = call_tool("ai_team.events", {"root": str(root), "run_id": "missing"})

        self.assertEqual(capacity["snapshots"], [])
        self.assertEqual(events["events"], [])

    def test_repo_prepare_accepts_explicit_edits_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            target = root / "note.md"
            result = call_tool(
                "ai_team.repo_prepare",
                {
                    "prompt": "Add a note",
                    "path": str(root),
                    "edits": [{"path": "note.md", "content": "prepared\n"}],
                },
            )

            self.assertEqual(result["state"], "prepared")
            self.assertTrue(result["implemented"])
            self.assertFalse(result["writes_performed"])
            self.assertFalse(target.exists())
            self.assertTrue(result["changeset"]["approval_digest"])

    def test_run_start_returns_immediately_and_can_be_polled(self) -> None:
        import time

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.md"
            source.write_text("# Input\nBuild a tiny package.")
            started = call_tool(
                "ai_team.run_start",
                {
                    "prompt": "Build a final package",
                    "paths": [str(source)],
                    "root": str(root / "runs"),
                },
            )
            state: dict[str, object] = {}
            for _ in range(40):
                state = call_tool(
                    "ai_team.status",
                    {"run_id": started["run_id"], "root": str(root / "runs")},
                )
                snapshot = state.get("runtime_snapshot", {})
                if isinstance(snapshot, dict) and snapshot.get("latest_state") == "delivered":
                    break
                time.sleep(0.025)

        self.assertTrue(started["accepted"])
        self.assertEqual(started["run_id"], state["run_id"])


if __name__ == "__main__":
    unittest.main()
