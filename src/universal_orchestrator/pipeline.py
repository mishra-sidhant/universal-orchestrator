from __future__ import annotations

from pathlib import Path

from universal_orchestrator.artifacts import ArtifactStore
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    Artifact,
    ArtifactType,
    HostInvocation,
    RunManifest,
    RunResult,
    RunState,
    new_id,
    utc_now,
)
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.quality import QualityGateEngine
from universal_orchestrator.repair import RepairPlanner
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry


class Orchestrator:
    def __init__(self, artifact_root: Path | str = ".uo/runs") -> None:
        self.artifact_store = ArtifactStore(Path(artifact_root))
        self.ingestor = InputIngestor()
        self.context = ContextIntelligence()
        self.contracts = ProductContractCompiler()
        self.planner = PlannerEnsemble()
        self.executor = DeterministicExecutor()
        self.quality = QualityGateEngine()
        self.repair = RepairPlanner()

    def run(self, invocation: HostInvocation) -> RunResult:
        run_id = new_id("run")
        started_at = utc_now()

        manifest = self.ingestor.ingest(invocation, run_id)
        cards = self.context.rank_cards(invocation.prompt, self.context.build_cards(manifest))
        contract = self.contracts.compile(invocation, manifest)
        dag = self.planner.create_execution_plan(run_id, contract)

        registry = CapabilityRegistry.from_environment()
        router = AdaptiveRouter(registry)
        decisions = router.route_all(dag.topological_order())
        execution_context = {
            "run_id": run_id,
            "contract": contract.model_dump(mode="json"),
            "input_refs": [item.id for item in manifest.inputs],
            "files": [item.path for item in manifest.inputs if item.path],
            "security_findings_count": sum(len(item.security_findings) for item in manifest.inputs),
            "context_card_count": len(cards),
        }
        self.executor = DeterministicExecutor(
            adapters=registry.adapter_registry(),
            prompt=invocation.prompt,
            allow_network=invocation.user_options.allow_internet,
            dry_run_external=not invocation.user_options.allow_internet,
            context=execution_context,
        )
        results = self.executor.execute(dag.topological_order(), decisions)

        artifacts: list[Artifact] = []
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "context_manifest.json", manifest.model_dump(mode="json")
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "context_cards.json", [card.model_dump(mode="json") for card in cards]
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "product_contract.json", contract.model_dump(mode="json")
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "task_dag.json", dag.model_dump(mode="json")
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id,
                "routing_decisions.json",
                [decision.model_dump(mode="json") for decision in decisions],
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id,
                "execution_results.json",
                [result.model_dump(mode="json") for result in results],
            )
        )

        quality = self.quality.evaluate(
            manifest=manifest,
            contract=contract,
            dag=dag,
            decisions=decisions,
            results=results,
            artifact_paths=[artifact.as_path for artifact in artifacts],
        )
        all_decisions = list(decisions)
        all_results = list(results)
        if not quality.passed:
            repair_dag = self.repair.create_repair_dag(run_id, quality)
            repair_decisions = router.route_all(repair_dag.topological_order())
            repair_results = self.executor.execute(repair_dag.topological_order(), repair_decisions)
            all_decisions.extend(repair_decisions)
            all_results.extend(repair_results)
            artifacts.append(
                self.artifact_store.write_json_artifact(
                    run_id, "repair_task_dag.json", repair_dag.model_dump(mode="json")
                )
            )
            artifacts.append(
                self.artifact_store.write_json_artifact(
                    run_id,
                    "repair_execution_results.json",
                    [result.model_dump(mode="json") for result in repair_results],
                )
            )
            quality = self.quality.evaluate(
                manifest=manifest,
                contract=contract,
                dag=dag,
                decisions=all_decisions,
                results=all_results,
                artifact_paths=[artifact.as_path for artifact in artifacts],
            )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "quality_report.json", quality.model_dump(mode="json")
            )
        )
        artifacts.append(
            self.artifact_store.write_final_report(
                run_id, manifest, contract, cards, dag, all_decisions, all_results, quality
            )
        )

        run_manifest = RunManifest(
            run_id=run_id,
            invocation=invocation,
            state=RunState.DELIVERED if quality.passed else RunState.VALIDATION,
            context_manifest_path=str(self.artifact_store.run_dir(run_id) / "context_manifest.json"),
            product_contract_path=str(self.artifact_store.run_dir(run_id) / "product_contract.json"),
            task_dag_path=str(self.artifact_store.run_dir(run_id) / "task_dag.json"),
            quality_report_path=str(self.artifact_store.run_dir(run_id) / "quality_report.json"),
            artifacts=artifacts,
            warnings=manifest.warnings + quality.warnings,
            routing_decisions=all_decisions,
            started_at=started_at,
            completed_at=utc_now(),
        )
        run_manifest_artifact = self.artifact_store.write_run_manifest(run_manifest)
        run_manifest.artifacts.append(run_manifest_artifact)
        self.artifact_store.write_run_manifest(run_manifest)

        return RunResult(
            run_id=run_id,
            state=run_manifest.state,
            artifact_dir=str(self.artifact_store.run_dir(run_id)),
            manifest=run_manifest,
            quality=quality,
        )

    def list_runs(self) -> list[Path]:
        if not self.artifact_store.root.exists():
            return []
        return sorted([path for path in self.artifact_store.root.iterdir() if path.is_dir()])

    def artifact_manifest_path(self, run_id: str) -> Path:
        return self.artifact_store.run_dir(run_id) / "run_manifest.json"
