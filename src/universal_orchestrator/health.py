from __future__ import annotations

import json
import os
from time import monotonic
from typing import Callable

from universal_orchestrator.models import (
    ProviderDescriptor,
    ProviderHealth,
    ProviderStatus,
)
from universal_orchestrator.providers.transport import (
    HTTPRequest,
    HTTPTransport,
    TransportConnectionError,
    TransportTimeout,
)


class ProviderHealthChecker:
    def __init__(
        self,
        ttl_seconds: float = 60.0,
        timeout_seconds: float = 5.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.clock = clock
        self._cache: dict[str, tuple[float, ProviderHealth]] = {}

    def check(
        self,
        descriptor: ProviderDescriptor,
        transport: HTTPTransport,
    ) -> ProviderHealth:
        now = self.clock()
        cached = self._cache.get(descriptor.id)
        if cached and cached[0] > now:
            return cached[1]
        request = self._request(descriptor.id)
        started = self.clock()
        try:
            response = transport.send(request)
            latency_ms = max(0, round((self.clock() - started) * 1_000))
            health = self._classify(descriptor.id, response.status_code, response.body, latency_ms)
        except (TransportTimeout, TransportConnectionError) as exc:
            health = ProviderHealth(
                status=ProviderStatus.UNAVAILABLE,
                reliability_score=0.0,
                message=f"Liveness probe failed: {type(exc).__name__}.",
            )
        self._cache[descriptor.id] = (now + self.ttl_seconds, health)
        return health

    def _request(self, provider_id: str) -> HTTPRequest:
        if provider_id == "openai.configured":
            base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}"}
            url = f"{base}/models"
        elif provider_id == "anthropic.configured":
            base = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
            headers = {
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
            }
            url = f"{base}/v1/models"
        elif provider_id == "ollama.local":
            base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
            headers = {}
            url = f"{base}/api/tags"
        elif provider_id == "gemini.configured":
            base = os.getenv(
                "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"
            ).rstrip("/")
            api_key = os.getenv("GOOGLE_API_KEY", "")
            headers = {"x-goog-api-key": api_key} if api_key else {}
            url = f"{base}/v1beta/models"
        elif provider_id == "xai.configured":
            base = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
            api_key = os.getenv("XAI_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            url = f"{base}/models"
        elif provider_id == "openai-compatible.local":
            base = os.getenv(
                "OPENAI_COMPATIBLE_BASE_URL", "http://127.0.0.1:8000/v1"
            ).rstrip("/")
            api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            url = f"{base}/models"
        else:
            raise ValueError(f"No liveness endpoint configured for {provider_id}")
        return HTTPRequest(
            method="GET",
            url=url,
            headers=headers,
            timeout_seconds=self.timeout_seconds,
        )

    def _classify(
        self,
        provider_id: str,
        status_code: int,
        body: bytes,
        latency_ms: int,
    ) -> ProviderHealth:
        if 200 <= status_code < 300:
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return ProviderHealth(
                    status=ProviderStatus.DEGRADED,
                    latency_ms=latency_ms,
                    reliability_score=0.4,
                    message="Liveness endpoint returned malformed JSON.",
                )
            if not isinstance(payload, dict):
                return ProviderHealth(
                    status=ProviderStatus.DEGRADED,
                    latency_ms=latency_ms,
                    reliability_score=0.4,
                    message="Liveness endpoint returned an unexpected JSON shape.",
                )
            return ProviderHealth(
                status=ProviderStatus.HEALTHY,
                latency_ms=latency_ms,
                reliability_score=0.9,
                message=f"Measured {provider_id} liveness probe succeeded.",
            )
        if status_code == 429:
            return ProviderHealth(
                status=ProviderStatus.DEGRADED,
                latency_ms=latency_ms,
                reliability_score=0.3,
                message="Liveness probe was rate-limited.",
            )
        return ProviderHealth(
            status=ProviderStatus.UNAVAILABLE,
            latency_ms=latency_ms,
            reliability_score=0.0,
            message=f"Liveness probe failed with HTTP {status_code}.",
        )
