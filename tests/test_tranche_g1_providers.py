from __future__ import annotations

import json
import unittest
from unittest.mock import patch

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
from universal_orchestrator.providers.gemini import GeminiAdapter
from universal_orchestrator.providers.openai_compatible import OpenAICompatibleChatAdapter
from universal_orchestrator.providers.transport import FakeTransport, HTTPResponse


def task() -> ProviderTask:
    return ProviderTask(
        task=TaskNode(id="T", run_id="R", title="Synthesize", task_type=TaskType.FINAL_SYNTHESIS),
        prompt="Return a compact result",
        dry_run=False,
        allow_network=True,
    )


def descriptor(provider_id: str) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=provider_id,
        kind=ProviderKind.HOSTED_MODEL,
        enabled=True,
        capabilities={"final_synthesis": 1.0},
        cost_tier=CostTier.PREMIUM,
        health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
    )


class FrontierProviderTests(unittest.TestCase):
    def test_gemini_captures_text_and_usage_without_key_in_url(self) -> None:
        transport = FakeTransport(
            [
                HTTPResponse(
                    status_code=200,
                    headers={},
                    body=json.dumps(
                        {
                            "candidates": [
                                {"content": {"parts": [{"text": "Gemini result"}]}}
                            ],
                            "usageMetadata": {
                                "promptTokenCount": 8,
                                "candidatesTokenCount": 4,
                                "totalTokenCount": 12,
                            },
                        }
                    ).encode(),
                )
            ]
        )
        adapter = GeminiAdapter(descriptor("gemini.configured"), transport=transport)
        with patch.dict(
            "os.environ",
            {"GOOGLE_API_KEY": "fixture-secret", "GEMINI_MODEL": "gemini-fixture"},
            clear=True,
        ):
            result = adapter.execute(task())

        self.assertEqual(result.output["summary"], "Gemini result")
        self.assertEqual(result.output["usage"]["total_tokens"], 12)
        self.assertNotIn("fixture-secret", transport.requests[0].url)
        self.assertEqual(transport.requests[0].headers["x-goog-api-key"], "fixture-secret")

    def test_openai_compatible_adapter_captures_chat_usage(self) -> None:
        transport = FakeTransport(
            [
                HTTPResponse(
                    status_code=200,
                    headers={},
                    body=json.dumps(
                        {
                            "model": "grok-fixture",
                            "choices": [{"message": {"content": "Compatible result"}}],
                            "usage": {
                                "prompt_tokens": 9,
                                "completion_tokens": 3,
                                "total_tokens": 12,
                            },
                        }
                    ).encode(),
                )
            ]
        )
        adapter = OpenAICompatibleChatAdapter(
            descriptor("xai.configured"),
            api_key_env="XAI_API_KEY",
            model_env="XAI_MODEL",
            base_url_env="XAI_BASE_URL",
            default_base_url="https://api.x.ai/v1",
            transport=transport,
        )
        with patch.dict(
            "os.environ",
            {"XAI_API_KEY": "fixture-secret", "XAI_MODEL": "grok-fixture"},
            clear=True,
        ):
            result = adapter.execute(task())

        self.assertEqual(result.output["summary"], "Compatible result")
        self.assertEqual(result.output["usage"]["input_tokens"], 9)
        self.assertTrue(transport.requests[0].url.endswith("/chat/completions"))


if __name__ == "__main__":
    unittest.main()
