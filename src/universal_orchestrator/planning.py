from __future__ import annotations

from universal_orchestrator.models import (
    CostTier,
    Criticality,
    PlanCandidate,
    PlanReview,
    ProductContract,
    RetryPolicy,
    TaskDAG,
    TaskNode,
    TaskType,
)


class PlannerEnsemble:
    """Derives a small executable stage plan and property-based review."""

    def review_plan(self, run_id: str, contract: ProductContract, dag: TaskDAG) -> PlanReview:
        candidates = self.create_candidate_plans(contract, dag)
        score = round(sum(candidate.score for candidate in candidates) / max(1, len(candidates)), 4)
        strengths = sorted({strength for candidate in candidates for strength in candidate.strengths})
        risks = sorted({risk for candidate in candidates for risk in candidate.risks})
        critical_path = self.critical_path(dag)
        return PlanReview(
            run_id=run_id,
            candidates=candidates,
            selected_task_ids=[node.id for node in dag.topological_order()],
            merged_strengths=strengths,
            residual_risks=risks,
            score=score,
            critical_path=critical_path,
            estimated_cost_tier=self.estimate_cost_tier(dag),
            simulation=self.simulate_plan(dag),
        )

    def critical_path(self, dag: TaskDAG) -> list[str]:
        nodes = {node.id: node for node in dag.nodes}
        memo: dict[str, list[str]] = {}

        def path_to(node_id: str) -> list[str]:
            if node_id in memo:
                return memo[node_id]
            node = nodes[node_id]
            if not node.dependencies:
                memo[node_id] = [node_id]
                return memo[node_id]
            best_dependency_path = max((path_to(dep) for dep in node.dependencies), key=len)
            memo[node_id] = [*best_dependency_path, node_id]
            return memo[node_id]

        return max((path_to(node.id) for node in dag.nodes), key=len)

    def estimate_cost_tier(self, dag: TaskDAG) -> CostTier:
        order = {CostTier.FREE: 0, CostTier.CHEAP: 1, CostTier.MEDIUM: 2, CostTier.PREMIUM: 3}
        return max((node.max_cost_tier for node in dag.nodes), key=lambda tier: order[tier])

    def simulate_plan(self, dag: TaskDAG) -> dict[str, object]:
        remaining = {node.id: node for node in dag.nodes}
        completed: set[str] = set()
        batches: list[list[str]] = []
        while remaining:
            ready = sorted(
                node.id
                for node in remaining.values()
                if all(dependency in completed for dependency in node.dependencies)
            )
            if not ready:
                break
            batches.append(ready)
            completed.update(ready)
            for task_id in ready:
                remaining.pop(task_id)
        return {
            "task_count": len(dag.nodes),
            "parallel_batches": batches,
            "max_parallelism": max((len(batch) for batch in batches), default=0),
            "critical_path_length": len(self.critical_path(dag)),
        }

    def create_candidate_plans(self, contract: ProductContract, dag: TaskDAG) -> list[PlanCandidate]:
        task_ids = [node.id for node in dag.nodes]
        ids = set(task_ids)
        artifact_coverage = 1.0 if contract.primary_artifacts else 0.0
        worker_ids = {
            "T-AGGREGATE",
            "T-GAP-ANALYSIS",
            "T-SYNTHESIS",
            "T-ARTIFACT-BUILD",
            "T-QUALITY",
        }
        worker_coverage = len(ids.intersection(worker_ids)) / max(1, len(ids))
        quality_coverage = float({"T-GAP-ANALYSIS", "T-QUALITY"}.issubset(ids))
        cache_safety = sum(not node.cacheable for node in dag.nodes) / max(1, len(dag.nodes))
        dependency_coverage = sum(bool(node.dependencies) for node in dag.nodes) / max(
            1, len(dag.nodes)
        )
        scores = {
            "strategic_planner": round(0.6 * artifact_coverage + 0.4 * worker_coverage, 4),
            "decomposition_planner": round(
                0.6 * worker_coverage + 0.4 * dependency_coverage, 4
            ),
            "risk_planner": round(0.7 * quality_coverage + 0.3 * cache_safety, 4),
            "cost_planner": round(
                sum(
                    node.max_cost_tier in {CostTier.FREE, CostTier.CHEAP}
                    for node in dag.nodes
                )
                / max(1, len(dag.nodes)),
                4,
            ),
            "skeptic_planner": round(
                0.5 * quality_coverage + 0.5 * worker_coverage, 4
            ),
        }
        return [
            PlanCandidate(
                role="strategic_planner",
                bias="product outcome and final deliverable ownership",
                proposed_task_ids=task_ids,
                strengths=["contract-first planning", "final product owner is explicit"],
                risks=[] if contract.primary_artifacts else ["primary artifacts are underspecified"],
                score=scores["strategic_planner"],
            ),
            PlanCandidate(
                role="decomposition_planner",
                bias="small typed tasks with dependencies",
                proposed_task_ids=task_ids,
                strengths=["DAG is typed", "repair can target individual failed nodes"],
                risks=[],
                score=scores["decomposition_planner"],
            ),
            PlanCandidate(
                role="risk_planner",
                bias="security, validation, artifact, and provider failure modes",
                proposed_task_ids=task_ids,
                strengths=["validation gates are first-class", "routing degradation is surfaced"],
                risks=["live provider quality is not validated until keys are configured"],
                score=scores["risk_planner"],
            ),
            PlanCandidate(
                role="cost_planner",
                bias="deterministic and cheap work before premium escalation",
                proposed_task_ids=task_ids,
                strengths=["deterministic tools cover artifact and validation tasks"],
                risks=["exact-match cache does not provide semantic similarity"],
                score=scores["cost_planner"],
            ),
            PlanCandidate(
                role="skeptic_planner",
                bias="attack assumptions and prevent thin delivery",
                proposed_task_ids=task_ids,
                strengths=["quality gates can reject incomplete packages"],
                risks=["human-grade acceptance tests still need expansion"],
                score=scores["skeptic_planner"],
            ),
        ]

    def create_execution_plan(self, run_id: str, contract: ProductContract) -> TaskDAG:
        del contract
        nodes = [
            self._node(
                run_id,
                "T-AGGREGATE",
                "Aggregate indexed context",
                TaskType.SUMMARIZATION,
                {"context_aggregation": 0.9},
                [],
                Criticality.HIGH,
                CostTier.FREE,
            ),
            self._node(
                run_id,
                "T-GAP-ANALYSIS",
                "Analyze manifest and context gaps",
                TaskType.VALIDATION,
                {"gap_analysis": 0.9},
                ["T-AGGREGATE"],
                Criticality.HIGH,
                CostTier.FREE,
            ),
            self._node(
                run_id,
                "T-SYNTHESIS",
                "Synthesize extractive source findings",
                TaskType.FINAL_SYNTHESIS,
                {"extractive_synthesis": 0.9},
                ["T-GAP-ANALYSIS"],
                Criticality.HIGH,
                CostTier.FREE,
            ),
            self._node(
                run_id,
                "T-ARTIFACT-BUILD",
                "Build static run artifacts",
                TaskType.ARTIFACT_BUILD,
                {"artifact_build": 0.9, "file_io": 0.9},
                ["T-SYNTHESIS"],
                Criticality.MISSION_CRITICAL,
                CostTier.FREE,
                cacheable=False,
                max_attempts=2,
            ),
            self._node(
                run_id,
                "T-QUALITY",
                "Evaluate runtime quality",
                TaskType.VALIDATION,
                {"quality_evaluation": 0.9},
                ["T-ARTIFACT-BUILD"],
                Criticality.MISSION_CRITICAL,
                CostTier.FREE,
                cacheable=False,
            ),
        ]
        dag = TaskDAG(run_id=run_id, nodes=nodes)
        dag.validate_graph()
        return dag

    def _node(
        self,
        run_id: str,
        task_id: str,
        title: str,
        task_type: TaskType,
        capabilities: dict[str, float],
        dependencies: list[str],
        criticality: Criticality,
        max_cost_tier: CostTier,
        cacheable: bool = True,
        max_attempts: int = 1,
    ) -> TaskNode:
        return TaskNode(
            id=task_id,
            run_id=run_id,
            title=title,
            task_type=task_type,
            required_capabilities=capabilities,
            dependencies=dependencies,
            criticality=criticality,
            max_cost_tier=max_cost_tier,
            cacheable=cacheable,
            retry_policy=RetryPolicy(max_attempts=max_attempts),
        )
