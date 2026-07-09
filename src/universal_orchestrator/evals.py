from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile

from universal_orchestrator.models import HostInvocation, InputAttachment, StrictModel
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.utils import ensure_dir, read_json, write_json


class EvaluationCaseResult(StrictModel):
    case_id: str
    run_id: str | None = None
    artifact_dir: str | None = None
    passed: bool = False
    missing_artifacts: list[str] = []
    failed_gates: list[str] = []
    notes: list[str] = []


class EvaluationReport(StrictModel):
    suite_name: str
    passed: bool
    cases: list[EvaluationCaseResult]
    report_path: str | None = None


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


class EvaluationRunner:
    def run(
        self,
        suite: EvaluationSuite | None = None,
        root: Path | str = ".uo/evals",
        case_ids: list[str] | None = None,
    ) -> EvaluationReport:
        active_suite = suite or built_in_suite()
        selected = [
            case for case in active_suite.cases if not case_ids or case.id in set(case_ids)
        ]
        root_path = ensure_dir(Path(root))
        results: list[EvaluationCaseResult] = []
        with tempfile.TemporaryDirectory() as tmp:
            fixture_root = Path(tmp)
            for case in selected:
                results.append(self._run_case(case, root_path, fixture_root))
        report = EvaluationReport(
            suite_name=active_suite.name,
            passed=all(result.passed for result in results),
            cases=results,
        )
        report_path = root_path / "eval_report.json"
        report = report.model_copy(update={"report_path": str(report_path)})
        write_json(report_path, report.model_dump(mode="json"))
        return report

    def _run_case(self, case: EvaluationCase, root: Path, fixture_root: Path) -> EvaluationCaseResult:
        inputs = [self._resolve_input(input_ref, fixture_root) for input_ref in case.inputs]
        result = Orchestrator(root).run(
            HostInvocation(
                prompt=case.prompt,
                attachments=[InputAttachment(uri=str(path)) for path in inputs],
                cwd=str(Path.cwd()),
            )
        )
        run_dir = Path(result.artifact_dir)
        missing_artifacts = [
            name for name in case.expected_artifacts if not (run_dir / name).exists()
        ]
        failed_gates = [
            gate for gate in case.expected_gates if not self._gate_passed(gate, run_dir)
        ]
        return EvaluationCaseResult(
            case_id=case.id,
            run_id=result.run_id,
            artifact_dir=str(run_dir),
            passed=result.quality.passed and not missing_artifacts and not failed_gates,
            missing_artifacts=missing_artifacts,
            failed_gates=failed_gates,
            notes=result.quality.warnings,
        )

    def _resolve_input(self, input_ref: str, fixture_root: Path) -> Path:
        path = Path(input_ref)
        if path.exists():
            return path
        if input_ref == "fixtures/unsafe.zip":
            fixture_path = fixture_root / "fixtures" / "unsafe.zip"
            ensure_dir(fixture_path.parent)
            with zipfile.ZipFile(fixture_path, "w") as archive:
                archive.writestr("../escape.txt", "unsafe")
                archive.writestr("safe.txt", "safe")
            return fixture_path
        return path

    def _gate_passed(self, gate: str, run_dir: Path) -> bool:
        if gate == "artifact_integrity":
            report = read_json(run_dir / "artifact_integrity_report.json")
            return bool(report.get("passed"))
        if gate == "contract_compliance":
            return (run_dir / "product_contract.json").exists()
        if gate == "context_manifest":
            return (run_dir / "context_manifest.json").exists()
        if gate == "dag_valid":
            return (run_dir / "task_dag.json").exists()
        if gate == "routing_complete":
            return (run_dir / "routing_decisions.json").exists()
        if gate == "structured_outputs":
            return "worker_output" in (run_dir / "execution_results.json").read_text()
        if gate == "archive_path_traversal_detected":
            manifest = read_json(run_dir / "context_manifest.json")
            warnings = [
                warning
                for item in manifest.get("inputs", [])
                for warning in item.get("warnings", [])
            ]
            return any("unsafe paths" in warning for warning in warnings)
        if gate == "no_unpack_without_sandbox":
            return not any(path.name == "escape.txt" for path in run_dir.rglob("*"))
        return False
