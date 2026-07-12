from __future__ import annotations

import os
from typing import Any

from universal_orchestrator.config import load_env_file
from universal_orchestrator.capacity import CapacityBroker
from universal_orchestrator.cost_ledger import CostLedger
from universal_orchestrator.execution_policy import PolicyCompiler
from universal_orchestrator.health import ProviderHealthChecker
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
    ClaudeCodeCLIAdapter,
    CodexCLIAdapter,
    DeterministicToolsAdapter,
    GeminiAdapter,
    OllamaAdapter,
    OpenAIResponsesAdapter,
    OpenAICompatibleChatAdapter,
    ProviderAdapter,
    ProviderAdapterRegistry,
)
from universal_orchestrator.providers.transport import HTTPTransport
from universal_orchestrator.providers.transport import UrllibHTTPTransport
from universal_orchestrator.providers.cli import discover_executable


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
        cost_ledger: CostLedger | None = None,
        health_checker: ProviderHealthChecker | None = None,
        capacity_broker: CapacityBroker | None = None,
        runtime_store: Any | None = None,
    ) -> None:
        self.providers = providers
        self.transports = transports or {}
        self.cost_ledger = cost_ledger
        self.health_checker = health_checker or ProviderHealthChecker()
        self.capacity_broker = capacity_broker or CapacityBroker(runtime_store=runtime_store)
        self.runtime_store = runtime_store
        if runtime_store is not None:
            self.bind_runtime(runtime_store)

    def bind_runtime(self, runtime_store: Any) -> None:
        self.runtime_store = runtime_store
        self.capacity_broker.bind_runtime(runtime_store)

    @classmethod
    def from_environment(
        cls,
        transports: dict[str, HTTPTransport] | None = None,
        cost_ledger: CostLedger | None = None,
        health_checker: ProviderHealthChecker | None = None,
        capacity_broker: CapacityBroker | None = None,
        runtime_store: Any | None = None,
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
                enabled=bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")),
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
                    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")
                    else ProviderStatus.UNAVAILABLE,
                    reliability_score=(
                        0.85 if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL") else 0.0
                    ),
                    message="OpenAI key and model detected."
                    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")
                    else "OpenAI key and model are not both configured.",
                ),
            ),
            ProviderDescriptor(
                id="anthropic.configured",
                kind=ProviderKind.HOSTED_MODEL,
                enabled=bool(os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_MODEL")),
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
                    if os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_MODEL")
                    else ProviderStatus.UNAVAILABLE,
                    reliability_score=(
                        0.85
                        if os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_MODEL")
                        else 0.0
                    ),
                    message="Anthropic key and model detected."
                    if os.getenv("ANTHROPIC_API_KEY") and os.getenv("ANTHROPIC_MODEL")
                    else "Anthropic key and model are not both configured.",
                ),
            ),
            ProviderDescriptor(
                id="ollama.local",
                kind=ProviderKind.LOCAL_MODEL,
                enabled=bool(os.getenv("OLLAMA_BASE_URL") and os.getenv("OLLAMA_MODEL")),
                capabilities={
                    "summarization": 0.72,
                    "classification": 0.7,
                    "extraction": 0.68,
                    "structured_output": 0.55,
                    "final_synthesis": 0.65,
                    "citation_discipline": 0.55,
                },
                cost_tier=CostTier.FREE,
                context_limit_tokens=32_000,
                health=ProviderHealth(
                    status=ProviderStatus.UNKNOWN
                    if os.getenv("OLLAMA_BASE_URL") and os.getenv("OLLAMA_MODEL")
                    else ProviderStatus.UNAVAILABLE,
                    reliability_score=(
                        0.5 if os.getenv("OLLAMA_BASE_URL") and os.getenv("OLLAMA_MODEL") else 0.0
                    ),
                    message="Ollama base URL and model detected; health is not yet probed."
                    if os.getenv("OLLAMA_BASE_URL") and os.getenv("OLLAMA_MODEL")
                    else "Ollama base URL and model are not both configured.",
                ),
            ),
        ]
        providers.extend(
            [
                ProviderDescriptor(
                    id="gemini.configured",
                    kind=ProviderKind.HOSTED_MODEL,
                    connector_id="gemini.configured/default",
                    billing_mode="metered",
                    enabled=bool(os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_MODEL")),
                    capabilities={
                        "strategic_reasoning": 0.9,
                        "final_synthesis": 0.88,
                        "structured_output": 0.86,
                        "research": 0.9,
                    },
                    cost_tier=CostTier.PREMIUM,
                    context_limit_tokens=1_000_000,
                    health=ProviderHealth(
                        status=ProviderStatus.HEALTHY
                        if os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_MODEL")
                        else ProviderStatus.UNAVAILABLE,
                        reliability_score=0.8
                        if os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_MODEL")
                        else 0.0,
                        message="Gemini API key and model detected. Capability values are configured priors.",
                    ),
                ),
                ProviderDescriptor(
                    id="xai.configured",
                    kind=ProviderKind.HOSTED_MODEL,
                    connector_id="xai.configured/default",
                    billing_mode="metered",
                    enabled=bool(os.getenv("XAI_API_KEY") and os.getenv("XAI_MODEL")),
                    capabilities={
                        "strategic_reasoning": 0.86,
                        "final_synthesis": 0.84,
                        "structured_output": 0.8,
                        "research": 0.82,
                    },
                    cost_tier=CostTier.PREMIUM,
                    context_limit_tokens=128_000,
                    health=ProviderHealth(
                        status=ProviderStatus.HEALTHY
                        if os.getenv("XAI_API_KEY") and os.getenv("XAI_MODEL")
                        else ProviderStatus.UNAVAILABLE,
                        reliability_score=0.78
                        if os.getenv("XAI_API_KEY") and os.getenv("XAI_MODEL")
                        else 0.0,
                        message="xAI API key and model detected. Capability values are configured priors.",
                    ),
                ),
                ProviderDescriptor(
                    id="openai-compatible.local",
                    kind=ProviderKind.LOCAL_MODEL,
                    connector_id="openai-compatible.local/default",
                    billing_mode="local",
                    enabled=bool(
                        os.getenv("OPENAI_COMPATIBLE_BASE_URL")
                        and os.getenv("OPENAI_COMPATIBLE_MODEL")
                    ),
                    capabilities={
                        "summarization": 0.7,
                        "extraction": 0.68,
                        "structured_output": 0.6,
                        "final_synthesis": 0.62,
                    },
                    cost_tier=CostTier.FREE,
                    context_limit_tokens=32_000,
                    health=ProviderHealth(
                        status=ProviderStatus.UNKNOWN
                        if os.getenv("OPENAI_COMPATIBLE_BASE_URL")
                        and os.getenv("OPENAI_COMPATIBLE_MODEL")
                        else ProviderStatus.UNAVAILABLE,
                        reliability_score=0.5
                        if os.getenv("OPENAI_COMPATIBLE_BASE_URL")
                        and os.getenv("OPENAI_COMPATIBLE_MODEL")
                        else 0.0,
                        message="OpenAI-compatible local endpoint detected; health is not yet probed.",
                    ),
                ),
                ProviderDescriptor(
                    id="claude-code.cli",
                    kind=ProviderKind.SUBSCRIPTION_CLI,
                    connector_id="claude-code.cli/default",
                    model_id=os.getenv("CLAUDE_CODE_MODEL", "default"),
                    billing_mode="subscription",
                    enabled=discover_executable("CLAUDE_CODE_BIN", "claude") is not None,
                    capabilities={
                        "final_synthesis": 0.9,
                        "longform_reasoning": 0.9,
                        "code_review": 0.9,
                        "structured_output": 0.8,
                    },
                    cost_tier=CostTier.PREMIUM,
                    context_limit_tokens=200_000,
                    health=ProviderHealth(
                        status=ProviderStatus.UNKNOWN
                        if discover_executable("CLAUDE_CODE_BIN", "claude")
                        else ProviderStatus.UNAVAILABLE,
                        reliability_score=0.5
                        if discover_executable("CLAUDE_CODE_BIN", "claude")
                        else 0.0,
                        message="Claude Code CLI discovered; subscription capacity is not yet probed.",
                    ),
                ),
                ProviderDescriptor(
                    id="codex.cli",
                    kind=ProviderKind.SUBSCRIPTION_CLI,
                    connector_id="codex.cli/default",
                    model_id=os.getenv("CODEX_MODEL", "default"),
                    billing_mode="subscription",
                    enabled=discover_executable("CODEX_BIN", "codex") is not None,
                    capabilities={
                        "strategic_reasoning": 0.9,
                        "final_synthesis": 0.9,
                        "code_reasoning": 0.95,
                        "structured_output": 0.85,
                    },
                    cost_tier=CostTier.PREMIUM,
                    context_limit_tokens=200_000,
                    health=ProviderHealth(
                        status=ProviderStatus.UNKNOWN
                        if discover_executable("CODEX_BIN", "codex")
                        else ProviderStatus.UNAVAILABLE,
                        reliability_score=0.5
                        if discover_executable("CODEX_BIN", "codex")
                        else 0.0,
                        message="Codex CLI discovered; subscription capacity is not yet probed.",
                    ),
                ),
            ]
        )
        return cls(
            providers,
            transports=transports,
            cost_ledger=cost_ledger,
            health_checker=health_checker,
            capacity_broker=capacity_broker,
            runtime_store=runtime_store,
        )

    def refresh_health(
        self,
        policy: ExecutionPolicy,
        allow_network: bool,
    ) -> list[ProviderDescriptor]:
        refreshed: list[ProviderDescriptor] = []
        for provider in self.providers:
            if provider.kind == ProviderKind.DETERMINISTIC_TOOL or not provider.enabled:
                refreshed.append(provider)
                continue
            if provider.kind == ProviderKind.SUBSCRIPTION_CLI:
                refreshed.append(
                    provider.model_copy(
                        update={
                            "metadata": {
                                **provider.metadata,
                                "health_source": "cli_status_only",
                            }
                        }
                    )
                )
                continue
            allowed, _ = PolicyCompiler().provider_allowed(policy, provider)
            if not allowed or (
                provider.kind in {ProviderKind.HOSTED_MODEL, ProviderKind.SUBSCRIPTION_CLI}
                and not allow_network
            ):
                refreshed.append(provider)
                continue
            transport = self.transports.get(provider.id) or UrllibHTTPTransport()
            health = self.health_checker.check(provider, transport)
            refreshed.append(
                provider.model_copy(
                    update={
                        "health": health,
                        "metadata": {**provider.metadata, "health_source": "measured_probe"},
                    }
                )
            )
        self.providers = refreshed
        return refreshed

    def available(self) -> list[ProviderDescriptor]:
        return [
            provider
            for provider in self.providers
            if provider.enabled and provider.health.status != ProviderStatus.UNAVAILABLE
        ]

    def adapter_registry(self) -> ProviderAdapterRegistry:
        adapters: list[ProviderAdapter] = []
        for provider in self.providers:
            if provider.id == "deterministic.tools":
                adapters.append(DeterministicToolsAdapter(provider))
            elif provider.id == "openai.configured":
                adapters.append(
                    OpenAIResponsesAdapter(
                        provider,
                        transport=self.transports.get(provider.id),
                        cost_ledger=self.cost_ledger,
                        capacity_broker=self.capacity_broker,
                        runtime_store=self.runtime_store,
                    )
                )
            elif provider.id == "anthropic.configured":
                adapters.append(
                    AnthropicAdapter(
                        provider,
                        transport=self.transports.get(provider.id),
                        cost_ledger=self.cost_ledger,
                        capacity_broker=self.capacity_broker,
                        runtime_store=self.runtime_store,
                    )
                )
            elif provider.id == "ollama.local":
                adapters.append(
                    OllamaAdapter(
                        provider,
                        transport=self.transports.get(provider.id),
                        cost_ledger=self.cost_ledger,
                        capacity_broker=self.capacity_broker,
                        runtime_store=self.runtime_store,
                    )
                )
            elif provider.id == "gemini.configured":
                adapters.append(
                    GeminiAdapter(
                        provider,
                        transport=self.transports.get(provider.id),
                        cost_ledger=self.cost_ledger,
                        capacity_broker=self.capacity_broker,
                        runtime_store=self.runtime_store,
                    )
                )
            elif provider.id == "xai.configured":
                adapters.append(
                    OpenAICompatibleChatAdapter(
                        provider,
                        api_key_env="XAI_API_KEY",
                        model_env="XAI_MODEL",
                        base_url_env="XAI_BASE_URL",
                        default_base_url="https://api.x.ai/v1",
                        transport=self.transports.get(provider.id),
                        cost_ledger=self.cost_ledger,
                        capacity_broker=self.capacity_broker,
                        runtime_store=self.runtime_store,
                    )
                )
            elif provider.id == "openai-compatible.local":
                adapters.append(
                    OpenAICompatibleChatAdapter(
                        provider,
                        api_key_env="OPENAI_COMPATIBLE_API_KEY",
                        model_env="OPENAI_COMPATIBLE_MODEL",
                        base_url_env="OPENAI_COMPATIBLE_BASE_URL",
                        default_base_url="http://127.0.0.1:8000/v1",
                        transport=self.transports.get(provider.id),
                        cost_ledger=self.cost_ledger,
                        capacity_broker=self.capacity_broker,
                        runtime_store=self.runtime_store,
                    )
                )
            elif provider.id == "claude-code.cli":
                executable = discover_executable("CLAUDE_CODE_BIN", "claude")
                if executable:
                    adapters.append(
                        ClaudeCodeCLIAdapter(
                            provider,
                            executable=executable,
                            capacity_broker=self.capacity_broker,
                            runtime_store=self.runtime_store,
                            cost_ledger=self.cost_ledger,
                        )
                    )
            elif provider.id == "codex.cli":
                executable = discover_executable("CODEX_BIN", "codex")
                if executable:
                    adapters.append(
                        CodexCLIAdapter(
                            provider,
                            executable=executable,
                            capacity_broker=self.capacity_broker,
                            runtime_store=self.runtime_store,
                            cost_ledger=self.cost_ledger,
                        )
                    )
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
            reason=(
                "No available provider can execute required capabilities "
                f"{sorted(task.required_capabilities)} safely. Configure or restore a provider "
                "that advertises those capabilities."
            ),
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
            connector_id = provider.connector_id or f"{provider.id}/{provider.model_id}"
            capacity_snapshot = self.registry.capacity_broker.snapshot(connector_id)
            capacity_eligible = self.registry.capacity_broker.is_eligible(connector_id)
            if not capacity_eligible:
                reasons.append(
                    f"capacity {capacity_snapshot.status if capacity_snapshot else 'unavailable'}"
                )
            reliability = provider.health.reliability_score
            cost_score = 1.0 - (COST_ORDER[provider.cost_tier] / 4)
            capacity_score = self.registry.capacity_broker.score(connector_id)
            total = 0.0
            eligible = not reasons
            if eligible:
                total = (
                    capability_score * 0.55
                    + reliability * 0.20
                    + cost_score * 0.10
                    + capacity_score * 0.15
                )
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
                    capacity_status=self.registry.capacity_broker.effective_status(connector_id),
                    capacity_score=round(capacity_score, 4),
                    capacity_reason=capacity_snapshot.reason if capacity_snapshot else "No capacity observation yet.",
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
