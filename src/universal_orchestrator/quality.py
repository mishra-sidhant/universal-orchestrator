from __future__ import annotations

from pathlib import Path

from universal_orchestrator.models import (
    ContextManifest,
    ExecutionResult,
    ProductContract,
    QualityGateResult,
    QualityScore,
    RoutingAction,
    RoutingDecision,
    TaskDAG,
    TaskStatus,
)


class QualityGateEngine:
    def evaluate(
        self,
        manifest: ContextManifest,
        contract: ProductContract,
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        artifact_paths: list[Path],
    ) -> QualityGateResult:
        violations: list[str] = []
        warnings: list[str] = []

        if not manifest.inputs:
            violations.append("Context manifest has no inputs.")
        if manifest.parsed_count == 0:
            violations.append("No inputs were parsed successfully.")

        try:
            dag.validate_graph()
        except ValueError as exc:
            violations.append(f"DAG validation failed: {exc}")

        executable_task_ids = {node.id for node in dag.nodes}
        decision_task_ids = {decision.task_id for decision in decisions}
        missing_decisions = executable_task_ids.difference(decision_task_ids)
        if missing_decisions:
            violations.append(f"Missing routing decisions for tasks: {sorted(missing_decisions)}")

        if any(decision.action == RoutingAction.PAUSE for decision in decisions):
            violations.append("One or more tasks paused because no safe provider was available.")
        degraded = [decision.task_id for decision in decisions if decision.action == RoutingAction.ROUTE_DEGRADED]
        if degraded:
            warnings.append(f"Degraded routing used for tasks: {degraded}")
        reshaped = [decision.task_id for decision in decisions if decision.action == RoutingAction.RESHAPE]
        if reshaped:
            warnings.append(f"Task reshaping requested for tasks: {reshaped}")

        partial_inputs = [item.name for item in manifest.inputs if item.status in {"partial", "failed"}]
        if partial_inputs:
            warnings.append(f"Some inputs were only partially parsed or failed: {partial_inputs}")

        security_findings = [
            finding
            for item in manifest.inputs
            for finding in item.security_findings
            if finding.severity in {"high", "critical"}
        ]
        if security_findings:
            warnings.append(f"High-severity security findings surfaced: {len(security_findings)}")

        if not artifact_paths:
            violations.append("No artifacts were built.")
        missing_artifacts = [str(path) for path in artifact_paths if not path.exists()]
        if missing_artifacts:
            violations.append(f"Artifact paths do not exist: {missing_artifacts}")

        failed_results = [result.task_id for result in results if result.status == TaskStatus.FAILED]
        if failed_results:
            violations.append(f"Execution failed for tasks: {failed_results}")
        skipped_results = [result.task_id for result in results if result.status == TaskStatus.SKIPPED]
        if skipped_results:
            warnings.append(f"Execution skipped for tasks: {skipped_results}")

        passed = not violations
        scores = QualityScore(
            completeness=95 if passed else 60,
            factuality=80,
            citation_support=70 if "source-aware synthesis" in contract.must_have else 100,
            style_quality=82,
            continuity=88,
            cost_efficiency=90 if not degraded and not reshaped else 75,
            artifact_integrity="pass" if not missing_artifacts and artifact_paths else "fail",
            code_validation="not_applicable",
        )
        return QualityGateResult(
            passed=passed,
            scores=scores,
            violations=violations,
            warnings=warnings,
            repair_task_ids=[] if passed else ["T-REPAIR-001"],
        )
