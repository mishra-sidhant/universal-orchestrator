from __future__ import annotations

import os

from universal_orchestrator.models import (
    CostTier,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderStatus,
    RoutingAction,
    RoutingDecision,
    TaskNode,
)


COST_ORDER = {
    CostTier.FREE: 0,
    CostTier.CHEAP: 1,
    CostTier.MEDIUM: 2,
    CostTier.PREMIUM: 3,
}


class CapabilityRegistry:
    def __init__(self, providers: list[ProviderDescriptor]) -> None:
        self.providers = providers

    @classmethod
    def from_environment(cls) -> "CapabilityRegistry":
        providers = [
            ProviderDescriptor(
                id="deterministic.tools",
                kind=ProviderKind.DETERMINISTIC_TOOL,
                enabled=True,
                capabilities={
                    "file_io": 1.0,
                    "artifact_build": 0.95,
                    "artifact_validation": 0.95,
                    "contract_validation": 0.9,
                    "routing": 0.85,
                    "security_review": 0.75,
                    "summarization": 0.6,
                    "classification": 0.65,
                    "structured_output": 0.8,
                    "decomposition": 0.55,
                    "strategic_reasoning": 0.5,
                    "final_synthesis": 0.55,
                    "code_reasoning": 0.55,
                    "repo_navigation": 0.7,
                    "code_review": 0.55,
                    "research": 0.55,
                    "citation_discipline": 0.5,
                    "critique": 0.55,
                    "style_quality": 0.6,
                },
                cost_tier=CostTier.FREE,
                context_limit_tokens=256_000,
                health=ProviderHealth(
                    status=ProviderStatus.HEALTHY,
                    reliability_score=0.95,
                    message="Local deterministic tools are available.",
                ),
            ),
            ProviderDescriptor(
                id="openai.configured",
                kind=ProviderKind.HOSTED_MODEL,
                enabled=bool(os.getenv("OPENAI_API_KEY")),
                capabilities={
                    "strategic_reasoning": 0.95,
                    "final_synthesis": 0.94,
                    "code_reasoning": 0.9,
                    "structured_output": 0.92,
                    "research": 0.9,
                    "citation_discipline": 0.82,
                    "critique": 0.82,
                    "style_quality": 0.85,
                },
                cost_tier=CostTier.PREMIUM,
                context_limit_tokens=128_000,
                health=ProviderHealth(
                    status=ProviderStatus.HEALTHY
                    if os.getenv("OPENAI_API_KEY")
                    else ProviderStatus.UNAVAILABLE,
                    reliability_score=0.85 if os.getenv("OPENAI_API_KEY") else 0.0,
                    message="OPENAI_API_KEY detected."
                    if os.getenv("OPENAI_API_KEY")
                    else "OPENAI_API_KEY is not configured.",
                ),
            ),
            ProviderDescriptor(
                id="anthropic.configured",
                kind=ProviderKind.HOSTED_MODEL,
                enabled=bool(os.getenv("ANTHROPIC_API_KEY")),
                capabilities={
                    "critique": 0.94,
                    "style_quality": 0.93,
                    "code_review": 0.88,
                    "longform_reasoning": 0.9,
                    "final_synthesis": 0.88,
                },
                cost_tier=CostTier.PREMIUM,
                context_limit_tokens=200_000,
                health=ProviderHealth(
                    status=ProviderStatus.HEALTHY
                    if os.getenv("ANTHROPIC_API_KEY")
                    else ProviderStatus.UNAVAILABLE,
                    reliability_score=0.85 if os.getenv("ANTHROPIC_API_KEY") else 0.0,
                    message="ANTHROPIC_API_KEY detected."
                    if os.getenv("ANTHROPIC_API_KEY")
                    else "ANTHROPIC_API_KEY is not configured.",
                ),
            ),
            ProviderDescriptor(
                id="ollama.local",
                kind=ProviderKind.LOCAL_MODEL,
                enabled=bool(os.getenv("OLLAMA_BASE_URL")),
                capabilities={
                    "summarization": 0.72,
                    "classification": 0.7,
                    "extraction": 0.68,
                    "structured_output": 0.55,
                },
                cost_tier=CostTier.FREE,
                context_limit_tokens=32_000,
                health=ProviderHealth(
                    status=ProviderStatus.UNKNOWN
                    if os.getenv("OLLAMA_BASE_URL")
                    else ProviderStatus.UNAVAILABLE,
                    reliability_score=0.5 if os.getenv("OLLAMA_BASE_URL") else 0.0,
                    message="OLLAMA_BASE_URL detected but health check is not implemented."
                    if os.getenv("OLLAMA_BASE_URL")
                    else "OLLAMA_BASE_URL is not configured.",
                ),
            ),
        ]
        return cls(providers)

    def available(self) -> list[ProviderDescriptor]:
        return [
            provider
            for provider in self.providers
            if provider.enabled and provider.health.status != ProviderStatus.UNAVAILABLE
        ]


class AdaptiveRouter:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def route(self, task: TaskNode) -> RoutingDecision:
        candidates: list[tuple[float, ProviderDescriptor]] = []
        for provider in self.registry.available():
            if not self._within_cost(task, provider):
                continue
            capability_score = self._capability_score(task, provider)
            if capability_score <= 0:
                continue
            reliability = provider.health.reliability_score
            cost_score = 1.0 - (COST_ORDER[provider.cost_tier] / 4)
            total = capability_score * 0.65 + reliability * 0.25 + cost_score * 0.10
            candidates.append((round(total, 4), provider))

        if candidates:
            score, provider = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
            action = (
                RoutingAction.ROUTE
                if provider.supports(task.required_capabilities)
                else RoutingAction.ROUTE_DEGRADED
            )
            reason = "Provider satisfies required capabilities."
            if action == RoutingAction.ROUTE_DEGRADED:
                reason = "Best available provider is below one or more requested capability thresholds."
            alternatives = [candidate.id for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True)[1:]]
            return RoutingDecision(
                task_id=task.id,
                action=action,
                provider_id=provider.id,
                score=score,
                reason=reason,
                alternatives=alternatives,
            )

        if task.fallback_policy.allow_task_reshape:
            return RoutingDecision(
                task_id=task.id,
                action=RoutingAction.RESHAPE,
                reason="No available provider fit capability and cost limits; task should be reshaped.",
            )
        return RoutingDecision(
            task_id=task.id,
            action=RoutingAction.PAUSE,
            reason="No available provider can execute this task safely.",
        )

    def route_all(self, tasks: list[TaskNode]) -> list[RoutingDecision]:
        return [self.route(task) for task in tasks]

    def _within_cost(self, task: TaskNode, provider: ProviderDescriptor) -> bool:
        return COST_ORDER[provider.cost_tier] <= COST_ORDER[task.max_cost_tier]

    def _capability_score(self, task: TaskNode, provider: ProviderDescriptor) -> float:
        if not task.required_capabilities:
            return 0.75
        scores: list[float] = []
        for capability, minimum in task.required_capabilities.items():
            actual = provider.capabilities.get(capability, 0.0)
            scores.append(min(1.0, actual / max(minimum, 0.01)))
        return sum(scores) / len(scores)
