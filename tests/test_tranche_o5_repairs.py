from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from universal_orchestrator.models import (
    ExecutionResult,
    HostInvocation,
    QualityGateResult,
    QualityScore,
    TaskDAG,
    TaskNode,
    TaskStatus,
    TaskType,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.repair import RepairPlanner
from universal_orchestrator.scheduler import DAGScheduler


class ForcedManuscriptRepairScheduler(DAGScheduler):
    def execute(self, dag, decisions, executor, *args, **kwargs):
        results, report = super().execute(dag, decisions, executor, *args, **kwargs)
        if any(node.id.startswith("T-REPAIR") for node in dag.nodes):
            return results, report
        for result in results:
            if result.task_id == "T-SYNTHESIS":
                worker = dict(result.output["worker_output"])
                worker.pop("manuscript", None)
                result_index = results.index(result)
                results[result_index] = result.model_copy(
                    update={"output": {**result.output, "worker_output": worker}}
                )
            if result.task_id == "T-QUALITY":
                worker = dict(result.output["worker_output"])
                quality = dict(worker["quality_result"])
                quality["passed"] = False
                quality["violations"] = [
                    "Final-synthesis tasks lack a manuscript: ['T-SYNTHESIS']"
                ]
                worker["quality_result"] = quality
                result_index = results.index(result)
                results[result_index] = result.model_copy(
                    update={"output": {**result.output, "worker_output": worker}}
                )
        return results, report


class TrancheO5RepairTests(unittest.TestCase):
    def test_repair_planner_records_target_task_ids(self) -> None:
        quality = QualityGateResult(
            passed=False,
            scores=QualityScore(
                completeness=60,
                parse_confidence=80,
                citation_support=0,
                continuity=80,
                routing_efficiency=70,
                artifact_presence="fail",
                code_validation="not_applicable",
            ),
            violations=["Final-synthesis tasks lack a manuscript: ['T-SYNTHESIS']"],
        )

        dag = RepairPlanner().create_repair_dag("R", quality)

        self.assertEqual(dag.nodes[0].repair_target_task_ids, ["T-SYNTHESIS"])

    def test_targeted_repair_replaces_missing_manuscript(self) -> None:
        orchestrator = Orchestrator("/tmp/uo-o5-unused")
        original = ExecutionResult(
            task_id="T-SYNTHESIS",
            provider_id="deterministic.tools",
            status=TaskStatus.COMPLETED,
            output={
                "worker_output": {
                    "summary": "Grounded original summary.",
                    "chapter_title": "Executive Summary",
                    "objective": "Answer the request.",
                    "evidence_refs": ["chunk-1"],
                }
            },
        )
        repair_task = TaskNode(
            id="T-REPAIR-001",
            run_id="R",
            title="Repair manuscript",
            task_type=TaskType.QUALITY_REPAIR,
            input_refs=["Final-synthesis tasks lack a manuscript: ['T-SYNTHESIS']"],
            repair_target_task_ids=["T-SYNTHESIS"],
        )
        repair_result = ExecutionResult(
            task_id=repair_task.id,
            provider_id="deterministic.tools",
            status=TaskStatus.COMPLETED,
            output={"worker_output": {"summary": "Repair completed."}},
        )

        replaced, report = orchestrator._apply_repair_replacements(
            [original], TaskDAG(run_id="R", nodes=[repair_task]), [repair_result]
        )

        self.assertEqual(replaced[0].status, TaskStatus.COMPLETED)
        self.assertEqual(
            replaced[0].output["worker_output"]["manuscript"][0]["heading"],
            "Executive Summary",
        )
        self.assertEqual(report[0]["target_task_id"], "T-SYNTHESIS")
        self.assertTrue(report[0]["replaced"])

    def test_repair_run_persists_replacement_and_reaudit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = Orchestrator(Path(tmp) / "runs")
            orchestrator.scheduler = ForcedManuscriptRepairScheduler()
            result = orchestrator.run(HostInvocation(prompt="Produce a grounded report"))
            run_dir = Path(result.artifact_dir)
            re_audit = json.loads((run_dir / "repair_reaudit.json").read_text())
            execution = json.loads((run_dir / "execution_results.json").read_text())
            audit = json.loads((run_dir / "evidence_audit.json").read_text())

        self.assertTrue(re_audit["replacements"][0]["replaced"])
        self.assertIn("T-SYNTHESIS", re_audit["replaced_task_ids"])
        self.assertTrue(audit["passed"])
        synthesis = next(item for item in execution if item["task_id"] == "T-SYNTHESIS")
        self.assertTrue(synthesis["output"]["worker_output"]["manuscript"])


if __name__ == "__main__":
    unittest.main()
