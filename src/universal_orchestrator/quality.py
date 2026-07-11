from __future__ import annotations

from pathlib import Path

from universal_orchestrator.models import (
    ContextManifest,
    ExecutionResult,
    ProductContract,
    QualityGateResult,
    QualityScore,
    RepoValidationReport,
    RoutingAction,
    RoutingDecision,
    TaskDAG,
    TaskStatus,
    task_succeeded,
)
from universal_orchestrator.validators import ValidatorRegistry


class QualityGateEngine:
    def __init__(self) -> None:
        self.validators = ValidatorRegistry()

    def evaluate(
        self,
        manifest: ContextManifest,
        contract: ProductContract,
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        artifact_paths: list[Path],
        repo_validation_report: RepoValidationReport | None = None,
    ) -> QualityGateResult:
        findings = self.validators.evaluate(manifest, contract, dag, decisions, results, artifact_paths)
        violations: list[str] = [
            finding.message
            for finding in findings
            if not finding.passed and finding.severity in {"high", "critical"}
        ]
        warnings: list[str] = [
            finding.message
            for finding in findings
            if not finding.passed and finding.severity in {"info", "low", "medium"}
        ]

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
        cancelled_results = [result.task_id for result in results if result.status == TaskStatus.CANCELLED]
        if cancelled_results:
            violations.append(f"Execution cancelled for tasks: {cancelled_results}")

        code_validation = "not_applicable"
        if repo_validation_report and repo_validation_report.command_results:
            if any(result.status == "failed" for result in repo_validation_report.command_results):
                violations.append("One or more repository validation commands failed.")
                code_validation = "fail"
            elif repo_validation_report.executed and repo_validation_report.passed:
                code_validation = "pass"
            else:
                warnings.append("Repository validation commands were detected but not executed.")

        passed = not violations
        validator_pass_rate = (
            sum(1 for finding in findings if finding.passed) / len(findings) if findings else 0.0
        )
        task_ids = {node.id for node in dag.nodes}.union(result.task_id for result in results)
        successful_task_ids = {
            result.task_id for result in results if task_succeeded(result.status)
        }
        result_success_rate = (
            len(successful_task_ids.intersection(task_ids)) / len(task_ids) if task_ids else 0.0
        )
        parse_rate = manifest.parsed_count / len(manifest.inputs) if manifest.inputs else 0.0
        completeness = round(
            100 * (0.4 * validator_pass_rate + 0.4 * result_success_rate + 0.2 * parse_rate)
        )
        if violations:
            completeness = min(completeness, 69)
        continuity = round(100 * result_success_rate)
        routing_efficiency = (
            round(
                100
                * sum(1 for decision in decisions if decision.action == RoutingAction.ROUTE)
                / len(decisions)
            )
            if decisions
            else 0
        )
        scores = QualityScore(
            completeness=completeness,
            parse_confidence=round(100 * parse_rate),
            citation_support=0,
            continuity=continuity,
            routing_efficiency=routing_efficiency,
            artifact_presence="pass" if not missing_artifacts and artifact_paths else "fail",
            code_validation=code_validation,
        )
        repair_task_ids = [f"T-REPAIR-{index:03d}" for index, _ in enumerate(violations, start=1)]
        return QualityGateResult(
            passed=passed,
            scores=scores,
            violations=violations,
            warnings=warnings,
            repair_task_ids=[] if passed else repair_task_ids,
        )
