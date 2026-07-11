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


class OllamaAdapter(JSONHTTPMixin, ProviderAdapter):
    def execute(self, task: ProviderTask) -> ProviderResult:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL")
        payload = self._payload(task, model or "OLLAMA_MODEL")

        if task.dry_run or not task.allow_network:
            return dry_run_result(
                self.id,
                payload,
                "Ollama request prepared in dry-run mode; no network call was made.",
                self.estimate_cost(task),
            )
        if not model:
            return unavailable_result(self.id, "OLLAMA_MODEL is not configured.")

        cost_estimate, authorization = self.authorize_cost(task, model)
        try:
            response = self._post_json(
                f"{base_url}/api/generate",
                payload,
                {},
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
            output={
                "summary": response.get("response", "Ollama response completed without text response."),
                "model": response.get("model", model),
                "usage": usage,
            },
            cost_estimate=cost_estimate,
        )

    def _payload(self, task: ProviderTask, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "stream": False,
            "prompt": render_provider_prompt(task),
            "options": {"num_predict": self.estimated_output_tokens(task)},
        }

    def _usage(self, response: dict[str, Any]) -> dict[str, int]:
        input_tokens = int(response.get("prompt_eval_count", 0) or 0)
        output_tokens = int(response.get("eval_count", 0) or 0)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }


def build_adapter(descriptor: ProviderDescriptor) -> OllamaAdapter:
    return OllamaAdapter(descriptor)
