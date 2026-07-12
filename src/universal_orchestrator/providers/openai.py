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
from universal_orchestrator.security import redact_text


class OpenAIResponsesAdapter(JSONHTTPMixin, ProviderAdapter):
    """OpenAI Responses API adapter.

    The adapter is permission-gated: no network call is made unless the task allows network access,
    dry_run is false, and OPENAI_API_KEY plus OPENAI_MODEL are configured.
    """

    def execute(self, task: ProviderTask) -> ProviderResult:
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_MODEL")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload = self._payload(task, model or "OPENAI_MODEL")

        if task.dry_run or not task.allow_network:
            return dry_run_result(
                self.id,
                self._safe_payload(payload),
                "OpenAI request prepared in dry-run mode; no network call was made.",
                self.estimate_cost(task),
            )
        if not api_key:
            return unavailable_result(self.id, "OPENAI_API_KEY is not configured.")
        if not model:
            return unavailable_result(self.id, "OPENAI_MODEL is not configured.")

        self._active_model = model
        cost_estimate, authorization = self.authorize_cost(task, model)
        capacity_authorization = None
        try:
            capacity_authorization = self.authorize_capacity(task, model, cost_estimate)
            response = self._post_json(
                f"{base_url}/responses",
                payload,
                {"Authorization": f"Bearer {api_key}"},
                task.timeout_seconds,
            )
        except Exception:
            self.release_capacity(capacity_authorization)
            self.release_cost(authorization)
            raise
        usage = self._usage(response)
        self.commit_cost(authorization, usage)
        self.commit_capacity(capacity_authorization)
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.COMPLETED,
            output={
                "summary": self._extract_output_text(response),
                "raw_response_id": response.get("id"),
                "model": response.get("model", model),
                "usage": usage,
            },
            cost_estimate=cost_estimate,
        )

    def _payload(self, task: ProviderTask, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "input": [
                {
                    "role": "developer",
                    "content": "You are a worker inside a larger orchestration kernel. Return concise structured output.",
                },
                {
                    "role": "user",
                    "content": self._prompt(task),
                },
            ],
            "store": False,
            "max_output_tokens": self.estimated_output_tokens(task),
        }

    def _prompt(self, task: ProviderTask) -> str:
        return render_provider_prompt(task)

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        redacted = self._redact_value(payload)
        if not isinstance(redacted, dict):
            raise TypeError("Redacted provider payload must remain a JSON object")
        return redacted

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return redact_text(value)
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._redact_value(item) for key, item in value.items()}
        return value

    def _extract_output_text(self, response: dict[str, Any]) -> str:
        output_text = response.get("output_text")
        if isinstance(output_text, str):
            return output_text
        texts: list[str] = []
        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content_items = item.get("content")
                if not isinstance(content_items, list):
                    continue
                for content in content_items:
                    if not isinstance(content, dict):
                        continue
                    text = content.get("text")
                    if content.get("type") == "output_text" and isinstance(text, str):
                        texts.append(text)
        return "\n".join(texts).strip() or "OpenAI response completed without extractable output_text."

    def _usage(self, response: dict[str, Any]) -> dict[str, int]:
        usage_value = response.get("usage")
        usage = usage_value if isinstance(usage_value, dict) else {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": int(usage.get("total_tokens", input_tokens + output_tokens) or 0),
        }


def build_adapter(descriptor: ProviderDescriptor) -> OpenAIResponsesAdapter:
    return OpenAIResponsesAdapter(descriptor)
