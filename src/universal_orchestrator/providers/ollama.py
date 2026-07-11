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

        response = self._post_json(
            f"{base_url}/api/generate",
            payload,
            {},
            task.timeout_seconds,
        )
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.COMPLETED,
            output={
                "summary": response.get("response", "Ollama response completed without text response."),
                "model": response.get("model", model),
            },
        )

    def _payload(self, task: ProviderTask, model: str) -> dict[str, Any]:
        return {
            "model": model,
            "stream": False,
            "prompt": render_provider_prompt(task),
        }


def build_adapter(descriptor: ProviderDescriptor) -> OllamaAdapter:
    return OllamaAdapter(descriptor)
