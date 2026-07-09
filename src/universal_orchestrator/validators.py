from __future__ import annotations

from pathlib import Path

from universal_orchestrator.models import (
    ContextManifest,
    ExecutionResult,
    ProductContract,
    RoutingAction,
    RoutingDecision,
    TaskDAG,
    TaskStatus,
    ValidationFinding,
)


class ValidatorRegistry:
    def evaluate(
        self,
        manifest: ContextManifest,
        contract: ProductContract,
        dag: TaskDAG,
        decisions: list[RoutingDecision],
        results: list[ExecutionResult],
        artifact_paths: list[Path],
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        findings.extend(self._manifest_findings(manifest))
        findings.extend(self._contract_findings(contract))
        findings.extend(self._dag_findings(dag))
        findings.extend(self._routing_findings(dag, decisions))
        findings.extend(self._execution_findings(results))
        findings.extend(self._artifact_findings(artifact_paths))
        return findings

    def _manifest_findings(self, manifest: ContextManifest) -> list[ValidationFinding]:
        return [
            ValidationFinding(
                validator="manifest",
                passed=bool(manifest.inputs),
                severity="critical",
                message="Context manifest contains inventoried inputs.",
                metadata={"input_count": len(manifest.inputs), "parsed_count": manifest.parsed_count},
            ),
            ValidationFinding(
                validator="manifest",
                passed=manifest.parsed_count > 0,
                severity="high",
                message="At least one input parsed successfully.",
            ),
        ]

    def _contract_findings(self, contract: ProductContract) -> list[ValidationFinding]:
        return [
            ValidationFinding(
                validator="contract",
                passed=bool(contract.must_have and contract.must_not_have),
                severity="high",
                message="Product contract has explicit must-have and must-not-have constraints.",
            )
        ]

    def _dag_findings(self, dag: TaskDAG) -> list[ValidationFinding]:
        try:
            dag.validate_graph()
        except ValueError as exc:
            return [
                ValidationFinding(
                    validator="dag",
                    passed=False,
                    severity="critical",
                    message=f"DAG validation failed: {exc}",
                )
            ]
        return [
            ValidationFinding(
                validator="dag",
                passed=True,
                severity="critical",
                message="DAG validates without missing dependencies or cycles.",
                metadata={"task_count": len(dag.nodes)},
            )
        ]

    def _routing_findings(self, dag: TaskDAG, decisions: list[RoutingDecision]) -> list[ValidationFinding]:
        task_ids = {node.id for node in dag.nodes}
        decision_ids = {decision.task_id for decision in decisions}
        missing = sorted(task_ids.difference(decision_ids))
        paused = [decision.task_id for decision in decisions if decision.action == RoutingAction.PAUSE]
        return [
            ValidationFinding(
                validator="routing",
                passed=not missing,
                severity="critical",
                message="Every DAG task has a routing decision.",
                metadata={"missing": missing},
            ),
            ValidationFinding(
                validator="routing",
                passed=not paused,
                severity="high",
                message="No task paused for lack of a safe provider.",
                metadata={"paused": paused},
            ),
        ]

    def _execution_findings(self, results: list[ExecutionResult]) -> list[ValidationFinding]:
        failed = [result.task_id for result in results if result.status == TaskStatus.FAILED]
        missing_structured = [
            result.task_id for result in results if "worker_output" not in result.output
        ]
        return [
            ValidationFinding(
                validator="execution",
                passed=not failed,
                severity="critical",
                message="No execution result failed.",
                metadata={"failed": failed},
            ),
            ValidationFinding(
                validator="execution",
                passed=not missing_structured,
                severity="medium",
                message="Execution results include structured worker output.",
                metadata={"missing_structured": missing_structured},
            ),
        ]

    def _artifact_findings(self, artifact_paths: list[Path]) -> list[ValidationFinding]:
        missing = [str(path) for path in artifact_paths if not path.exists()]
        return [
            ValidationFinding(
                validator="artifact",
                passed=bool(artifact_paths),
                severity="critical",
                message="At least one artifact was built.",
                metadata={"artifact_count": len(artifact_paths)},
            ),
            ValidationFinding(
                validator="artifact",
                passed=not missing,
                severity="critical",
                message="All declared artifact paths exist.",
                metadata={"missing": missing},
            ),
        ]

