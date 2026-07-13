from __future__ import annotations

from pathlib import Path
from typing import Any

from universal_orchestrator.models import (
    ContextManifest,
    ExecutionResult,
    ProductContract,
    ProductPlan,
    RoutingAction,
    RoutingDecision,
    TaskDAG,
    TaskStatus,
    ValidationFinding,
)


class ValidatorRegistry:
    def _finding(
        self,
        *,
        validator: str,
        passed: bool,
        severity: str,
        pass_message: str,
        fail_message: str,
        metadata: dict[str, Any] | None = None,
    ) -> ValidationFinding:
        return ValidationFinding(
            validator=validator,
            passed=passed,
            severity=severity,
            message=pass_message if passed else fail_message,
            pass_message=pass_message,
            fail_message=fail_message,
            metadata=metadata or {},
        )

    def evaluate(
        self,
        manifest: ContextManifest,
        contract: ProductContract,
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        artifact_paths: list[Path],
        product_plan: ProductPlan | None = None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        findings.extend(self._manifest_findings(manifest))
        findings.extend(self._contract_findings(contract))
        findings.extend(self._dag_findings(dag))
        findings.extend(self._routing_findings(dag, decisions))
        findings.extend(self._execution_findings(results))
        findings.extend(self._artifact_findings(artifact_paths))
        if product_plan is not None:
            findings.extend(self._plan_findings(product_plan))
            findings.extend(self._manuscript_findings(dag, results))
        return findings

    def _plan_findings(self, plan: ProductPlan) -> list[ValidationFinding]:
        return [
            self._finding(
                validator="product_plan",
                passed=bool(plan.execution_steps),
                severity="high",
                pass_message="Product plan contains executable steps.",
                fail_message="Product plan contains no executable steps.",
                metadata={"step_count": len(plan.execution_steps)},
            ),
            self._finding(
                validator="product_plan",
                passed=bool(plan.acceptance_criteria),
                severity="high",
                pass_message="Product plan contains acceptance criteria.",
                fail_message="Product plan contains no acceptance criteria.",
                metadata={"criterion_count": len(plan.acceptance_criteria)},
            ),
            self._finding(
                validator="product_plan",
                passed=bool(plan.required_artifacts),
                severity="high",
                pass_message="Product plan names required artifacts.",
                fail_message="Product plan names no required artifacts.",
                metadata={"required_artifacts": plan.required_artifacts},
            ),
        ]

    def _manuscript_findings(
        self, dag: TaskDAG, results: list[ExecutionResult]
    ) -> list[ValidationFinding]:
        result_by_task = {result.task_id: result for result in results}
        missing: list[str] = []
        malformed: list[str] = []
        for node in dag.nodes:
            if node.task_type != "final_synthesis":
                continue
            result = result_by_task.get(node.id)
            worker_output = result.output.get("worker_output", {}) if result else {}
            sections = worker_output.get("manuscript") if isinstance(worker_output, dict) else None
            if not isinstance(sections, list) or not sections:
                missing.append(node.id)
                continue
            if any(
                not isinstance(section, dict)
                or not str(section.get("heading", "")).strip()
                or not str(section.get("objective", "")).strip()
                or not str(section.get("body", "")).strip()
                for section in sections
            ):
                malformed.append(node.id)
        return [
            self._finding(
                validator="manuscript",
                passed=not missing,
                severity="high",
                pass_message="Every final-synthesis task emits a structured manuscript.",
                fail_message=f"Final-synthesis tasks lack a manuscript: {sorted(missing)}",
                metadata={"missing": sorted(missing)},
            ),
            self._finding(
                validator="manuscript",
                passed=not malformed,
                severity="high",
                pass_message="Every manuscript section has heading, objective, and body.",
                fail_message=f"Malformed manuscript sections found for tasks: {sorted(malformed)}",
                metadata={"malformed": sorted(malformed)},
            ),
        ]

    def _manifest_findings(self, manifest: ContextManifest) -> list[ValidationFinding]:
        return [
            self._finding(
                validator="manifest",
                passed=bool(manifest.inputs),
                severity="critical",
                pass_message="Context manifest contains inventoried inputs.",
                fail_message="Context manifest contains no inventoried inputs.",
                metadata={"input_count": len(manifest.inputs), "parsed_count": manifest.parsed_count},
            ),
            self._finding(
                validator="manifest",
                passed=manifest.parsed_count > 0,
                severity="high",
                pass_message="At least one input parsed successfully.",
                fail_message="No input parsed successfully.",
            ),
        ]

    def _contract_findings(self, contract: ProductContract) -> list[ValidationFinding]:
        return [
            self._finding(
                validator="contract",
                passed=bool(contract.must_have and contract.must_not_have),
                severity="high",
                pass_message="Product contract has explicit must-have and must-not-have constraints.",
                fail_message="Product contract is missing must-have or must-not-have constraints.",
            )
        ]

    def _dag_findings(self, dag: TaskDAG) -> list[ValidationFinding]:
        try:
            dag.validate_graph()
        except ValueError as exc:
            return [
                self._finding(
                    validator="dag",
                    passed=False,
                    severity="critical",
                    pass_message="DAG validates without missing dependencies or cycles.",
                    fail_message=f"DAG validation failed: {exc}",
                )
            ]
        return [
            self._finding(
                validator="dag",
                passed=True,
                severity="critical",
                pass_message="DAG validates without missing dependencies or cycles.",
                fail_message="DAG has missing dependencies or cycles.",
                metadata={"task_count": len(dag.nodes)},
            )
        ]

    def _routing_findings(self, dag: TaskDAG, decisions: list[RoutingDecision]) -> list[ValidationFinding]:
        task_ids = {node.id for node in dag.nodes}
        decision_ids = {decision.task_id for decision in decisions}
        missing = sorted(task_ids.difference(decision_ids))
        paused = [decision.task_id for decision in decisions if decision.action == RoutingAction.PAUSE]
        return [
            self._finding(
                validator="routing",
                passed=not missing,
                severity="critical",
                pass_message="Every DAG task has a routing decision.",
                fail_message=f"Missing routing decisions for tasks: {missing}",
                metadata={"missing": missing},
            ),
            self._finding(
                validator="routing",
                passed=not paused,
                severity="high",
                pass_message="No task paused for lack of a safe provider.",
                fail_message=f"Tasks paused for lack of a safe provider: {paused}",
                metadata={"paused": paused},
            ),
        ]

    def _execution_findings(self, results: list[ExecutionResult]) -> list[ValidationFinding]:
        failed = [result.task_id for result in results if result.status == TaskStatus.FAILED]
        missing_structured = [
            result.task_id for result in results if "worker_output" not in result.output
        ]
        return [
            self._finding(
                validator="execution",
                passed=not failed,
                severity="critical",
                pass_message="No execution result failed.",
                fail_message=f"Execution failed for tasks: {failed}",
                metadata={"failed": failed},
            ),
            self._finding(
                validator="execution",
                passed=not missing_structured,
                severity="medium",
                pass_message="Execution results include structured worker output.",
                fail_message=f"Execution results lack structured worker output: {missing_structured}",
                metadata={"missing_structured": missing_structured},
            ),
        ]

    def _artifact_findings(self, artifact_paths: list[Path]) -> list[ValidationFinding]:
        missing = [str(path) for path in artifact_paths if not path.exists()]
        return [
            self._finding(
                validator="artifact",
                passed=bool(artifact_paths),
                severity="critical",
                pass_message="At least one artifact was built.",
                fail_message="No artifact was built.",
                metadata={"artifact_count": len(artifact_paths)},
            ),
            self._finding(
                validator="artifact",
                passed=not missing,
                severity="critical",
                pass_message="All declared artifact paths exist.",
                fail_message=f"Declared artifact paths do not exist: {missing}",
                metadata={"missing": missing},
            ),
        ]
