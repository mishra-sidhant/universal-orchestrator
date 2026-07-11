from __future__ import annotations

import json
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.cli import build_parser, handle_smoke
from universal_orchestrator.models import (
    CostTier,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    ProviderTask,
    TaskNode,
    TaskType,
)
from universal_orchestrator.providers.anthropic import AnthropicAdapter
from universal_orchestrator.providers.base import (
    ProviderAdapterRegistry,
    ProviderError,
    ProviderErrorKind,
)
from universal_orchestrator.providers.ollama import OllamaAdapter
from universal_orchestrator.providers.openai import OpenAIResponsesAdapter
from universal_orchestrator.providers.transport import (
    FakeTransport,
    HTTPResponse,
    TransportTimeout,
)


FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "provider_responses.json").read_text()
)


def response(name: str) -> HTTPResponse:
    fixture = FIXTURES[name]
    body = fixture.get("raw_body")
    if body is None:
        body = json.dumps(fixture["body"])
    return HTTPResponse(
        status_code=fixture["status_code"],
        headers=fixture["headers"],
        body=body.encode(),
    )


def descriptor(provider_id: str, kind: ProviderKind = ProviderKind.HOSTED_MODEL) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=provider_id,
        kind=kind,
        enabled=True,
        capabilities={"final_synthesis": 1.0},
        cost_tier=CostTier.PREMIUM,
        health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
    )


def provider_task(timeout_seconds: int = 7) -> ProviderTask:
    return ProviderTask(
        task=TaskNode(
            id="T-LIVE",
            run_id="R-LIVE",
            title="Synthesize",
            task_type=TaskType.FINAL_SYNTHESIS,
        ),
        prompt="Return a tiny result",
        dry_run=False,
        allow_network=True,
        timeout_seconds=timeout_seconds,
    )


class TrancheF1TransportTests(unittest.TestCase):
    def test_all_adapters_use_injected_transport_and_capture_usage(self) -> None:
        cases = [
            (
                OpenAIResponsesAdapter,
                "openai.configured",
                "openai_success",
                {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
                (11, 7, 18),
            ),
            (
                AnthropicAdapter,
                "anthropic.configured",
                "anthropic_success",
                {"ANTHROPIC_API_KEY": "fixture-key", "ANTHROPIC_MODEL": "fixture-model"},
                (13, 5, 18),
            ),
            (
                OllamaAdapter,
                "ollama.local",
                "ollama_success",
                {"OLLAMA_MODEL": "fixture-model"},
                (17, 6, 23),
            ),
        ]
        for adapter_type, provider_id, fixture, environment, expected_usage in cases:
            with self.subTest(provider=provider_id), patch.dict("os.environ", environment, clear=True):
                transport = FakeTransport([response(fixture)])
                adapter = adapter_type(descriptor(provider_id), transport=transport)
                result = adapter.execute(provider_task())

            usage = result.output["usage"]
            self.assertEqual(
                (usage["input_tokens"], usage["output_tokens"], usage["total_tokens"]),
                expected_usage,
            )
            self.assertEqual(len(transport.requests), 1)
            self.assertEqual(transport.requests[0].timeout_seconds, 7)

    def test_rate_limit_honors_retry_after_and_then_succeeds(self) -> None:
        delays: list[float] = []
        transport = FakeTransport([response("rate_limit"), response("openai_success")])
        adapter = OpenAIResponsesAdapter(
            descriptor("openai.configured"),
            transport=transport,
            sleeper=delays.append,
            jitter=lambda: 0.0,
        )
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            result = adapter.execute(provider_task())

        self.assertEqual(result.output["summary"], "OpenAI fixture result")
        self.assertEqual(delays, [2.0])
        self.assertEqual(len(transport.requests), 2)

    def test_transient_5xx_and_timeout_retry_with_bounded_attempts(self) -> None:
        for first_failure, expected_kind in (
            (response("server_error"), ProviderErrorKind.TRANSIENT),
            (TransportTimeout("socket timed out"), ProviderErrorKind.TIMEOUT),
        ):
            with self.subTest(kind=expected_kind):
                transport = FakeTransport([first_failure, first_failure, first_failure])
                adapter = OpenAIResponsesAdapter(
                    descriptor("openai.configured"),
                    transport=transport,
                    sleeper=lambda _: None,
                    jitter=lambda: 0.0,
                )
                with patch.dict(
                    "os.environ",
                    {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
                    clear=True,
                ), self.assertRaises(ProviderError) as caught:
                    adapter.execute(provider_task())

                self.assertEqual(caught.exception.kind, expected_kind)
                self.assertEqual(len(transport.requests), 3)

    def test_auth_fatal_and_malformed_fail_without_retry(self) -> None:
        for fixture, expected_kind in (
            ("auth_error", ProviderErrorKind.AUTH),
            ("fatal_error", ProviderErrorKind.FATAL),
            ("malformed_success", ProviderErrorKind.MALFORMED_OUTPUT),
        ):
            with self.subTest(fixture=fixture):
                transport = FakeTransport([response(fixture)])
                adapter = OpenAIResponsesAdapter(
                    descriptor("openai.configured"),
                    transport=transport,
                    sleeper=lambda _: None,
                )
                with patch.dict(
                    "os.environ",
                    {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
                    clear=True,
                ), self.assertRaises(ProviderError) as caught:
                    adapter.execute(provider_task())

                self.assertEqual(caught.exception.kind, expected_kind)
                self.assertEqual(len(transport.requests), 1)
                self.assertIn("openai.configured", str(caught.exception))

    def test_smoke_command_is_explicit_and_reports_round_trip_metrics(self) -> None:
        args = build_parser().parse_args(["smoke", "--provider", "openai.configured"])
        self.assertIs(args.handler, handle_smoke)
        self.assertEqual(args.provider, "openai.configured")
        provider = descriptor("openai.configured")
        transport = FakeTransport([response("openai_success")])

        class FixtureRegistry:
            providers = [provider]
            cost_ledger = None

            def adapter_registry(self) -> ProviderAdapterRegistry:
                return ProviderAdapterRegistry(
                    [
                        OpenAIResponsesAdapter(
                            provider,
                            transport=transport,
                            cost_ledger=self.cost_ledger,
                        )
                    ]
                )

        output = io.StringIO()
        with patch(
            "universal_orchestrator.cli.CapabilityRegistry.from_environment",
            return_value=FixtureRegistry(),
        ), patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ), redirect_stdout(output):
            handle_smoke(args)

        payload = json.loads(output.getvalue())
        self.assertEqual(payload["provider"], "openai.configured")
        self.assertEqual(payload["usage"]["total_tokens"], 18)
        self.assertAlmostEqual(payload["actual_cost_usd"], 0.00016)
        self.assertTrue(payload["response_received"])
        self.assertEqual(len(transport.requests), 1)


if __name__ == "__main__":
    unittest.main()
