from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.cli import build_parser, handle_release_gate
from universal_orchestrator.release_gate import ReleaseGateRunner


class TrancheO8ReleaseGateTests(unittest.TestCase):
    def test_parser_exposes_offline_release_gate(self) -> None:
        args = build_parser().parse_args(["release-gate", "--root", ".uo/test-release-gate"])

        self.assertIs(args.handler, handle_release_gate)
        self.assertEqual(args.root, ".uo/test-release-gate")

    def test_fixture_release_gate_passes_all_adversarial_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = ReleaseGateRunner().run(Path(tmp))

        self.assertTrue(report["passed"])
        names = {check["name"] for check in report["checks"]}
        self.assertEqual(
            names,
            {
                "built_in_evals",
                "delivery_state_consistency",
                "local_only_no_egress",
                "key_sweep",
                "context_text_tamper_detection",
                "context_hash_tamper_detection",
                "fidelity_failure_blocks_delivery",
                "integrity_failure_blocks_delivery",
                "repository_mode_preservation",
                "repository_stale_write_rejection",
                "write_approval_boundary",
            },
        )
        self.assertTrue(all(check["passed"] for check in report["checks"]))
        self.assertTrue(all(isinstance(check["passed"], bool) for check in report["checks"]))


if __name__ == "__main__":
    unittest.main()
