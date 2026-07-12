from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from universal_orchestrator.cli import build_parser, handle_integrate


class HostIntegrationTests(unittest.TestCase):
    def test_integrate_prints_read_only_codex_mcp_configuration(self) -> None:
        args = build_parser().parse_args(["integrate", "--host", "codex"])
        output = io.StringIO()
        with redirect_stdout(output):
            handle_integrate(args)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["host"], "codex")
        self.assertEqual(
            payload["configuration"]["mcpServers"]["universal-orchestrator"]["args"],
            ["mcp-server"],
        )


if __name__ == "__main__":
    unittest.main()
