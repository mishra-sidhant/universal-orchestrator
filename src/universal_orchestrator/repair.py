from __future__ import annotations

import re

from universal_orchestrator.models import (
    CostTier,
    Criticality,
    QualityGateResult,
    TaskDAG,
    TaskNode,
    TaskType,
)


class RepairPlanner:
    def create_repair_dag(self, run_id: str, quality: QualityGateResult) -> TaskDAG:
        nodes: list[TaskNode] = []
        for index, violation in enumerate(quality.violations, start=1):
            repair_id = f"T-REPAIR-{index:03d}"
            nodes.append(
                TaskNode(
                    id=repair_id,
                    run_id=run_id,
                    title=self._title_for_violation(violation),
                    task_type=TaskType.QUALITY_REPAIR,
                    input_refs=[violation],
                    repair_target_task_ids=self._target_task_ids(violation),
                    output_schema="repair_result_json",
                    dependencies=[],
                    required_capabilities=self._capabilities_for_violation(violation),
                    criticality=Criticality.HIGH,
                    max_cost_tier=CostTier.MEDIUM,
                )
            )
        if nodes:
            nodes.append(
                TaskNode(
                    id="T-REPAIR-VALIDATE",
                    run_id=run_id,
                    title="Validate targeted repairs",
                    task_type=TaskType.VALIDATION,
                    input_refs=[node.id for node in nodes],
                    output_schema="repair_validation_json",
                    dependencies=[node.id for node in nodes],
                    required_capabilities={"contract_validation": 0.75, "artifact_validation": 0.75},
                    criticality=Criticality.HIGH,
                    max_cost_tier=CostTier.MEDIUM,
                )
            )
        dag = TaskDAG(run_id=run_id, nodes=nodes)
        dag.validate_graph()
        return dag

    def _title_for_violation(self, violation: str) -> str:
        lowered = violation.lower()
        if "artifact" in lowered:
            return f"Repair artifact issue: {violation}"
        if "dag" in lowered:
            return f"Repair DAG issue: {violation}"
        if "routing" in lowered or "provider" in lowered:
            return f"Repair routing issue: {violation}"
        if "input" in lowered or "manifest" in lowered:
            return f"Repair manifest issue: {violation}"
        return f"Repair quality issue: {violation}"

    def _capabilities_for_violation(self, violation: str) -> dict[str, float]:
        lowered = violation.lower()
        if "artifact" in lowered:
            return {"artifact_validation": 0.8, "file_io": 0.7}
        if "dag" in lowered:
            return {"decomposition": 0.65, "contract_validation": 0.7}
        if "routing" in lowered or "provider" in lowered:
            return {"routing": 0.75}
        return {"contract_validation": 0.7, "critique": 0.6}

    def _target_task_ids(self, violation: str) -> list[str]:
        return sorted(set(re.findall(r"T-[A-Z0-9]+(?:-[A-Z0-9]+)*", violation)))
