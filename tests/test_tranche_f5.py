from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.health import ProviderHealthChecker
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    CostTier,
    FallbackPolicy,
    HostInvocation,
    InputAttachment,
    PrivacyMode,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    TaskNode,
    TaskType,
    UserOptions,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.providers.transport import FakeTransport, HTTPResponse, TransportTimeout
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry


def response(status: int, payload: dict) -> HTTPResponse:
    return HTTPResponse(status, {}, json.dumps(payload).encode())


def descriptor(provider_id: str) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=provider_id,
        kind=ProviderKind.HOSTED_MODEL,
        enabled=True,
        capabilities={"final_synthesis": 0.9},
        cost_tier=CostTier.PREMIUM,
        health=ProviderHealth(status=ProviderStatus.UNKNOWN, reliability_score=0.5),
    )


def invocation(source: Path) -> HostInvocation:
    return HostInvocation(
        prompt="Produce a grounded provider health report",
        attachments=[InputAttachment(uri=str(source))],
        user_options=UserOptions(
            allow_internet=True,
            allow_cloud=True,
            privacy_mode=PrivacyMode.CLOUD_ALLOWED,
            budget_profile="premium",
        ),
    )


def chunk_id(source: Path, request: HostInvocation) -> str:
    manifest = InputIngestor().ingest(request, "run_probe")
    return next(
        chunk.id
        for chunk in ContextIntelligence().chunk_manifest(manifest)
        if chunk.input_id != "input_prompt"
    )


def structured(ref: str) -> str:
    return json.dumps(
        {
            "summary": "Grounded provider fallback synthesis completed.",
            "findings": [],
            "claims": [
                {
                    "text": "Provider fallback evidence is grounded.",
                    "evidence_refs": [ref],
                }
            ],
        }
    )


class TrancheF5HealthAndFallbackTests(unittest.TestCase):
    def test_health_probe_classifies_states_and_caches_by_ttl(self) -> None:
        now = [100.0]
        checker = ProviderHealthChecker(ttl_seconds=60, clock=lambda: now[0])
        healthy_transport = FakeTransport([response(200, {"data": []})])
        healthy = checker.check(descriptor("openai.configured"), healthy_transport)
        cached = checker.check(descriptor("openai.configured"), healthy_transport)
        self.assertEqual(healthy.status, ProviderStatus.HEALTHY)
        self.assertEqual(cached.status, ProviderStatus.HEALTHY)
        self.assertEqual(len(healthy_transport.requests), 1)

        degraded = checker.check(
            descriptor("anthropic.configured"),
            FakeTransport([response(429, {"error": "limited"})]),
        )
        down = checker.check(
            descriptor("ollama.local").model_copy(update={"kind": ProviderKind.LOCAL_MODEL}),
            FakeTransport([TransportTimeout("down")]),
        )
        self.assertEqual(degraded.status, ProviderStatus.DEGRADED)
        self.assertEqual(down.status, ProviderStatus.UNAVAILABLE)

    def test_health_probe_supports_gemini_xai_and_openai_compatible_matrix(self) -> None:
        checker = ProviderHealthChecker()
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_API_KEY": "fixture-google",
                "XAI_API_KEY": "fixture-xai",
                "OPENAI_COMPATIBLE_API_KEY": "fixture-local",
            },
            clear=True,
        ):
            cases = [
                ("gemini.configured", "https://generativelanguage.googleapis.com/v1beta/models", "x-goog-api-key", "fixture-google"),
                ("xai.configured", "https://api.x.ai/v1/models", "Authorization", "Bearer fixture-xai"),
                ("openai-compatible.local", "http://127.0.0.1:8000/v1/models", "Authorization", "Bearer fixture-local"),
            ]
            for provider_id, expected_url, header, expected_value in cases:
                with self.subTest(provider=provider_id):
                    transport = FakeTransport([response(200, {"data": []})])
                    health = checker.check(descriptor(provider_id), transport)

                    self.assertEqual(health.status, ProviderStatus.HEALTHY)
                    self.assertEqual(transport.requests[0].url, expected_url)
                    self.assertEqual(transport.requests[0].headers[header], expected_value)
                    self.assertNotIn("fixture-", transport.requests[0].url)

    def test_one_hosted_family_down_routes_to_other_and_reports_degradation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "fixture-openai",
                "OPENAI_MODEL": "openai-fixture",
                "ANTHROPIC_API_KEY": "fixture-anthropic",
                "ANTHROPIC_MODEL": "anthropic-fixture",
            },
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Provider fallback evidence is grounded in this source.")
            request = invocation(source)
            ref = chunk_id(source, request)
            openai = FakeTransport([response(503, {"error": "down"})])
            anthropic = FakeTransport(
                [
                    response(200, {"data": []}),
                    response(
                        200,
                        {
                            "id": "msg_fallback",
                            "model": "anthropic-fixture",
                            "content": [{"type": "text", "text": structured(ref)}],
                            "usage": {"input_tokens": 25, "output_tokens": 15},
                        },
                    ),
                    response(
                        200,
                        {
                            "id": "msg_fallback_2",
                            "model": "anthropic-fixture",
                            "content": [{"type": "text", "text": structured(ref)}],
                            "usage": {"input_tokens": 25, "output_tokens": 15},
                        },
                    ),
                    response(
                        200,
                        {
                            "id": "msg_fallback_3",
                            "model": "anthropic-fixture",
                            "content": [{"type": "text", "text": structured(ref)}],
                            "usage": {"input_tokens": 25, "output_tokens": 15},
                        },
                    ),
                ]
            )
            registry = CapabilityRegistry.from_environment(
                transports={
                    "openai.configured": openai,
                    "anthropic.configured": anthropic,
                }
            )
            result = Orchestrator(root / "runs", capability_registry=registry).run(request)
            run_dir = Path(result.artifact_dir)
            routes = json.loads((run_dir / "routing_decisions.json").read_text())
            report = (run_dir / "final_report.md").read_text()

        synthesis = next(item for item in routes if item["task_id"] == "T-SYNTHESIS")
        self.assertEqual(synthesis["provider_id"], "anthropic.configured")
        self.assertEqual(len(openai.requests), 1)
        self.assertEqual(len(anthropic.requests), 4)
        self.assertIn("openai.configured", report)
        self.assertIn("degraded", report.lower())

    def test_all_hosted_models_down_uses_local_extractive_mode_with_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Local extractive evidence remains available.")
            transport = FakeTransport([response(503, {"error": "down"})])
            registry = CapabilityRegistry.from_environment(
                transports={"openai.configured": transport}
            )
            result = Orchestrator(root / "runs", capability_registry=registry).run(
                invocation(source)
            )
            report = (Path(result.artifact_dir) / "final_report.md").read_text()

        self.assertIn("Synthesis path: `extractive`", report)
        self.assertIn("openai.configured", report)
        self.assertIn("unavailable", report.lower())

    def test_ollama_uses_same_health_transport_and_zero_cost_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            "os.environ",
            {"OLLAMA_BASE_URL": "http://ollama.fixture", "OLLAMA_MODEL": "local-fixture"},
            clear=True,
        ):
            root = Path(tmp)
            source = root / "source.md"
            source.write_text("Provider fallback evidence is grounded locally.")
            request = HostInvocation(
                prompt="Produce a grounded local model report",
                attachments=[InputAttachment(uri=str(source))],
            )
            ref = chunk_id(source, request)
            transport = FakeTransport(
                [
                    response(200, {"models": []}),
                    response(
                        200,
                        {
                            "model": "local-fixture",
                            "response": structured(ref),
                            "prompt_eval_count": 20,
                            "eval_count": 10,
                        },
                    ),
                    response(
                        200,
                        {
                            "model": "local-fixture",
                            "response": structured(ref),
                            "prompt_eval_count": 20,
                            "eval_count": 10,
                        },
                    ),
                    response(
                        200,
                        {
                            "model": "local-fixture",
                            "response": structured(ref),
                            "prompt_eval_count": 20,
                            "eval_count": 10,
                        },
                    ),
                ]
            )
            registry = CapabilityRegistry.from_environment(
                transports={"ollama.local": transport}
            )
            result = Orchestrator(root / "runs", capability_registry=registry).run(request)
            ledger = json.loads(
                (Path(result.artifact_dir) / "cost_ledger.json").read_text()
            )

        self.assertEqual(len(transport.requests), 4)
        self.assertEqual(ledger["calls"][0]["provider_id"], "ollama.local")
        self.assertEqual(ledger["calls"][0]["actual_usd"], 0)

    def test_pause_reason_names_capability_and_configuration_action(self) -> None:
        task = TaskNode(
            id="T-PAUSE",
            run_id="R-PAUSE",
            title="Unavailable semantic work",
            task_type=TaskType.FINAL_SYNTHESIS,
            required_capabilities={"semantic_entailment": 0.9},
            fallback_policy=FallbackPolicy(allow_task_reshape=False),
        )

        decision = AdaptiveRouter(CapabilityRegistry([])).route(task)

        self.assertEqual(decision.action, "pause")
        self.assertIn("semantic_entailment", decision.reason)
        self.assertIn("configure", decision.reason.lower())


if __name__ == "__main__":
    unittest.main()
