from __future__ import annotations

from pathlib import Path

from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.artifacts import ArtifactStore
from universal_orchestrator.cache import SemanticCache
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    Artifact,
    ArtifactType,
    HostInvocation,
    RuntimeEvent,
    RunManifest,
    RunResult,
    RunState,
    new_id,
    utc_now,
)
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.product import FinalProductOwner
from universal_orchestrator.quality import QualityGateEngine
from universal_orchestrator.repair import RepairPlanner
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry
from universal_orchestrator.scheduler import DAGScheduler


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
        self.product_owner = FinalProductOwner()
        self.artifact_builder = ArtifactBuilder()
        self.cache = SemanticCache(Path(artifact_root) / "_cache")
        self.runtime = RuntimeStore(Path(artifact_root) / "runtime.sqlite3")
        self.scheduler = DAGScheduler(self.cache)

    def run(self, invocation: HostInvocation) -> RunResult:
        run_id = new_id("run")
        started_at = utc_now()
        self.runtime.record_event(RuntimeEvent(run_id=run_id, event_type="received", payload={"host": invocation.host}))
        self.runtime.transition(run_id, RunState.RECEIVED)

        manifest = self.ingestor.ingest(invocation, run_id)
        self.runtime.transition(run_id, RunState.INGESTING)
        raw_cards = self.context.deduplicate_cards(self.context.build_cards(manifest))
        cards = self.context.rank_cards(invocation.prompt, raw_cards)
        chunks = self.context.chunk_manifest(manifest)
        provenance = self.context.provenance(cards, chunks)
        context_index = self.context.build_index(cards)
        conflicts = self.context.detect_conflicts(cards)
        cache_key = self.cache.key_for(
            "context_cards",
            {"prompt": invocation.prompt, "inputs": [item.content_hash for item in manifest.inputs]},
        )
        self.cache.set(
            cache_key,
            {
                "card_count": len(cards),
                "index_terms": len(context_index),
                "conflicts": conflicts,
            },
        )
        contract = self.contracts.compile(invocation, manifest)
        self.runtime.transition(run_id, RunState.CONTRACTING)
        dag = self.planner.create_execution_plan(run_id, contract)
        self.runtime.transition(run_id, RunState.PLANNING)
        plan_review = self.planner.review_plan(run_id, contract, dag)
        context_packs = self.context.compile_packs_for_tasks([node.id for node in dag.nodes], cards)

        registry = CapabilityRegistry.from_environment()
        router = AdaptiveRouter(registry)
        decisions = router.route_all(dag.topological_order())
        self.runtime.transition(run_id, RunState.ROUTING)
        execution_context = {
            "run_id": run_id,
            "contract": contract.model_dump(mode="json"),
            "input_refs": [item.id for item in manifest.inputs],
            "files": [item.path for item in manifest.inputs if item.path],
            "security_findings_count": sum(len(item.security_findings) for item in manifest.inputs),
            "context_card_count": len(cards),
            "context_chunk_count": len(chunks),
            "context_pack_count": len(context_packs),
        }
        self.executor = DeterministicExecutor(
            adapters=registry.adapter_registry(),
            prompt=invocation.prompt,
            allow_network=invocation.user_options.allow_internet,
            dry_run_external=not invocation.user_options.allow_internet,
            context=execution_context,
        )
        self.runtime.transition(run_id, RunState.EXECUTING)
        results, schedule_report = self.scheduler.execute(dag, decisions, self.executor)
        for record in schedule_report.records:
            self.runtime.save_task_record(run_id, record.task_id, str(record.status), record.attempt, record.cache_key)

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
                run_id, "context_chunks.json", [chunk.model_dump(mode="json") for chunk in chunks]
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "context_provenance.json", [item.model_dump(mode="json") for item in provenance]
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id,
                "context_packs.json",
                {task_id: pack.model_dump(mode="json") for task_id, pack in context_packs.items()},
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id,
                "context_index.json",
                {"terms": context_index, "conflicts": conflicts, "cache_key": cache_key},
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
                run_id, "plan_review.json", plan_review.model_dump(mode="json")
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
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "schedule_report.json", schedule_report.model_dump(mode="json")
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
        self.runtime.transition(run_id, RunState.VALIDATION)
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
        validation_findings = self.quality.validators.evaluate(
            manifest, contract, dag, all_decisions, all_results, [artifact.as_path for artifact in artifacts]
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id,
                "validation_findings.json",
                [finding.model_dump(mode="json") for finding in validation_findings],
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "quality_report.json", quality.model_dump(mode="json")
            )
        )
        product_package = self.product_owner.assemble(
            manifest, contract, cards, dag, all_decisions, all_results, quality
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "product_package.json", product_package.model_dump(mode="json")
            )
        )
        artifacts.append(
            self.artifact_store.write_text_artifact(
                run_id, "final_report.md", product_package.final_markdown, ArtifactType.REPORT
            )
        )
        if "pdf" in contract.primary_artifacts:
            pdf_path = self.artifact_store.run_dir(run_id) / "final_report.pdf"
            pdf_artifact = self.artifact_builder.build_pdf(product_package.final_markdown, pdf_path)
            pdf_errors = self.artifact_builder.validate_pdf(pdf_path)
            artifacts.append(pdf_artifact)
            artifacts.append(
                self.artifact_store.write_json_artifact(
                    run_id, "pdf_validation.json", {"path": str(pdf_path), "errors": pdf_errors}
                )
            )
        if "docx" in contract.primary_artifacts:
            docx_path = self.artifact_store.run_dir(run_id) / "final_report.docx"
            docx_artifact = self.artifact_builder.build_docx(product_package.final_markdown, docx_path)
            docx_errors = self.artifact_builder.validate_docx(docx_path)
            artifacts.append(docx_artifact)
            artifacts.append(
                self.artifact_store.write_json_artifact(
                    run_id, "docx_validation.json", {"path": str(docx_path), "errors": docx_errors}
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
        self.runtime.save_run_summary(
            run_id,
            str(run_manifest.state),
            str(self.artifact_store.run_dir(run_id)),
            quality.passed,
        )
        self.runtime.transition(run_id, run_manifest.state)
        self.runtime.record_event(
            RuntimeEvent(
                run_id=run_id,
                event_type="delivered" if quality.passed else "validation_failed",
                payload={"artifact_count": len(run_manifest.artifacts), "quality_passed": quality.passed},
            )
        )

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
