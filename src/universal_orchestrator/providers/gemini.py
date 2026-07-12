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


class GeminiAdapter(JSONHTTPMixin, ProviderAdapter):
    """Google Gemini API adapter using an AI Studio API key."""

    def execute(self, task: ProviderTask) -> ProviderResult:
        api_key = os.getenv("GOOGLE_API_KEY")
        model = os.getenv("GEMINI_MODEL")
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com").rstrip("/")
        payload = self._payload(task, model or "GEMINI_MODEL")
        if task.dry_run or not task.allow_network:
            return dry_run_result(
                self.id,
                payload,
                "Gemini request prepared in dry-run mode; no network call was made.",
                self.estimate_cost(task),
            )
        if not api_key:
            return unavailable_result(self.id, "GOOGLE_API_KEY is not configured.")
        if not model:
            return unavailable_result(self.id, "GEMINI_MODEL is not configured.")
        self._active_model = model
        cost_estimate, authorization = self.authorize_cost(task, model)
        try:
            response = self._post_json(
                f"{base_url}/v1beta/models/{model}:generateContent",
                payload,
                {"x-goog-api-key": api_key},
                task.timeout_seconds,
            )
        except Exception:
            self.release_cost(authorization)
            raise
        usage = self._usage(response)
        self.commit_cost(authorization, usage)
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.COMPLETED,
            output={"summary": self._extract_text(response), "model": model, "usage": usage},
            cost_estimate=cost_estimate,
        )

    def _payload(self, task: ProviderTask, model: str) -> dict[str, Any]:
        del model
        return {
            "contents": [{"role": "user", "parts": [{"text": render_provider_prompt(task)}]}],
            "generationConfig": {"maxOutputTokens": self.estimated_output_tokens(task)},
        }

    def _extract_text(self, response: dict[str, Any]) -> str:
        candidates = response.get("candidates")
        if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
            content = candidates[0].get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
                    return "\n".join(text for text in texts if isinstance(text, str)).strip()
        return "Gemini response completed without extractable text."

    def _usage(self, response: dict[str, Any]) -> dict[str, int]:
        usage_value = response.get("usageMetadata")
        usage = usage_value if isinstance(usage_value, dict) else {}
        input_tokens = int(usage.get("promptTokenCount", 0) or 0)
        output_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": int(usage.get("totalTokenCount", input_tokens + output_tokens) or 0),
        }


def build_adapter(descriptor: ProviderDescriptor) -> GeminiAdapter:
    return GeminiAdapter(descriptor)
