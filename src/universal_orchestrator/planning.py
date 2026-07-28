from __future__ import annotations

from universal_orchestrator.models import (
    CostTier,
    Criticality,
    PlanCandidate,
    PlanReview,
    ProductContract,
    ProductPlan,
    ChapterPlan,
    PlanBlueprint,
    PlanWorkUnit,
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
        chapter_specs = self._adaptive_chapter_specs(contract, run_id)
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
            run_type=contract.run_type,
            chapters=chapters,
            artifact_types=contract.primary_artifacts,
            continuity_terms=self._continuity_terms(contract),
            execution_steps=self._execution_steps(contract),
            acceptance_criteria=self._acceptance_criteria(contract),
            required_artifacts=list(dict.fromkeys(contract.primary_artifacts)),
        )

    def create_blueprint(
        self, run_id: str, contract: ProductContract, max_parallel_tasks: int = 4
    ) -> PlanBlueprint:
        specs = self._adaptive_chapter_specs(contract, run_id)
        return PlanBlueprint(
            run_id=run_id,
            work_units=[
                PlanWorkUnit(
                    id=chapter_id,
                    title=title,
                    objective=objective,
                    task_id=task_id,
                )
                for chapter_id, title, objective, task_id in specs
            ],
            max_parallel_tasks=max_parallel_tasks,
        )

    def validate_product_plan(
        self,
        plan: ProductPlan,
        dag: TaskDAG,
        contract: ProductContract | None = None,
    ) -> list[str]:
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
        if not plan.execution_steps:
            errors.append("Product plan has no executable steps.")
        if not plan.acceptance_criteria:
            errors.append("Product plan has no acceptance criteria.")
        if not plan.required_artifacts:
            errors.append("Product plan has no required artifacts.")
        if any(not chapter.task_ids for chapter in plan.chapters):
            errors.append("Product plan contains a chapter with no executable task.")
        if contract is not None and plan.run_type != contract.run_type:
            errors.append(
                f"Product plan run type {plan.run_type} does not match contract {contract.run_type}."
            )
        return sorted(errors)

    def _execution_steps(self, contract: ProductContract) -> list[str]:
        if contract.run_type == "research_report":
            return [
                "Inventory and redact every supplied source before retrieval.",
                "Compile bounded task context packs and exclude prompt-injection-risk chunks.",
                "Synthesize each chapter with consumed evidence references and audit every claim.",
                "Validate requested artifacts structurally and through rendered-page inspection.",
                "Package only after quality, evidence, integrity, and delivery checks agree.",
            ]
        if contract.run_type == "repo_implementation":
            return [
                "Map repository frameworks, languages, package files, hot files, and detected test commands.",
                "Produce a scoped implementation plan with explicit files, validation steps, and no unapproved writes.",
                "Run only the deterministic allowlisted repository validation commands when shell approval exists.",
                "Report implementation status, residual risks, and a truthful patch-plan artifact.",
                "Package only after repository, artifact, evidence, integrity, and delivery checks agree.",
            ]
        if contract.run_type == "code_review":
            return [
                "Map the repository and identify the requested review surface and likely hot files.",
                "Inspect findings against delivered source locations and classify severity and confidence.",
                "Validate available tests or commands without treating skipped validation as a pass.",
                "Assemble findings, risks, remediation actions, and evidence into the requested artifacts.",
                "Package only after evidence, quality, artifact, integrity, and delivery checks agree.",
            ]
        return [
            "Inventory and redact the supplied context before bounded retrieval.",
            "Compile task-specific context packs and preserve the operator objective.",
            "Produce objective-specific chapters with grounded findings and explicit limitations.",
            "Validate requested artifacts structurally and through rendered-page inspection.",
            "Package only after quality, evidence, integrity, and delivery checks agree.",
        ]

    def _acceptance_criteria(self, contract: ProductContract) -> list[str]:
        common = [
            "Every evidence-required claim cites only a delivered and consumed source chunk.",
            "Contradicted or insufficient claims are visibly rejected rather than cited.",
            "The delivery manifest, quality report, evidence audit, checksums, and ZIP agree on final state.",
        ]
        if contract.run_type == "research_report":
            return [
                *common,
                "Each requested primary artifact passes its structural and render-aware validation gate.",
            ]
        if contract.run_type == "repo_implementation":
            return [
                *common,
                "Repository scope, planned changes, validation commands, and residual risks are explicit.",
                "No repository write is implied or performed without the explicit write approval gate.",
            ]
        if contract.run_type == "code_review":
            return [
                *common,
                "Each material review finding has a severity, source location when available, and validation status.",
                "Skipped or blocked validation is disclosed as such and never represented as a pass.",
            ]
        return [
            *common,
            "The final product answers the operator objective and labels degraded or extractive paths.",
        ]

    def _continuity_terms(self, contract: ProductContract) -> list[str]:
        if contract.run_type == "repo_implementation":
            return ["repository scope", "validation", "residual risks", "implementation status"]
        if contract.run_type == "code_review":
            return ["finding", "severity", "location", "validation status", "remediation"]
        if contract.run_type == "research_report":
            return ["evidence", "finding", "limitation", "recommendation"]
        return ["objective", "evidence", "risk", "next action"]

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
        chapter_specs = self._adaptive_chapter_specs(contract, run_id)
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
            *[
                self._node(
                    run_id,
                    task_id,
                    self._synthesis_title(task_id, chapter_title, model_synthesis),
                    TaskType.FINAL_SYNTHESIS,
                    {"final_synthesis": 0.6}
                    if model_synthesis
                    else {"extractive_synthesis": 0.9},
                    ["T-GAP-ANALYSIS"],
                    Criticality.HIGH,
                    CostTier.PREMIUM if model_synthesis else CostTier.FREE,
                    chapter_id=chapter_id,
                    chapter_title=chapter_title,
                    objective=objective,
                )
                for chapter_id, chapter_title, objective, task_id in chapter_specs
            ],
            self._node(
                run_id,
                "T-ARTIFACT-BUILD",
                "Build static run artifacts",
                TaskType.ARTIFACT_BUILD,
                {"artifact_build": 0.9, "file_io": 0.9},
                [task_id for _, _, _, task_id in chapter_specs],
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

    def _synthesis_title(self, task_id: str, chapter_title: str, model_synthesis: bool) -> str:
        if task_id == "T-SYNTHESIS":
            return (
                "Synthesize grounded model findings"
                if model_synthesis
                else "Synthesize extractive source findings"
            )
        if task_id == "T-CHAPTER-002":
            return "Synthesize findings and evidence chapter"
        if task_id == "T-CHAPTER-003":
            return "Synthesize risks and actions chapter"
        return f"Synthesize {chapter_title.lower()}"

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

    def _adaptive_chapter_specs(
        self, contract: ProductContract, run_id: str
    ) -> list[tuple[str, str, str, str]]:
        requested = contract.constraints.get("sections")
        if not isinstance(requested, list) or not requested:
            return self._chapter_specs(contract)
        specs: list[tuple[str, str, str, str]] = []
        for index, item in enumerate(requested[:12], start=1):
            if isinstance(item, str):
                title = item.strip() or f"Section {index}"
                objective = f"Address the requested section: {title}"
            elif isinstance(item, dict):
                title = str(item.get("title", f"Section {index}")).strip() or f"Section {index}"
                objective = str(item.get("objective", title)).strip() or title
            else:
                title = f"Section {index}"
                objective = title
            task_id = "T-SYNTHESIS" if index == 1 else f"T-CHAPTER-{index:03d}"
            specs.append((f"chapter-{index}", title, objective, task_id))
        if not specs:
            return self._chapter_specs(contract)
        return specs
