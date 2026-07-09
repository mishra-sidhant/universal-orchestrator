from __future__ import annotations

from universal_orchestrator.models import StrictModel


class EvaluationCase(StrictModel):
    id: str
    prompt: str
    inputs: list[str]
    expected_artifacts: list[str]
    expected_gates: list[str]


class EvaluationSuite(StrictModel):
    name: str
    cases: list[EvaluationCase]


def built_in_suite() -> EvaluationSuite:
    return EvaluationSuite(
        name="world_readiness_core",
        cases=[
            EvaluationCase(
                id="report_pdf_package",
                prompt="Create a cited report package as PDF and markdown.",
                inputs=["docs/product-requirements.md"],
                expected_artifacts=["final_report.md", "final_report.pdf", "run_manifest.json"],
                expected_gates=["artifact_integrity", "contract_compliance", "context_manifest"],
            ),
            EvaluationCase(
                id="repo_implementation_trace",
                prompt="Analyze this repo and produce an implementation package with tests.",
                inputs=["src", "tests"],
                expected_artifacts=["execution_results.json", "quality_report.json"],
                expected_gates=["dag_valid", "routing_complete", "structured_outputs"],
            ),
            EvaluationCase(
                id="unsafe_archive",
                prompt="Inspect this archive safely.",
                inputs=["fixtures/unsafe.zip"],
                expected_artifacts=["context_manifest.json"],
                expected_gates=["archive_path_traversal_detected", "no_unpack_without_sandbox"],
            ),
        ],
    )

