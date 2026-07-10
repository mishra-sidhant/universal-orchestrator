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
    def _finding(
        self,
        *,
        validator: str,
        passed: bool,
        severity: str,
        pass_message: str,
        fail_message: str,
        metadata: dict | None = None,
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
