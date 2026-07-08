from __future__ import annotations

import os
from typing import Any

from universal_orchestrator.models import ProviderDescriptor, ProviderResult, ProviderTask, TaskStatus
from universal_orchestrator.providers.base import JSONHTTPMixin, ProviderAdapter, dry_run_result, unavailable_result


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
            )
        if not api_key:
            return unavailable_result(self.id, "OPENAI_API_KEY is not configured.")
        if not model:
            return unavailable_result(self.id, "OPENAI_MODEL is not configured.")

        response = self._post_json(
            f"{base_url}/responses",
            payload,
            {"Authorization": f"Bearer {api_key}"},
            task.timeout_seconds,
        )
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.COMPLETED,
            output={
                "summary": self._extract_output_text(response),
                "raw_response_id": response.get("id"),
                "model": response.get("model", model),
            },
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
        }

    def _prompt(self, task: ProviderTask) -> str:
        context = task.context.get("summary", "")
        return f"Task: {task.task.title}\nType: {task.task.task_type}\nContext: {context}\nPrompt: {task.prompt}"

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def _extract_output_text(self, response: dict[str, Any]) -> str:
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        texts: list[str] = []
        for item in response.get("output", []) or []:
            for content in item.get("content", []) or []:
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    texts.append(content["text"])
        return "\n".join(texts).strip() or "OpenAI response completed without extractable output_text."


def build_adapter(descriptor: ProviderDescriptor) -> OpenAIResponsesAdapter:
    return OpenAIResponsesAdapter(descriptor)

