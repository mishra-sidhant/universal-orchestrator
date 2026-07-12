from __future__ import annotations

from universal_orchestrator.models import (
    CostTier,
    Criticality,
    PlanCandidate,
    PlanReview,
    ProductContract,
    ProductPlan,
    ChapterPlan,
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

    def create_product_plan(
        self,
        run_id: str,
        contract: ProductContract,
        task_ids: list[str],
    ) -> ProductPlan:
        """Create a deterministic chapter contract without claiming prose quality."""

        title = contract.requested_output[:120] or "Universal Orchestrator Product"
        chapter_specs = self._chapter_specs(contract)
        chapters = [
            ChapterPlan(id=chapter_id, title=chapter_title, objective=objective, task_ids=[task_id])
            for chapter_id, chapter_title, objective, task_id in chapter_specs
            if task_id in task_ids
        ]
        if not chapters:
            chapters = [
                ChapterPlan(
                    id="chapter-1",
                    title=title,
                    objective=contract.requested_output,
                    task_ids=task_ids,
                )
            ]
        return ProductPlan(
            run_id=run_id,
            title=title,
            chapters=chapters,
            artifact_types=contract.primary_artifacts,
        )

    def validate_product_plan(self, plan: ProductPlan, dag: TaskDAG) -> list[str]:
        known_task_ids = {node.id for node in dag.nodes}
        errors: list[str] = []
        if plan.run_id != dag.run_id:
            errors.append(
                f"Product plan run {plan.run_id} does not match DAG run {dag.run_id}."
            )
        seen_chapter_ids: set[str] = set()
        for chapter in plan.chapters:
            if chapter.id in seen_chapter_ids:
                errors.append(f"Product plan contains duplicate chapter id {chapter.id}.")
            seen_chapter_ids.add(chapter.id)
            for task_id in chapter.task_ids:
                if task_id not in known_task_ids:
                    errors.append(
                        f"Product plan chapter {chapter.id} references unknown task {task_id}."
                    )
        return sorted(errors)

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

    def create_execution_plan(
        self,
        run_id: str,
        contract: ProductContract,
        model_synthesis: bool = False,
    ) -> TaskDAG:
        chapter_specs = {
            task_id: (chapter_id, chapter_title, objective)
            for chapter_id, chapter_title, objective, task_id in self._chapter_specs(contract)
        }
        chapter_one = chapter_specs["T-SYNTHESIS"]
        chapter_two = chapter_specs["T-CHAPTER-002"]
        chapter_three = chapter_specs["T-CHAPTER-003"]
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
                (
                    "Synthesize grounded model findings"
                    if model_synthesis
                    else "Synthesize extractive source findings"
                ),
                TaskType.FINAL_SYNTHESIS,
                {"final_synthesis": 0.6} if model_synthesis else {"extractive_synthesis": 0.9},
                ["T-GAP-ANALYSIS"],
                Criticality.HIGH,
                CostTier.PREMIUM if model_synthesis else CostTier.FREE,
                chapter_id=chapter_one[0],
                chapter_title=chapter_one[1],
                objective=chapter_one[2],
            ),
            self._node(
                run_id,
                "T-CHAPTER-002",
                "Synthesize findings and evidence chapter",
                TaskType.FINAL_SYNTHESIS,
                {"extractive_synthesis": 0.9},
                ["T-GAP-ANALYSIS"],
                Criticality.HIGH,
                CostTier.FREE,
                chapter_id=chapter_two[0],
                chapter_title=chapter_two[1],
                objective=chapter_two[2],
            ),
            self._node(
                run_id,
                "T-CHAPTER-003",
                "Synthesize risks and actions chapter",
                TaskType.FINAL_SYNTHESIS,
                {"extractive_synthesis": 0.9},
                ["T-GAP-ANALYSIS"],
                Criticality.HIGH,
                CostTier.FREE,
                chapter_id=chapter_three[0],
                chapter_title=chapter_three[1],
                objective=chapter_three[2],
            ),
            self._node(
                run_id,
                "T-ARTIFACT-BUILD",
                "Build static run artifacts",
                TaskType.ARTIFACT_BUILD,
                {"artifact_build": 0.9, "file_io": 0.9},
                ["T-SYNTHESIS", "T-CHAPTER-002", "T-CHAPTER-003"],
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
        chapter_id: str | None = None,
        chapter_title: str | None = None,
        objective: str | None = None,
    ) -> TaskNode:
        return TaskNode(
            id=task_id,
            run_id=run_id,
            title=title,
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            objective=objective,
            task_type=task_type,
            required_capabilities=capabilities,
            dependencies=dependencies,
            criticality=criticality,
            max_cost_tier=max_cost_tier,
            cacheable=cacheable,
            retry_policy=RetryPolicy(max_attempts=max_attempts),
        )

    def _chapter_specs(
        self, contract: ProductContract
    ) -> list[tuple[str, str, str, str]]:
        """Return the stable three-chapter contract for the requested product family."""

        if contract.run_type == "research_report":
            return [
                (
                    "chapter-1",
                    "Executive Summary",
                    f"Answer the requested output from the supplied evidence: {contract.requested_output}",
                    "T-SYNTHESIS",
                ),
                (
                    "chapter-2",
                    "Findings And Evidence",
                    "Present the independently synthesized findings and tie each finding to delivered evidence.",
                    "T-CHAPTER-002",
                ),
                (
                    "chapter-3",
                    "Risks And Recommendations",
                    "Present risks, limitations, and concrete recommendations grounded in the observed record.",
                    "T-CHAPTER-003",
                ),
            ]
        if contract.run_type in {"repo_implementation", "code_review"}:
            return [
                (
                    "chapter-1",
                    "System Overview",
                    "Describe the system scope, architecture, and execution path established by the inputs.",
                    "T-SYNTHESIS",
                ),
                (
                    "chapter-2",
                    "Engineering Findings",
                    "Report engineering findings with validation evidence and precise source locations where available.",
                    "T-CHAPTER-002",
                ),
                (
                    "chapter-3",
                    "Implementation And Validation",
                    "Describe implementation status, residual risks, and validation next actions.",
                    "T-CHAPTER-003",
                ),
            ]
        return [
            (
                "chapter-1",
                "Objective And Context",
                f"Clarify the objective, scope, and relevant context for: {contract.requested_output}",
                "T-SYNTHESIS",
            ),
            (
                "chapter-2",
                "Results And Evidence",
                "Present observed results and supporting evidence without adding unsupported claims.",
                "T-CHAPTER-002",
            ),
            (
                "chapter-3",
                "Risks And Next Actions",
                "Present risks, assumptions, and concrete next actions for the operator.",
                "T-CHAPTER-003",
            ),
        ]
