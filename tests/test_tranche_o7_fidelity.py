from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from universal_orchestrator.fidelity import ContextArtifactFidelityAuditor
from universal_orchestrator.models import (
    ContextChunk,
    ContextPack,
    ExecutionResult,
    HostInvocation,
    TaskStatus,
)
from universal_orchestrator.pipeline import Orchestrator


class TrancheO7FidelityTests(unittest.TestCase):
    def test_fidelity_auditor_detects_tampered_context_pack_chunk(self) -> None:
        canonical = ContextChunk(
            id="chunk-1",
            input_id="input-1",
            ordinal=0,
            text="Canonical content.",
            token_estimate=4,
            content_hash="sha256:canonical",
        )
        tampered = canonical.model_copy(update={"content_hash": "sha256:tampered"})
        pack = ContextPack(task_id="T-SYNTHESIS", task="Answer", chunks=[tampered])
        result = ExecutionResult(
            task_id="T-SYNTHESIS",
            provider_id="deterministic.tools",
            status=TaskStatus.COMPLETED,
            output={
                "worker_output": {
                    "evidence_refs": ["chunk-1"],
                    "manuscript": [
                        {
                            "heading": "Answer",
                            "objective": "Answer",
                            "body": "Canonical content.",
                            "evidence_refs": ["chunk-1"],
                        }
                    ],
                }
            },
        )

        report = ContextArtifactFidelityAuditor().audit(
            "R",
            [canonical],
            {"T-SYNTHESIS": pack},
            [result],
            {"T-SYNTHESIS": ["chunk-1"]},
            [],
        )

        self.assertFalse(report.passed)
        self.assertTrue(any("content hash" in finding.message.lower() for finding in report.findings))

    def test_pipeline_writes_fidelity_and_product_audit_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Orchestrator(Path(tmp) / "runs").run(
                HostInvocation(prompt="Produce a grounded report")
            )
            run_dir = Path(result.artifact_dir)
            fidelity = json.loads((run_dir / "fidelity_report.json").read_text())
            bundle = json.loads((run_dir / "product_audit_bundle.json").read_text())
            with zipfile.ZipFile(run_dir / "delivery_bundle.zip") as archive:
                names = set(archive.namelist())

        self.assertTrue(fidelity["passed"])
        self.assertIn("fidelity_report.json", bundle["audit_artifacts"])
        self.assertIn("evidence_audit.json", bundle["audit_artifacts"])
        self.assertIn("fidelity_report.json", names)
        self.assertIn("product_audit_bundle.json", names)


if __name__ == "__main__":
    unittest.main()
