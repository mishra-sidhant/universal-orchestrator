from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
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


class ProviderAdapter(ABC):
    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self.descriptor = descriptor

    @property
    def id(self) -> str:
        return self.descriptor.id

    def health_check(self) -> ProviderHealth:
        return self.descriptor.health

    def estimate_cost(self, task: ProviderTask) -> CostEstimate:
        tokens = len(task.prompt.split()) * 2 + 256
        return CostEstimate(tier=self.descriptor.cost_tier, estimated_tokens=tokens)

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
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Provider HTTP {exc.code}: {error_body}") from exc
        return json.loads(response_body)


def unavailable_result(provider_id: str, message: str) -> ProviderResult:
    return ProviderResult(
        provider_id=provider_id,
        status=TaskStatus.SKIPPED,
        output={"summary": message},
        warnings=[message],
    )


def dry_run_result(provider_id: str, payload: dict[str, Any], message: str) -> ProviderResult:
    return ProviderResult(
        provider_id=provider_id,
        status=TaskStatus.COMPLETED,
        output={
            "summary": message,
            "dry_run": True,
            "request_preview": payload,
        },
    )


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
