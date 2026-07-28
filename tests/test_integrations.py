from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.integrations import IntegrationManager


class IntegrationTests(unittest.TestCase):
    def test_json_install_verify_is_idempotent_and_uninstall_is_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}))
            manager = IntegrationManager(executable="uo-test")

            first = manager.install("cursor", explicit_path=path)
            second = manager.install("cursor", explicit_path=path)
            payload = json.loads(path.read_text())

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertEqual(payload["mcpServers"]["universal-orchestrator"]["command"], "uo-test")
            self.assertEqual(manager.verify("cursor", explicit_path=path)["configured"], True)

            receipt = manager.uninstall("cursor", explicit_path=path)
            payload = json.loads(path.read_text())
            self.assertTrue(receipt.changed)
            self.assertIn("other", payload["mcpServers"])
            self.assertNotIn("universal-orchestrator", payload["mcpServers"])

    def test_jsonc_url_is_not_destroyed_by_comment_stripping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(
                '{\n  "url": "https://example.test/mcp", // keep URL\n'
                '  "mcpServers": {}\n}\n'
            )
            IntegrationManager(executable="uo-test").install("generic", explicit_path=path)
            payload = json.loads(path.read_text())
            self.assertEqual(payload["url"], "https://example.test/mcp")

    def test_codex_install_replaces_only_owned_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                'model = "gpt-test"\n\n'
                '[mcp_servers."other"]\ncommand = "other"\n\n'
                '[mcp_servers."universal-orchestrator"]\ncommand = "old"\nargs = ["old"]\n'
            )
            manager = IntegrationManager(executable="uo-test")
            manager.install("codex", explicit_path=path)
            text = path.read_text()

            self.assertIn('model = "gpt-test"', text)
            self.assertIn('[mcp_servers."other"]', text)
            self.assertIn('command = "uo-test"', text)
            self.assertNotIn('command = "old"', text)

    def test_uninstall_missing_file_is_a_noop_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            receipt = IntegrationManager().uninstall("generic", explicit_path=path)
            self.assertFalse(receipt.changed)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
