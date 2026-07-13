from __future__ import annotations

import json
import os
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.evals import EvaluationRunner
from universal_orchestrator.fidelity import ContextArtifactFidelityAuditor
from universal_orchestrator.models import (
    Artifact,
    ContextChunk,
    ContextPack,
    ExecutionResult,
    HostInvocation,
    PrivacyMode,
    TaskStatus,
    UserOptions,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.providers.transport import FakeTransport
from universal_orchestrator.repo_transaction import RepositoryEdit, TransactionalRepoEditor
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.utils import write_json


PROVIDER_ENV = (
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "GOOGLE_API_KEY",
    "GEMINI_MODEL",
    "XAI_API_KEY",
    "XAI_MODEL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
)


class ReleaseGateRunner:
    """Run fixture-only adversarial checks without keys or provider network calls."""

    def run(self, root: Path | str = ".uo/release-gate") -> dict[str, object]:
        root_path = Path(root).expanduser().resolve()
        root_path.mkdir(parents=True, exist_ok=True)
        with self._scrub_provider_env():
            eval_report = EvaluationRunner().run(root=root_path / "evals")
            no_egress, key_sweep = self._local_only_checks(root_path / "local-only")
            checks = [
                {
                    "name": "built_in_evals",
                    "passed": eval_report.passed,
                    "details": "Built-in world-readiness eval suite passed against local fixtures.",
                },
                {
                    "name": "delivery_state_consistency",
                    "passed": self._delivery_state_check(root_path / "delivery"),
                    "details": "ZIP construction failure demotes delivery and issues no receipt.",
                },
                {
                    "name": "local_only_no_egress",
                    "passed": no_egress,
                    "details": "Valid hosted configuration still produces zero transport calls in local_only mode.",
                },
                {
                    "name": "key_sweep",
                    "passed": key_sweep,
                    "details": "Planted key material is absent from the run directory and delivery ZIP.",
                },
                {
                    "name": "fidelity_tamper_detection",
                    "passed": self._fidelity_tamper_check(),
                    "details": "Tampered context-pack content hashes are detected.",
                },
                {
                    "name": "write_approval_boundary",
                    "passed": self._write_approval_check(root_path / "writes"),
                    "details": "Unapproved repository edits produce no file changes.",
                },
            ]
        report = {
            "schema_version": "1.0",
            "passed": all(bool(check["passed"]) for check in checks),
            "checks": checks,
            "eval_report_path": str(root_path / "evals" / "eval_report.json"),
            "verification": "Fixture-only release gate; no API key or provider network execution.",
        }
        write_json(root_path / "release_gate.json", report)
        return report

    @contextmanager
    def _scrub_provider_env(self) -> Iterator[None]:
        saved = {name: os.environ.get(name) for name in PROVIDER_ENV}
        try:
            for name in PROVIDER_ENV:
                os.environ.pop(name, None)
            yield
        finally:
            for name, value in saved.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def _delivery_state_check(self, root: Path) -> bool:
        class FailingBuilder(ArtifactBuilder):
            def build_zip(self, artifacts: list[Artifact], path: Path) -> Artifact:
                del artifacts, path
                raise OSError("fixture ZIP failure")

        orchestrator = Orchestrator(root / "runs")
        orchestrator.artifact_builder = FailingBuilder()
        result = orchestrator.run(HostInvocation(prompt="Produce a report"))
        run_dir = Path(result.artifact_dir)
        return bool(
            str(result.state) == "needs_attention"
            and not (run_dir / "delivery_receipt.json").exists()
            and json.loads((run_dir / "zip_validation.json").read_text())["errors"]
        )

    def _local_only_checks(self, root: Path) -> tuple[bool, bool]:
        root.mkdir(parents=True, exist_ok=True)
        marker = "sk-release-fixture-secret-123456"
        source = root / "source.md"
        source.write_text(f"OPENAI_API_KEY={marker}\nTrusted source content.\n")
        transport = FakeTransport([])
        old_key = os.environ.get("OPENAI_API_KEY")
        old_model = os.environ.get("OPENAI_MODEL")
        os.environ["OPENAI_API_KEY"] = "release-fixture-key"
        os.environ["OPENAI_MODEL"] = "release-fixture-model"
        try:
            registry = CapabilityRegistry.from_environment(
                transports={"openai.configured": transport}
            )
            result = Orchestrator(root / "runs", capability_registry=registry).run(
                HostInvocation(
                    prompt="Produce a local report",
                    attachments=[{"uri": str(source)}],
                    user_options=UserOptions(
                        allow_internet=True,
                        allow_cloud=True,
                        privacy_mode=PrivacyMode.LOCAL_ONLY,
                    ),
                )
            )
        finally:
            if old_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_model is None:
                os.environ.pop("OPENAI_MODEL", None)
            else:
                os.environ["OPENAI_MODEL"] = old_model
        run_dir = Path(result.artifact_dir)
        files = [path for path in run_dir.rglob("*") if path.is_file()]
        key_found = any(marker.encode() in path.read_bytes() for path in files)
        zip_found = False
        bundle = run_dir / "delivery_bundle.zip"
        if bundle.exists():
            with zipfile.ZipFile(bundle) as archive:
                zip_found = any(marker.encode() in archive.read(name) for name in archive.namelist())
        return not transport.requests, not key_found and not zip_found

    def _fidelity_tamper_check(self) -> bool:
        canonical = ContextChunk(
            id="chunk-release",
            input_id="input-release",
            ordinal=0,
            text="canonical",
            token_estimate=2,
            content_hash="sha256:canonical",
        )
        tampered = canonical.model_copy(update={"content_hash": "sha256:tampered"})
        report = ContextArtifactFidelityAuditor().audit(
            "R",
            [canonical],
            {"T-SYNTHESIS": ContextPack(task_id="T-SYNTHESIS", task="Answer", chunks=[tampered])},
            [
                ExecutionResult(
                    task_id="T-SYNTHESIS",
                    provider_id="deterministic.tools",
                    status=TaskStatus.COMPLETED,
                    output={"worker_output": {"evidence_refs": []}},
                )
            ],
            {"T-SYNTHESIS": []},
            [],
        )
        return not report.passed

    def _write_approval_check(self, root: Path) -> bool:
        root.mkdir(parents=True, exist_ok=True)
        target = root / "not-written.py"
        report = TransactionalRepoEditor().apply(
            root,
            [RepositoryEdit(path=target.name, content="no write")],
            run_id="R-RELEASE-GATE",
            allow_repo_writes=False,
        )
        return not report.committed and not target.exists()
