from __future__ import annotations

import os
from typing import Any

from universal_orchestrator.models import ProviderDescriptor, ProviderResult, ProviderTask, TaskStatus
from universal_orchestrator.providers.base import (
    JSONHTTPMixin,
    ProviderAdapter,
    dry_run_result,
    render_provider_prompt,
    unavailable_result,
)


class AnthropicAdapter(JSONHTTPMixin, ProviderAdapter):
    def execute(self, task: ProviderTask) -> ProviderResult:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        model = os.getenv("ANTHROPIC_MODEL")
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        version = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
        payload = self._payload(task, model or "ANTHROPIC_MODEL")

        if task.dry_run or not task.allow_network:
            return dry_run_result(
                self.id,
                payload,
                "Anthropic request prepared in dry-run mode; no network call was made.",
                self.estimate_cost(task),
            )
        if not api_key:
            return unavailable_result(self.id, "ANTHROPIC_API_KEY is not configured.")
        if not model:
            return unavailable_result(self.id, "ANTHROPIC_MODEL is not configured.")

        response = self._post_json(
            f"{base_url}/v1/messages",
            payload,
            {"x-api-key": api_key, "anthropic-version": version},
            task.timeout_seconds,
        )
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.COMPLETED,
            output={
                "summary": self._extract_output_text(response),
                "raw_response_id": response.get("id"),
                "model": response.get("model", model),
                "usage": self._usage(response),
            },
        )

    def _payload(self, task: ProviderTask, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "max_tokens": self._max_tokens(),
            "system": "You are a worker inside a larger orchestration kernel. Return concise structured output.",
            "messages": [
                {
                    "role": "user",
                    "content": render_provider_prompt(task),
                }
            ],
        }

    def _max_tokens(self) -> int:
        try:
            return max(1, int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")))
        except ValueError:
            return 4096

    def estimated_output_tokens(self, task: ProviderTask) -> int:
        del task
        return self._max_tokens()

    def _extract_output_text(self, response: dict[str, Any]) -> str:
        texts = [
            item.get("text", "")
            for item in response.get("content", []) or []
            if item.get("type") == "text"
        ]
        return "\n".join(text for text in texts if text).strip() or "Anthropic response completed without text content."

    def _usage(self, response: dict[str, Any]) -> dict[str, int]:
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }


def build_adapter(descriptor: ProviderDescriptor) -> AnthropicAdapter:
    return AnthropicAdapter(descriptor)
