from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from time import sleep
from typing import Any

from universal_orchestrator.models import (
    CostEstimate,
    ProviderDescriptor,
    ProviderHealth,
    ProviderResult,
    ProviderStatus,
    ProviderTask,
    TaskStatus,
)
from universal_orchestrator.security import redact_text
from universal_orchestrator.utils import estimate_tokens


class ProviderAdapter(ABC):
    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self.descriptor = descriptor

    @property
    def id(self) -> str:
        return self.descriptor.id

    def health_check(self) -> ProviderHealth:
        return self.descriptor.health

    def estimate_cost(self, task: ProviderTask) -> CostEstimate:
        input_tokens = estimate_tokens(render_provider_prompt(task))
        output_tokens = self.estimated_output_tokens(task)
        return CostEstimate(
            tier=self.descriptor.cost_tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_tokens=input_tokens + output_tokens,
        )

    def estimated_output_tokens(self, task: ProviderTask) -> int:
        del task
        return 1_024

    def supports(self, requirements: dict[str, float]) -> bool:
        return self.descriptor.supports(requirements)

    @abstractmethod
    def execute(self, task: ProviderTask) -> ProviderResult:
        raise NotImplementedError


class ProviderAdapterRegistry:
    def __init__(self, adapters: list[ProviderAdapter]) -> None:
        self.adapters = {adapter.id: adapter for adapter in adapters}

    def get(self, provider_id: str | None) -> ProviderAdapter | None:
        if provider_id is None:
            return None
        return self.adapters.get(provider_id)

    def require(self, provider_id: str) -> ProviderAdapter:
        adapter = self.get(provider_id)
        if adapter is None:
            raise KeyError(f"No provider adapter registered for {provider_id}")
        return adapter


class JSONHTTPMixin:
    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: int,
        max_attempts: int = 3,
        backoff_seconds: float = 0.25,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        attempts = max(1, max_attempts)
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                    response_body = response.read().decode("utf-8")
                return json.loads(response_body)
            except urllib.error.HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if retryable and attempt < attempts:
                    sleep(backoff_seconds * (2 ** (attempt - 1)))
                    continue
                raise RuntimeError(f"Provider HTTP {exc.code}: {error_body}") from exc
        raise RuntimeError("Provider request exhausted retry attempts.")


def unavailable_result(provider_id: str, message: str) -> ProviderResult:
    return ProviderResult(
        provider_id=provider_id,
        status=TaskStatus.SKIPPED,
        output={"summary": message},
        warnings=[message],
    )


def dry_run_result(
    provider_id: str,
    payload: dict[str, Any],
    message: str,
    cost_estimate: CostEstimate | None = None,
) -> ProviderResult:
    estimated_tokens = cost_estimate.estimated_tokens if cost_estimate else 0
    return ProviderResult(
        provider_id=provider_id,
        status=TaskStatus.COMPLETED,
        output={
            "summary": message,
            "dry_run": True,
            "request_preview": _redact_value(payload),
            "usage": {
                "input_tokens": cost_estimate.input_tokens if cost_estimate else 0,
                "output_tokens": cost_estimate.output_tokens if cost_estimate else 0,
                "total_tokens": estimated_tokens,
                "estimated": True,
            },
        },
        cost_estimate=cost_estimate,
    )


def render_provider_prompt(task: ProviderTask) -> str:
    pack = task.context.get("context_pack")
    bounded_pack = _bounded_context_pack(pack) if isinstance(pack, dict) else pack
    context_text = (
        json.dumps(bounded_pack, sort_keys=True, default=str)
        if bounded_pack
        else "No context pack supplied."
    )
    return (
        f"Task: {task.task.title}\n"
        f"Type: {task.task.task_type}\n"
        f"Context pack: {context_text}\n"
        f"Prompt: {task.prompt}"
    )


def _bounded_context_pack(pack: dict[str, Any]) -> dict[str, Any]:
    budget = max(0, int(pack.get("token_budget", 0)))
    used = 0
    bounded = {key: value for key, value in pack.items() if key not in {"cards", "chunks"}}
    for collection_name in ("chunks", "cards"):
        selected: list[Any] = []
        for item in pack.get(collection_name, []) or []:
            if not isinstance(item, dict):
                continue
            tokens = max(0, int(item.get("token_estimate", 0)))
            if used + tokens > budget:
                continue
            selected.append(item)
            used += tokens
        bounded[collection_name] = selected
    bounded["used_tokens"] = used
    return bounded


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_value(item) for key, item in value.items()}
    return value


def health_from_enabled(enabled: bool, configured_message: str, missing_message: str) -> ProviderHealth:
    if enabled:
        return ProviderHealth(
            status=ProviderStatus.HEALTHY,
            reliability_score=0.85,
            message=configured_message,
        )
    return ProviderHealth(
        status=ProviderStatus.UNAVAILABLE,
        reliability_score=0.0,
        message=missing_message,
    )
