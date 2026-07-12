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


class OpenAICompatibleChatAdapter(JSONHTTPMixin, ProviderAdapter):
    """Chat-completions adapter for xAI and OpenAI-compatible local gateways."""

    def __init__(
        self,
        descriptor: ProviderDescriptor,
        *,
        api_key_env: str,
        model_env: str,
        base_url_env: str,
        default_base_url: str,
        transport: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(descriptor, transport=transport, **kwargs)
        self.api_key_env = api_key_env
        self.model_env = model_env
        self.base_url_env = base_url_env
        self.default_base_url = default_base_url

    def execute(self, task: ProviderTask) -> ProviderResult:
        api_key = os.getenv(self.api_key_env)
        model = os.getenv(self.model_env)
        base_url = os.getenv(self.base_url_env, self.default_base_url).rstrip("/")
        payload = self._payload(task, model or self.model_env)
        if task.dry_run or not task.allow_network:
            return dry_run_result(
                self.id,
                payload,
                f"{self.id} request prepared in dry-run mode; no network call was made.",
                self.estimate_cost(task),
            )
        if not api_key:
            return unavailable_result(self.id, f"{self.api_key_env} is not configured.")
        if not model:
            return unavailable_result(self.id, f"{self.model_env} is not configured.")
        self._active_model = model
        cost_estimate, authorization = self.authorize_cost(task, model)
        capacity_authorization = None
        try:
            capacity_authorization = self.authorize_capacity(task, model, cost_estimate)
            response = self._post_json(
                f"{base_url}/chat/completions",
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
                "summary": self._extract_text(response),
                "model": response.get("model", model),
                "usage": usage,
            },
            cost_estimate=cost_estimate,
        )

    def _payload(self, task: ProviderTask, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a worker inside a larger orchestration kernel. Return concise structured output.",
                },
                {"role": "user", "content": render_provider_prompt(task)},
            ],
            "stream": False,
            "max_tokens": self.estimated_output_tokens(task),
        }

    def _extract_text(self, response: dict[str, Any]) -> str:
        choices = response.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
        return "Provider response completed without extractable text."

    def _usage(self, response: dict[str, Any]) -> dict[str, int]:
        usage_value = response.get("usage")
        usage = usage_value if isinstance(usage_value, dict) else {}
        input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        output_tokens = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": int(usage.get("total_tokens", input_tokens + output_tokens) or 0),
        }


def build_xai_adapter(descriptor: ProviderDescriptor) -> OpenAICompatibleChatAdapter:
    return OpenAICompatibleChatAdapter(
        descriptor,
        api_key_env="XAI_API_KEY",
        model_env="XAI_MODEL",
        base_url_env="XAI_BASE_URL",
        default_base_url="https://api.x.ai/v1",
    )


def build_generic_adapter(descriptor: ProviderDescriptor) -> OpenAICompatibleChatAdapter:
    return OpenAICompatibleChatAdapter(
        descriptor,
        api_key_env="OPENAI_COMPATIBLE_API_KEY",
        model_env="OPENAI_COMPATIBLE_MODEL",
        base_url_env="OPENAI_COMPATIBLE_BASE_URL",
        default_base_url="http://127.0.0.1:8000/v1",
    )
