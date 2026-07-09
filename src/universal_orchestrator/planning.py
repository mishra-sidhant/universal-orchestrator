from __future__ import annotations

from universal_orchestrator.models import (
    CostTier,
    Criticality,
    PlanCandidate,
    PlanReview,
    ProductContract,
    TaskDAG,
    TaskNode,
    TaskType,
)


class PlannerEnsemble:
    """Deterministic v1 planner that preserves the report's ensemble shape."""

    def review_plan(self, run_id: str, contract: ProductContract, dag: TaskDAG) -> PlanReview:
        candidates = self.create_candidate_plans(contract, dag)
        score = round(sum(candidate.score for candidate in candidates) / max(1, len(candidates)), 4)
        strengths = sorted({strength for candidate in candidates for strength in candidate.strengths})
        risks = sorted({risk for candidate in candidates for risk in candidate.risks})
        return PlanReview(
            run_id=run_id,
            candidates=candidates,
            selected_task_ids=[node.id for node in dag.topological_order()],
            merged_strengths=strengths,
            residual_risks=risks,
            score=score,
        )

    def create_candidate_plans(self, contract: ProductContract, dag: TaskDAG) -> list[PlanCandidate]:
        task_ids = [node.id for node in dag.nodes]
        return [
            PlanCandidate(
                role="strategic_planner",
                bias="product outcome and final deliverable ownership",
                proposed_task_ids=task_ids,
                strengths=["contract-first planning", "final product owner is explicit"],
                risks=[] if contract.primary_artifacts else ["primary artifacts are underspecified"],
                score=0.88,
            ),
            PlanCandidate(
                role="decomposition_planner",
                bias="small typed tasks with dependencies",
                proposed_task_ids=task_ids,
                strengths=["DAG is typed", "repair can target individual failed nodes"],
                risks=[],
                score=0.9,
            ),
            PlanCandidate(
                role="risk_planner",
                bias="security, validation, artifact, and provider failure modes",
                proposed_task_ids=task_ids,
                strengths=["validation gates are first-class", "routing degradation is surfaced"],
                risks=["live provider quality is not validated until keys are configured"],
                score=0.82,
            ),
            PlanCandidate(
                role="cost_planner",
                bias="deterministic and cheap work before premium escalation",
                proposed_task_ids=task_ids,
                strengths=["deterministic tools cover artifact and validation tasks"],
                risks=["semantic cache is lexical until embeddings are added"],
                score=0.78,
            ),
            PlanCandidate(
                role="skeptic_planner",
                bias="attack assumptions and prevent thin delivery",
                proposed_task_ids=task_ids,
                strengths=["quality gates can reject incomplete packages"],
                risks=["human-grade acceptance tests still need expansion"],
                score=0.8,
            ),
        ]

    def create_execution_plan(self, run_id: str, contract: ProductContract) -> TaskDAG:
        nodes = [
            self._node(
                run_id,
                "T-001",
                "Review product contract",
                TaskType.PLANNING,
                {},
                [],
                Criticality.HIGH,
                CostTier.CHEAP,
            ),
            self._node(
                run_id,
                "T-002",
                "Score strategic plan",
                TaskType.PLANNING,
                {"strategic_reasoning": 0.7},
                ["T-001"],
                Criticality.HIGH,
                CostTier.PREMIUM,
            ),
            self._node(
                run_id,
                "T-003",
                "Decompose execution DAG",
                TaskType.PLANNING,
                {"decomposition": 0.75},
                ["T-001"],
                Criticality.HIGH,
                CostTier.MEDIUM,
            ),
            self._node(
                run_id,
                "T-004",
                "Evaluate risks and trust boundaries",
                TaskType.VALIDATION,
                {"security_review": 0.75},
                ["T-001"],
                Criticality.HIGH,
                CostTier.MEDIUM,
            ),
            self._node(
                run_id,
                "T-005",
                "Route executable work",
                TaskType.ROUTING,
                {"routing": 0.8},
                ["T-002", "T-003", "T-004"],
                Criticality.HIGH,
                CostTier.CHEAP,
            ),
            self._node(
                run_id,
                "T-006",
                "Execute deterministic worker pass",
                self._execution_task_type(contract),
                self._execution_capabilities(contract),
                ["T-005"],
                Criticality.MEDIUM,
                CostTier.MEDIUM,
            ),
            self._node(
                run_id,
                "T-007",
                "Aggregate structured worker outputs",
                TaskType.SUMMARIZATION,
                {"summarization": 0.65, "structured_output": 0.65},
                ["T-006"],
                Criticality.MEDIUM,
                CostTier.CHEAP,
            ),
            self._node(
                run_id,
                "T-008",
                "Run gap analysis",
                TaskType.VALIDATION,
                {"critique": 0.7, "contract_validation": 0.75},
                ["T-007"],
                Criticality.HIGH,
                CostTier.MEDIUM,
            ),
            self._node(
                run_id,
                "T-009",
                "Assemble final product",
                TaskType.FINAL_SYNTHESIS,
                {"final_synthesis": 0.8, "style_quality": 0.65},
                ["T-008"],
                Criticality.HIGH,
                CostTier.PREMIUM,
            ),
            self._node(
                run_id,
                "T-010",
                "Run quality gates",
                TaskType.VALIDATION,
                {"artifact_validation": 0.8, "contract_validation": 0.85},
                ["T-009"],
                Criticality.MISSION_CRITICAL,
                CostTier.MEDIUM,
            ),
            self._node(
                run_id,
                "T-011",
                "Build artifact package",
                TaskType.ARTIFACT_BUILD,
                {"artifact_build": 0.85, "file_io": 0.9},
                ["T-010"],
                Criticality.MISSION_CRITICAL,
                CostTier.FREE,
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
        )

    def _execution_task_type(self, contract: ProductContract) -> TaskType:
        if contract.run_type == "repo_implementation":
            return TaskType.CODE_EDIT
        if contract.run_type == "code_review":
            return TaskType.CODE_REVIEW
        if contract.run_type == "research_report":
            return TaskType.RESEARCH
        return TaskType.SUMMARIZATION

    def _execution_capabilities(self, contract: ProductContract) -> dict[str, float]:
        if contract.run_type == "repo_implementation":
            return {"code_reasoning": 0.75, "repo_navigation": 0.7}
        if contract.run_type == "code_review":
            return {"code_review": 0.75, "security_review": 0.6}
        if contract.run_type == "research_report":
            return {"research": 0.75, "citation_discipline": 0.65}
        return {"summarization": 0.6, "classification": 0.5}
