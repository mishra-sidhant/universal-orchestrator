from __future__ import annotations

from universal_orchestrator.models import (
    BudgetProfile,
    BudgetReport,
    ContextPack,
    CostTier,
    CostLedgerReport,
    HostInvocation,
    RoutingDecision,
    TaskBudget,
    TaskDAG,
    TaskNode,
    TaskType,
    UsageLedgerEntry,
)


COST_ORDER = {
    CostTier.FREE: 0,
    CostTier.CHEAP: 1,
    CostTier.MEDIUM: 2,
    CostTier.PREMIUM: 3,
}

PROFILE_MAX_TIER = {
    BudgetProfile.CHEAP: CostTier.CHEAP,
    BudgetProfile.BALANCED: CostTier.MEDIUM,
    BudgetProfile.PREMIUM: CostTier.PREMIUM,
    BudgetProfile.UNLIMITED: CostTier.PREMIUM,
}

PROFILE_TOKEN_BUDGET = {
    BudgetProfile.CHEAP: 40_000,
    BudgetProfile.BALANCED: 160_000,
    BudgetProfile.PREMIUM: 500_000,
    BudgetProfile.UNLIMITED: 2_000_000,
}

USD_PER_MILLION_TOKENS = {
    CostTier.FREE: 0.0,
    CostTier.CHEAP: 0.15,
    CostTier.MEDIUM: 1.25,
    CostTier.PREMIUM: 8.0,
}

BASE_TOKENS_BY_TASK = {
    TaskType.PLANNING: 2_000,
    TaskType.ROUTING: 800,
    TaskType.RESEARCH: 7_500,
    TaskType.SUMMARIZATION: 3_500,
    TaskType.CODE_EDIT: 8_000,
    TaskType.CODE_REVIEW: 6_000,
    TaskType.VALIDATION: 2_500,
    TaskType.FINAL_SYNTHESIS: 6_500,
    TaskType.ARTIFACT_BUILD: 1_000,
    TaskType.QUALITY_REPAIR: 4_000,
}


class BudgetController:
    def apply(
        self,
        invocation: HostInvocation,
        dag: TaskDAG,
        context_packs: dict[str, ContextPack],
    ) -> tuple[TaskDAG, BudgetReport]:
        profile = BudgetProfile(invocation.user_options.budget_profile)
        effective_max_tier = PROFILE_MAX_TIER[profile]
        total_budget = PROFILE_TOKEN_BUDGET[profile]
        per_task_budget = max(1_000, total_budget // max(1, len(dag.nodes)))
        task_budgets: list[TaskBudget] = []
        adjusted_nodes: list[TaskNode] = []
        warnings: list[str] = []

        for node in dag.nodes:
            estimated_tokens = self.estimate_task_tokens(node, context_packs.get(node.id))
            enforced_tier = self._min_tier(node.max_cost_tier, effective_max_tier)
            reason = "Within requested budget profile."
            if enforced_tier != node.max_cost_tier:
                reason = f"Capped from {node.max_cost_tier} to {enforced_tier} by {profile} budget."
            if estimated_tokens > per_task_budget:
                warnings.append(
                    f"{node.id} estimated tokens {estimated_tokens} exceed per-task budget {per_task_budget}."
                )
            task_budgets.append(
                TaskBudget(
                    task_id=node.id,
                    original_max_cost_tier=node.max_cost_tier,
                    enforced_max_cost_tier=enforced_tier,
                    estimated_tokens=estimated_tokens,
                    token_budget=per_task_budget,
                    estimated_usd=self.estimate_usd(estimated_tokens, enforced_tier),
                    reason=reason,
                )
            )
            adjusted_nodes.append(node.model_copy(update={"max_cost_tier": enforced_tier}))

        total_estimated_tokens = sum(item.estimated_tokens for item in task_budgets)
        if total_estimated_tokens > total_budget:
            warnings.append(
                f"Estimated tokens {total_estimated_tokens} exceed total profile budget {total_budget}."
            )

        report = BudgetReport(
            run_id=dag.run_id,
            requested_profile=profile,
            effective_max_cost_tier=effective_max_tier,
            total_estimated_tokens=total_estimated_tokens,
            total_token_budget=total_budget,
            total_estimated_usd=round(
                sum(item.estimated_usd or 0.0 for item in task_budgets),
                6,
            ),
            enforced=True,
            cost_ceiling_usd=invocation.user_options.cost_ceiling_usd,
            task_budgets=task_budgets,
            warnings=warnings,
        )
        return TaskDAG(run_id=dag.run_id, nodes=adjusted_nodes), report

    def estimate_task_tokens(self, node: TaskNode, pack: ContextPack | None = None) -> int:
        base = BASE_TOKENS_BY_TASK.get(node.task_type, 2_000)
        capability_load = int(sum(node.required_capabilities.values()) * 1_000)
        context_tokens = 0
        if pack:
            context_tokens = min(
                pack.token_budget,
                sum(card.token_estimate for card in pack.cards)
                + sum(chunk.token_estimate for chunk in pack.chunks),
            )
        return base + capability_load + context_tokens

    def reconcile_estimated_usage(
        self,
        report: BudgetReport,
        decisions: list[RoutingDecision],
        context_packs: dict[str, ContextPack],
    ) -> BudgetReport:
        provider_by_task = {decision.task_id: decision.provider_id for decision in decisions}
        ledger: list[UsageLedgerEntry] = []
        for budget in report.task_budgets:
            pack = context_packs.get(budget.task_id)
            input_tokens = 0
            if pack:
                input_tokens = min(
                    budget.estimated_tokens,
                    sum(card.token_estimate for card in pack.cards)
                    + sum(chunk.token_estimate for chunk in pack.chunks),
                )
            output_tokens = max(0, budget.estimated_tokens - input_tokens)
            ledger.append(
                UsageLedgerEntry(
                    task_id=budget.task_id,
                    provider_id=provider_by_task.get(budget.task_id),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=budget.estimated_tokens,
                    estimated_usd=budget.estimated_usd,
                    token_budget=budget.token_budget,
                    within_token_budget=budget.estimated_tokens <= budget.token_budget,
                    estimated=True,
                )
            )
        reconciled = sum(item.total_tokens for item in ledger) == report.total_estimated_tokens
        return report.model_copy(
            update={"usage_ledger": ledger, "usage_reconciled": reconciled}
        )

    def reconcile_actual_usage(
        self,
        report: BudgetReport,
        ledger: CostLedgerReport,
        divergence_threshold: float = 0.25,
    ) -> BudgetReport:
        estimated = ledger.total_estimated_usd
        actual = ledger.total_actual_usd
        absolute = abs(actual - estimated)
        relative = absolute / estimated if estimated > 0 else 0.0
        diverged = bool(ledger.calls) and relative > divergence_threshold
        warnings = list(report.warnings)
        if diverged:
            warnings.append(
                "Provider estimate-to-actual cost divergence exceeded the configured threshold; "
                "estimator recalibration is recommended."
            )
        return report.model_copy(
            update={
                "cost_ceiling_usd": ledger.cost_ceiling_usd,
                "provider_calls": ledger.calls,
                "total_actual_usd": actual,
                "unknown_cost_calls": ledger.unknown_cost_calls,
                "budget_stop": ledger.budget_stop,
                "estimate_actual_reconciliation": {
                    "estimated_usd": estimated,
                    "actual_usd": actual,
                    "absolute_usd": absolute,
                    "relative_ratio": relative,
                    "threshold_ratio": divergence_threshold,
                    "diverged": diverged,
                },
                "warnings": warnings,
            }
        )

    def estimate_usd(self, tokens: int, cost_tier: CostTier) -> float:
        rate = USD_PER_MILLION_TOKENS[cost_tier]
        return round(tokens * rate / 1_000_000, 6)

    def _min_tier(self, left: CostTier, right: CostTier) -> CostTier:
        return left if COST_ORDER[left] <= COST_ORDER[right] else right
