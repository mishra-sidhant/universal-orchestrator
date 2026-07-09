from __future__ import annotations

from pathlib import Path

from universal_orchestrator.approvals import ApprovalGateEngine
from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.artifacts import ArtifactStore
from universal_orchestrator.budget import BudgetController
from universal_orchestrator.cache import SemanticCache
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.delta import DeltaPlanner
from universal_orchestrator.evidence import EvidenceAuditor
from universal_orchestrator.execution import DeterministicExecutor
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.integrity import ArtifactIntegrityAuditor
from universal_orchestrator.models import (
    Artifact,
    ArtifactType,
    HostInvocation,
    ProductContract,
    RuntimeEvent,
    RunManifest,
    RunResult,
    RunState,
    new_id,
    utc_now,
)
from universal_orchestrator.observability import DebugBundleBuilder, TraceRecorder
from universal_orchestrator.planning import PlannerEnsemble
from universal_orchestrator.product import FinalProductOwner
from universal_orchestrator.quality import QualityGateEngine
from universal_orchestrator.repair import RepairPlanner
from universal_orchestrator.repo_validation import RepoValidationRunner
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry
from universal_orchestrator.scheduler import DAGScheduler


class Orchestrator:
    def __init__(self, artifact_root: Path | str = ".uo/runs") -> None:
        self.artifact_store = ArtifactStore(Path(artifact_root))
        self.ingestor = InputIngestor()
        self.context = ContextIntelligence()
        self.contracts = ProductContractCompiler()
        self.approvals = ApprovalGateEngine()
        self.planner = PlannerEnsemble()
        self.budget = BudgetController()
        self.delta = DeltaPlanner()
        self.executor = DeterministicExecutor()
        self.quality = QualityGateEngine()
        self.evidence = EvidenceAuditor()
        self.repo_validation = RepoValidationRunner()
        self.repair = RepairPlanner()
        self.product_owner = FinalProductOwner()
        self.artifact_builder = ArtifactBuilder()
        self.debug_bundle = DebugBundleBuilder()
        self.integrity = ArtifactIntegrityAuditor()
        self.cache = SemanticCache(Path(artifact_root) / "_cache")
        self.runtime = RuntimeStore(Path(artifact_root) / "runtime.sqlite3")
        self.scheduler = DAGScheduler(self.cache)

    def run(self, invocation: HostInvocation) -> RunResult:
        run_id = new_id("run")
        trace = TraceRecorder(run_id)
        started_at = utc_now()
        self.runtime.record_event(RuntimeEvent(run_id=run_id, event_type="received", payload={"host": invocation.host}))
        self.runtime.transition(run_id, RunState.RECEIVED)

        manifest = self.ingestor.ingest(invocation, run_id)
        self.runtime.transition(run_id, RunState.INGESTING)
        trace.checkpoint("ingestion", {"input_count": len(manifest.inputs), "parsed_count": manifest.parsed_count})
        raw_cards = self.context.deduplicate_cards(self.context.build_cards(manifest))
        cards = self.context.rank_cards(invocation.prompt, raw_cards)
        chunks = self.context.chunk_manifest(manifest)
        provenance = self.context.provenance(cards, chunks)
        context_index = self.context.build_index(cards)
        conflicts = self.context.detect_conflicts(cards)
        trace.checkpoint(
            "context_indexing",
            {"card_count": len(cards), "chunk_count": len(chunks), "conflict_count": len(conflicts)},
        )
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
        cache_context = {"context_cache_key": cache_key}
        contract = self.contracts.compile(invocation, manifest)
        self.runtime.transition(run_id, RunState.CONTRACTING)
        trace.checkpoint("contracting", {"run_type": contract.run_type, "artifacts": contract.primary_artifacts})
        approval_report = self.approvals.evaluate(invocation, manifest, contract)
        dag = self.planner.create_execution_plan(run_id, contract)
        self.runtime.transition(run_id, RunState.PLANNING)
        context_packs = self.context.compile_packs_for_tasks([node.id for node in dag.nodes], cards)
        dag, budget_report = self.budget.apply(invocation, dag, context_packs)
        plan_review = self.planner.review_plan(run_id, contract, dag)
        delta_plan = self.delta.plan(manifest, dag, self.runtime, self.scheduler, cache_context)
        trace.checkpoint(
            "planning",
            {
                "task_count": len(dag.nodes),
                "budget_profile": budget_report.requested_profile,
                "reusable_task_count": len(delta_plan.reusable_task_ids),
            },
        )

        registry = CapabilityRegistry.from_environment()
        router = AdaptiveRouter(registry)
        decisions, routing_telemetry = router.route_all_with_telemetry(run_id, dag.topological_order())
        self.runtime.transition(run_id, RunState.ROUTING)
        trace.checkpoint(
            "routing",
            {"decision_count": len(decisions), "provider_count": routing_telemetry.provider_count},
        )
        execution_context = {
            "run_id": run_id,
            "contract": contract.model_dump(mode="json"),
            "input_refs": [item.id for item in manifest.inputs],
            "files": [item.path for item in manifest.inputs if item.path],
            "security_findings_count": sum(len(item.security_findings) for item in manifest.inputs),
            "context_card_count": len(cards),
            "context_chunk_count": len(chunks),
            "context_pack_count": len(context_packs),
            "delta_reusable_task_count": len(delta_plan.reusable_task_ids),
            "approval_blocked": approval_report.blocked,
            "approval_warning_count": len(approval_report.warnings),
        }
        self.executor = DeterministicExecutor(
            adapters=registry.adapter_registry(),
            prompt=invocation.prompt,
            allow_network=invocation.user_options.allow_internet,
            dry_run_external=not invocation.user_options.allow_internet,
            context=execution_context,
        )
        self.runtime.transition(run_id, RunState.EXECUTING)
        results, schedule_report = self.scheduler.execute(dag, decisions, self.executor, cache_context)
        for record in schedule_report.records:
            self.runtime.save_task_record(run_id, record.task_id, str(record.status), record.attempt, record.cache_key)
        trace.checkpoint(
            "execution",
            {"result_count": len(results), "cache_hits": len(schedule_report.cache_hits)},
        )
        repo_validation_report = self.repo_validation.run(invocation, manifest)
        trace.checkpoint(
            "repo_validation",
            {
                "executed": repo_validation_report.executed,
                "passed": repo_validation_report.passed,
                "command_count": len(repo_validation_report.command_results),
            },
        )

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
                run_id, "approval_report.json", approval_report.model_dump(mode="json")
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
                run_id, "budget_report.json", budget_report.model_dump(mode="json")
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "delta_execution_plan.json", delta_plan.model_dump(mode="json")
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
                "routing_telemetry.json",
                routing_telemetry.model_dump(mode="json"),
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
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "repo_validation_report.json", repo_validation_report.model_dump(mode="json")
            )
        )

        quality = self.quality.evaluate(
            manifest=manifest,
            contract=contract,
            dag=dag,
            decisions=decisions,
            results=results,
            artifact_paths=[artifact.as_path for artifact in artifacts],
            repo_validation_report=repo_validation_report,
        )
        all_decisions = list(decisions)
        all_results = list(results)
        self.runtime.transition(run_id, RunState.VALIDATION)
        trace.checkpoint("validation", {"quality_passed": quality.passed, "violations": len(quality.violations)})
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
                repo_validation_report=repo_validation_report,
            )
            trace.checkpoint(
                "repair_execution",
                {"repair_tasks": len(repair_dag.nodes), "quality_passed": quality.passed},
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
        product_package = self.product_owner.assemble(
            manifest, contract, cards, dag, all_decisions, all_results, quality
        )
        evidence_audit = self.evidence.audit(product_package, cards, provenance, all_results)
        quality = self.evidence.apply_to_quality(
            quality,
            evidence_audit,
            source_required="source-aware synthesis" in contract.must_have,
        )
        product_package = self.product_owner.assemble(
            manifest, contract, cards, dag, all_decisions, all_results, quality
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "evidence_audit.json", evidence_audit.model_dump(mode="json")
            )
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "quality_report.json", quality.model_dump(mode="json")
            )
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
        if "patch" in contract.primary_artifacts or contract.run_type == "repo_implementation":
            patch_path = self.artifact_store.run_dir(run_id) / "implementation_patch.diff"
            patch_artifact = self.artifact_builder.build_patch_plan(product_package.final_markdown, patch_path)
            patch_errors = self.artifact_builder.validate_patch(patch_path)
            artifacts.append(patch_artifact)
            artifacts.append(
                self.artifact_store.write_json_artifact(
                    run_id, "patch_validation.json", {"path": str(patch_path), "errors": patch_errors}
                )
            )
        zip_path = self.artifact_store.run_dir(run_id) / "delivery_bundle.zip"
        zip_artifact = self.artifact_builder.build_zip(artifacts, zip_path)
        zip_errors = self.artifact_builder.validate_zip(zip_path)
        artifacts.append(zip_artifact)
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "zip_validation.json", {"path": str(zip_path), "errors": zip_errors}
            )
        )
        integrity_report = self.integrity.audit(run_id, artifacts, self._expected_artifact_names(contract))
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "artifact_integrity_report.json", integrity_report.model_dump(mode="json")
            )
        )
        final_state = RunState.DELIVERED if quality.passed else RunState.VALIDATION
        trace.checkpoint("final_assembly", {"artifact_count": len(artifacts), "quality_passed": quality.passed})
        trace_report = trace.report(
            final_state=final_state,
            event_count=len(self.runtime.list_events(run_id)),
            artifact_count=len(artifacts) + 2,
            warning_count=len(manifest.warnings) + len(quality.warnings),
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "trace_report.json", trace_report.model_dump(mode="json")
            )
        )
        debug_manifest = self.debug_bundle.build(run_id, artifacts)
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "debug_bundle_manifest.json", debug_manifest.model_dump(mode="json")
            )
        )

        run_manifest = RunManifest(
            run_id=run_id,
            invocation=invocation,
            state=final_state,
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

    def _expected_artifact_names(self, contract: ProductContract) -> list[str]:
        expected = [
            "context_manifest.json",
            "context_cards.json",
            "context_chunks.json",
            "context_provenance.json",
            "context_packs.json",
            "context_index.json",
            "product_contract.json",
            "approval_report.json",
            "task_dag.json",
            "plan_review.json",
            "budget_report.json",
            "delta_execution_plan.json",
            "routing_decisions.json",
            "routing_telemetry.json",
            "execution_results.json",
            "schedule_report.json",
            "repo_validation_report.json",
            "validation_findings.json",
            "evidence_audit.json",
            "quality_report.json",
            "product_package.json",
            "final_report.md",
            "delivery_bundle.zip",
            "zip_validation.json",
        ]
        if "pdf" in contract.primary_artifacts:
            expected.extend(["final_report.pdf", "pdf_validation.json"])
        if "docx" in contract.primary_artifacts:
            expected.extend(["final_report.docx", "docx_validation.json"])
        if "patch" in contract.primary_artifacts or contract.run_type == "repo_implementation":
            expected.extend(["implementation_patch.diff", "patch_validation.json"])
        return expected
