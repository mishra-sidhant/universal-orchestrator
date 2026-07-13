from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.bench import BenchmarkRunner
from universal_orchestrator.cli import build_parser, handle_bench
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    HostInvocation,
    InputAttachment,
    PrivacyMode,
    UserOptions,
)
from universal_orchestrator.providers.transport import FakeTransport, HTTPResponse
from universal_orchestrator.routing import CapabilityRegistry


def openai_response(text: str, response_id: str) -> HTTPResponse:
    return HTTPResponse(
        200,
        {},
        json.dumps(
            {
                "id": response_id,
                "model": "fixture-model",
                "output_text": text,
                "usage": {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50},
            }
        ).encode(),
    )


class TrancheF7BenchmarkTests(unittest.TestCase):
    def test_parser_exposes_explicit_bench_command(self) -> None:
        args = build_parser().parse_args(["bench", "Compare this", "source.md"])
        self.assertIs(args.handler, handle_bench)
        self.assertEqual(args.prompt, "Compare this")
        self.assertEqual(args.paths, ["source.md"])

    def test_fixture_bench_emits_side_by_side_measurement_bundle_without_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Benchmark evidence is grounded in this source passage.")
            invocation = HostInvocation(
                command="bench",
                prompt="Compare native and orchestrated grounded output",
                attachments=[InputAttachment(uri=str(source))],
                user_options=UserOptions(
                    allow_internet=True,
                    allow_cloud=True,
                    privacy_mode=PrivacyMode.CLOUD_ALLOWED,
                    budget_profile="premium",
                ),
            )
            manifest = InputIngestor().ingest(invocation, "run_probe")
            ref = next(
                chunk.id
                for chunk in ContextIntelligence().chunk_manifest(manifest)
                if chunk.input_id != "input_prompt"
            )
            orchestrated = json.dumps(
                {
                    "summary": "Orchestrated fixture output with grounded evidence.",
                    "findings": [],
                    "claims": [
                        {
                            "text": "Benchmark evidence is grounded.",
                            "evidence_refs": [ref],
                        }
                    ],
                    "manuscript": [
                        {
                            "heading": "Benchmark Fixture",
                            "objective": "Compare native and orchestrated output.",
                            "body": "Benchmark evidence is grounded.",
                            "evidence_refs": [ref],
                        }
                    ],
                }
            )
            transport = FakeTransport(
                [
                    HTTPResponse(200, {}, b'{"data": []}'),
                    openai_response("Native fixture output.", "resp_native"),
                    openai_response(orchestrated, "resp_orchestrated_1"),
                    openai_response(orchestrated, "resp_orchestrated_2"),
                    openai_response(orchestrated, "resp_orchestrated_3"),
                ]
            )
            registry = CapabilityRegistry.from_environment(
                transports={"openai.configured": transport}
            )

            bundle = BenchmarkRunner(
                root / "bench",
                capability_registry=registry,
            ).run(invocation)
            bundle_dir = Path(bundle["bundle_dir"])
            comparison = json.loads((bundle_dir / "comparison.json").read_text())
            files_exist = [
                (bundle_dir / name).exists()
                for name in (
                    "native_output.md",
                    "orchestrated_output.md",
                    "quality_report.json",
                    "evidence_audit.json",
                )
            ]

        self.assertTrue(all(files_exist))
        self.assertEqual(comparison["automated_superiority_claim"], None)
        self.assertIn("human judgment", comparison["interpretation"].lower())
        self.assertEqual(comparison["native"]["provider_id"], "openai.configured")
        self.assertGreaterEqual(comparison["native"]["latency_ms"], 0)
        self.assertGreaterEqual(comparison["orchestrated"]["latency_ms"], 0)
        self.assertEqual(comparison["native"]["actual_cost_usd"], 0.00045)
        self.assertEqual(comparison["orchestrated"]["actual_cost_usd"], 0.00135)
        self.assertEqual(len(transport.requests), 5)


if __name__ == "__main__":
    unittest.main()
