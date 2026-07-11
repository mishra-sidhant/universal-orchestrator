from __future__ import annotations

import os

from universal_orchestrator.config import load_env_file
from universal_orchestrator.execution_policy import PolicyCompiler
from universal_orchestrator.models import (
    CostTier,
    ExecutionPolicy,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderRoutingMetric,
    ProviderStatus,
    RoutingAction,
    RoutingDecision,
    RoutingTelemetryReport,
    TaskNode,
    TaskRoutingTelemetry,
)
from universal_orchestrator.providers import (
    AnthropicAdapter,
    DeterministicToolsAdapter,
    OllamaAdapter,
    OpenAIResponsesAdapter,
    ProviderAdapterRegistry,
)
from universal_orchestrator.providers.transport import HTTPTransport


COST_ORDER = {
    CostTier.FREE: 0,
    CostTier.CHEAP: 1,
    CostTier.MEDIUM: 2,
    CostTier.PREMIUM: 3,
}


class CapabilityRegistry:
    def __init__(
        self,
        providers: list[ProviderDescriptor],
        transports: dict[str, HTTPTransport] | None = None,
    ) -> None:
        self.providers = providers
        self.transports = transports or {}

    @classmethod
    def from_environment(
        cls,
        transports: dict[str, HTTPTransport] | None = None,
    ) -> "CapabilityRegistry":
        load_env_file()
        providers = [
            ProviderDescriptor(
                id="deterministic.tools",
                kind=ProviderKind.DETERMINISTIC_TOOL,
                enabled=True,
                capabilities={
                    "file_io": 1.0,
                    "artifact_build": 0.95,
                    "context_aggregation": 1.0,
                    "gap_analysis": 1.0,
                    "extractive_synthesis": 1.0,
                    "quality_evaluation": 1.0,
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
        return cls(providers, transports=transports)

    def available(self) -> list[ProviderDescriptor]:
        return [
            provider
            for provider in self.providers
            if provider.enabled and provider.health.status != ProviderStatus.UNAVAILABLE
        ]

    def adapter_registry(self) -> ProviderAdapterRegistry:
        adapters = []
        for provider in self.providers:
            if provider.id == "deterministic.tools":
                adapters.append(DeterministicToolsAdapter(provider))
            elif provider.id == "openai.configured":
                adapters.append(OpenAIResponsesAdapter(provider, transport=self.transports.get(provider.id)))
            elif provider.id == "anthropic.configured":
                adapters.append(AnthropicAdapter(provider, transport=self.transports.get(provider.id)))
            elif provider.id == "ollama.local":
                adapters.append(OllamaAdapter(provider, transport=self.transports.get(provider.id)))
        return ProviderAdapterRegistry(adapters)


class AdaptiveRouter:
    def __init__(self, registry: CapabilityRegistry, policy: ExecutionPolicy | None = None) -> None:
        self.registry = registry
        self.policy = policy
        self.policy_compiler = PolicyCompiler()

    def route(self, task: TaskNode) -> RoutingDecision:
        provider_by_id = {provider.id: provider for provider in self.registry.providers}
        candidates = [
            metric for metric in self.provider_metrics(task) if metric.eligible
        ]

        if candidates:
            metric = sorted(candidates, key=lambda item: item.total_score, reverse=True)[0]
            provider = provider_by_id[metric.provider_id]
            action = (
                RoutingAction.ROUTE
                if provider.supports(task.required_capabilities)
                else RoutingAction.ROUTE_DEGRADED
            )
            reason = "Provider satisfies required capabilities."
            if action == RoutingAction.ROUTE_DEGRADED:
                reason = "Best available provider is below one or more requested capability thresholds."
            alternatives = [
                candidate.provider_id
                for candidate in sorted(candidates, key=lambda item: item.total_score, reverse=True)[1:]
            ]
            return RoutingDecision(
                task_id=task.id,
                action=action,
                provider_id=provider.id,
                score=metric.total_score,
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

    def route_all_with_telemetry(
        self,
        run_id: str,
        tasks: list[TaskNode],
    ) -> tuple[list[RoutingDecision], RoutingTelemetryReport]:
        decisions = self.route_all(tasks)
        decision_by_task = {decision.task_id: decision for decision in decisions}
        return decisions, RoutingTelemetryReport(
            run_id=run_id,
            provider_count=len(self.registry.providers),
            task_telemetry=[
                TaskRoutingTelemetry(
                    task_id=task.id,
                    selected_provider_id=decision_by_task[task.id].provider_id,
                    selected_action=decision_by_task[task.id].action,
                    selected_score=decision_by_task[task.id].score,
                    metrics=self.provider_metrics(task),
                )
                for task in tasks
            ],
        )

    def provider_metrics(self, task: TaskNode) -> list[ProviderRoutingMetric]:
        metrics: list[ProviderRoutingMetric] = []
        for provider in self.registry.providers:
            reasons: list[str] = []
            if not provider.enabled:
                reasons.append("provider disabled")
            if provider.health.status == ProviderStatus.UNAVAILABLE:
                reasons.append("provider unavailable")
            if self.policy:
                allowed, policy_reason = self.policy_compiler.provider_allowed(self.policy, provider)
                if not allowed:
                    reasons.append(policy_reason)
            if not self._within_cost(task, provider):
                reasons.append(f"provider cost tier {provider.cost_tier} exceeds task max {task.max_cost_tier}")
            capability_score = self._capability_score(task, provider)
            if capability_score <= 0:
                reasons.append("provider has no matching required capabilities")
            if not provider.supports(task.required_capabilities):
                reasons.append("provider capabilities are below task requirements")
            reliability = provider.health.reliability_score
            cost_score = 1.0 - (COST_ORDER[provider.cost_tier] / 4)
            total = 0.0
            eligible = not reasons
            if eligible:
                total = capability_score * 0.65 + reliability * 0.25 + cost_score * 0.10
            metrics.append(
                ProviderRoutingMetric(
                    task_id=task.id,
                    provider_id=provider.id,
                    enabled=provider.enabled,
                    health_status=provider.health.status,
                    reliability_score=reliability,
                    cost_tier=provider.cost_tier,
                    capability_score=round(capability_score, 4),
                    cost_score=round(cost_score, 4),
                    total_score=round(total, 4),
                    eligible=eligible,
                    supports_requirements=provider.supports(task.required_capabilities),
                    rejection_reasons=reasons,
                )
            )
        return metrics

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
