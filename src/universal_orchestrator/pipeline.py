from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any

from universal_orchestrator.approvals import ApprovalGateEngine
from universal_orchestrator.artifact_builders import ArtifactBuilder
from universal_orchestrator.artifacts import ArtifactStore
from universal_orchestrator.budget import BudgetController
from universal_orchestrator.cache import ExactMatchCache
from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.cost_ledger import CostLedger
from universal_orchestrator.contracts import ProductContractCompiler
from universal_orchestrator.delta import DeltaPlanner
from universal_orchestrator.evidence import EvidenceAuditor
from universal_orchestrator.errors import RunCancelledError
from universal_orchestrator.execution_policy import PolicyCompiler
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.integrity import ArtifactIntegrityAuditor
from universal_orchestrator.handoff import HandoffController
from universal_orchestrator.models import (
    ApprovalReport,
    Artifact,
    ArtifactType,
    BudgetReport,
    ContextCard,
    ContextChunk,
    ContextManifest,
    ContextPack,
    ClaimVerificationStatus,
    DeltaExecutionPlan,
    ExecutionResult,
    ExecutionPolicy,
    HostInvocation,
    InputType,
    PlanReview,
    ProductContract,
    ProductPlan,
    ProviderKind,
    ProvenanceRecord,
    QualityGateResult,
    QualityScore,
    RepoValidationReport,
    RoutingDecision,
    RoutingTelemetryReport,
    RuntimeEvent,
    RunManifest,
    RunResult,
    RunState,
    SlideSpec,
    TaskDAG,
    ValidatorPanelReport,
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
from universal_orchestrator.security import redact_text, scan_text
from universal_orchestrator.stages import KernelStageContext, StageWorkerRegistry
from universal_orchestrator.utils import read_json, sha256_file


class Orchestrator:
    def __init__(
        self,
        artifact_root: Path | str = ".uo/runs",
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.artifact_store = ArtifactStore(Path(artifact_root))
        self.ingestor = InputIngestor()
        self.context = ContextIntelligence()
        self.contracts = ProductContractCompiler()
        self.approvals = ApprovalGateEngine()
        self.policy_compiler = PolicyCompiler()
        self.planner = PlannerEnsemble()
        self.budget = BudgetController()
        self.delta = DeltaPlanner()
        self.quality = QualityGateEngine()
        self.evidence = EvidenceAuditor()
        self.repo_validation = RepoValidationRunner()
        self.repair = RepairPlanner()
        self.product_owner = FinalProductOwner()
        self.artifact_builder = ArtifactBuilder()
        self.debug_bundle = DebugBundleBuilder()
        self.integrity = ArtifactIntegrityAuditor()
        self.cache = ExactMatchCache(Path(artifact_root) / "_cache")
        self.runtime = RuntimeStore(Path(artifact_root) / "runtime.sqlite3")
        self.scheduler = DAGScheduler(self.cache, runtime_store=self.runtime)
        self.capability_registry = capability_registry

    def run(self, invocation: HostInvocation, run_id: str | None = None) -> RunResult:
        run_id = run_id or new_id("run")
        started_at = utc_now()
        self.runtime.record_event(RuntimeEvent(run_id=run_id, event_type="received", payload={"host": invocation.host}))
        self.runtime.transition(run_id, RunState.RECEIVED)
        request_artifact = self.artifact_store.write_json_artifact(
            run_id,
            "run_request.json",
            self._redacted_invocation(invocation).model_dump(mode="json"),
        )
        return self._run_with_failure_boundary(invocation, run_id, started_at, request_artifact)

    def resume(self, run_id: str) -> RunResult:
        state = self.runtime.latest_state(run_id)
        if state == RunState.DELIVERED:
            raise ValueError(f"Run {run_id} is already delivered and does not require resume.")
        request_path = self.artifact_store.run_dir(run_id) / "run_request.json"
        if not request_path.exists():
            raise FileNotFoundError(f"Run request is unavailable for {run_id}.")
        invocation = HostInvocation.model_validate(read_json(request_path))
        self.runtime.clear_cancel(run_id)
        self.runtime.record_event(RuntimeEvent(run_id=run_id, event_type="resume_requested"))
        self.runtime.transition(run_id, RunState.RECEIVED)
        request_artifact = self.artifact_store.write_json_artifact(
            run_id, "run_request.json", invocation.model_dump(mode="json")
        )
        return self._run_with_failure_boundary(invocation, run_id, utc_now(), request_artifact)

    def _run_with_failure_boundary(
        self,
        invocation: HostInvocation,
        run_id: str,
        started_at: datetime,
        request_artifact: Artifact,
    ) -> RunResult:
        try:
            self._ensure_not_cancelled(run_id)
            return self._run_pipeline(invocation, run_id, started_at, request_artifact)
        except RunCancelledError:
            if self.runtime.latest_state(run_id) != RunState.CANCELLED:
                self.runtime.transition(run_id, RunState.CANCELLED)
            self.runtime.save_run_summary(
                run_id,
                str(RunState.CANCELLED),
                str(self.artifact_store.run_dir(run_id)),
                False,
            )
            self.runtime.record_event(RuntimeEvent(run_id=run_id, event_type="cancelled"))
            raise
        except Exception as exc:
            stage = self.runtime.latest_state(run_id) or str(RunState.RECEIVED)
            self.runtime.save_failure(run_id, stage, exc)
            self.artifact_store.write_json_artifact(
                run_id,
                "failure.json",
                {"run_id": run_id, "stage": stage, "error_type": type(exc).__name__, "message": str(exc)},
            )
            self.runtime.transition(run_id, RunState.FAILED)
            self.runtime.save_run_summary(
                run_id,
                str(RunState.FAILED),
                str(self.artifact_store.run_dir(run_id)),
                False,
            )
            self.runtime.record_event(
                RuntimeEvent(
                    run_id=run_id,
                    event_type="failed",
                    payload={"stage": stage, "error_type": type(exc).__name__},
                )
            )
            raise

    def _run_pipeline(
        self,
        invocation: HostInvocation,
        run_id: str,
        started_at: datetime,
        request_artifact: Artifact,
    ) -> RunResult:
        trace = TraceRecorder(run_id)

        self.runtime.transition(run_id, RunState.INGESTING)
        manifest = self.ingestor.ingest(invocation, run_id)
        self._ensure_not_cancelled(run_id)
        trace.checkpoint("ingestion", {"input_count": len(manifest.inputs), "parsed_count": manifest.parsed_count})
        self.runtime.transition(run_id, RunState.CONTEXT_INDEXING)
        raw_cards = self.context.deduplicate_cards(self.context.build_cards(manifest))
        cards = self.context.rank_cards(invocation.prompt, raw_cards)
        chunks = self.context.chunk_manifest(manifest)
        provenance = self.context.provenance(cards, chunks)
        context_index = self.context.build_index(cards)
        conflicts = self.context.detect_conflicts(cards)
        self._ensure_not_cancelled(run_id)
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
        self.runtime.transition(run_id, RunState.CONTRACTING)
        contract = self.contracts.compile(invocation, manifest)
        trace.checkpoint("contracting", {"run_type": contract.run_type, "artifacts": contract.primary_artifacts})
        approval_report = self.approvals.evaluate(invocation, manifest, contract)
        execution_policy = self.policy_compiler.compile(invocation, manifest)
        cost_ledger = CostLedger(run_id, invocation.user_options.cost_ceiling_usd)
        registry = self.capability_registry or CapabilityRegistry.from_environment(
            runtime_store=self.runtime
        )
        registry.cost_ledger = cost_ledger
        registry.bind_runtime(self.runtime)
        handoff_controller = HandoffController(registry.capacity_broker, self.runtime)
        registry.refresh_health(
            execution_policy,
            allow_network=invocation.user_options.allow_internet,
        )
        provider_health_notices = [
            f"{provider.id} is {provider.health.status}: {provider.health.message}"
            for provider in registry.providers
            if provider.enabled and provider.health.status != "healthy"
        ]
        model_synthesis = self._model_synthesis_available(
            registry,
            execution_policy,
            invocation,
        )
        self.runtime.transition(run_id, RunState.PLANNING)
        dag = self.planner.create_execution_plan(
            run_id,
            contract,
            model_synthesis=model_synthesis,
        )
        context_packs = self.context.compile_packs_for_tasks(
            [node.id for node in dag.nodes],
            cards,
            chunks=chunks,
            task_queries={
                node.id: f"{redact_text(invocation.prompt)} {node.title} {node.task_type}"
                for node in dag.nodes
            },
        )
        dag, budget_report = self.budget.apply(invocation, dag, context_packs)
        product_plan = self.planner.create_product_plan(
            run_id,
            contract,
            [node.id for node in dag.topological_order()],
        )
        product_plan_errors = self.planner.validate_product_plan(product_plan, dag, contract)
        plan_review = self.planner.review_plan(run_id, contract, dag)
        self._ensure_not_cancelled(run_id)
        trace.checkpoint(
            "planning",
            {
                "task_count": len(dag.nodes),
                "budget_profile": budget_report.requested_profile,
                "plan_review_score": plan_review.score,
            },
        )

        router = AdaptiveRouter(registry, execution_policy)
        self.runtime.transition(run_id, RunState.ROUTING)
        decisions, routing_telemetry = router.route_all_with_telemetry(run_id, dag.topological_order())
        budget_report = self.budget.reconcile_estimated_usage(
            budget_report,
            decisions,
            context_packs,
        )
        cache_context = {
            "schema_version": "2.0",
            "context_cache_key": cache_key,
            "contract_key": self.cache.key_for(
                "contract", contract.model_dump(mode="json", exclude={"id"})
            ),
            "policy_key": self.cache.key_for(
                "policy",
                {
                    "schema_version": execution_policy.schema_version,
                    "privacy_mode": execution_policy.privacy_mode,
                    "allow_network_fetch": execution_policy.allow_network_fetch,
                    "allow_hosted_models": execution_policy.allow_hosted_models,
                    "allow_private_data_egress": execution_policy.allow_private_data_egress,
                    "allow_shell": execution_policy.allow_shell,
                    "allow_repo_writes": execution_policy.allow_repo_writes,
                },
            ),
            "providers_key": self.cache.key_for(
                "providers",
                [provider.model_dump(mode="json") for provider in registry.providers],
            ),
            "routing": {
                decision.task_id: {
                    "action": decision.action,
                    "provider_id": decision.provider_id,
                }
                for decision in decisions
            },
        }
        delta_plan = self.delta.plan(manifest, dag, self.runtime, self.scheduler, cache_context)
        self._ensure_not_cancelled(run_id)
        trace.checkpoint(
            "routing",
            {
                "decision_count": len(decisions),
                "provider_count": routing_telemetry.provider_count,
                "reusable_task_count": len(delta_plan.reusable_task_ids),
            },
        )
        source_input_ids = {
            item.id for item in manifest.inputs if item.type != InputType.PROMPT
        }
        chunk_refs_by_task: dict[str, list[str]] = {}
        for task_id, pack in context_packs.items():
            source_refs = [
                chunk.id
                for chunk in pack.chunks
                if chunk.input_id in source_input_ids
                and not any(
                    finding.kind == "prompt_injection_risk"
                    for finding in scan_text(chunk.text)
                )
            ]
            prompt_refs = [
                chunk.id for chunk in pack.chunks if chunk.input_id not in source_input_ids
            ]
            chunk_refs_by_task[task_id] = (
                (source_refs or prompt_refs)[:3]
                if task_id.startswith("T-CHAPTER-") or task_id == "T-SYNTHESIS"
                else []
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

        stage_context: KernelStageContext

        def build_static_artifacts() -> list[Artifact]:
            return self._build_static_artifacts(
                run_id=run_id,
                request_artifact=request_artifact,
                manifest=manifest,
                cards=cards,
                chunks=chunks,
                provenance=provenance,
                context_packs=context_packs,
                context_index=context_index,
                retrieval_hits=self.context.retrieval_hits_by_task,
                capacity_snapshots=[
                    snapshot.model_dump(mode="json")
                    for snapshot in registry.capacity_broker.snapshots()
                ],
                conflicts=conflicts,
                cache_key=cache_key,
                contract=contract,
                approval_report=approval_report,
                execution_policy=execution_policy,
                dag=dag,
                product_plan=product_plan,
                product_plan_errors=product_plan_errors,
                plan_review=plan_review,
                budget_report=budget_report,
                cost_ledger=cost_ledger,
                delta_plan=delta_plan,
                decisions=decisions,
                routing_telemetry=routing_telemetry,
                repo_validation_report=repo_validation_report,
                provider_health_report={
                    "run_id": run_id,
                    "providers": [
                        provider.model_dump(mode="json") for provider in registry.providers
                    ],
                },
            )

        def evaluate_stage_quality(stage_results: list[ExecutionResult]) -> QualityGateResult:
            return self.quality.evaluate(
                manifest=manifest,
                contract=contract,
                dag=dag,
                decisions=decisions,
                results=stage_results,
                artifact_paths=[artifact.as_path for artifact in stage_context.artifacts],
                repo_validation_report=repo_validation_report,
                product_plan=product_plan,
            )

        stage_context = KernelStageContext(
            manifest=manifest,
            contract=contract,
            cards=cards,
            chunks=chunks,
            conflicts=conflicts,
            chunk_refs_by_task=chunk_refs_by_task,
            build_static_artifacts=build_static_artifacts,
            evaluate_quality=evaluate_stage_quality,
            context_packs=context_packs,
            provider_adapters=registry.adapter_registry(),
            operator_prompt=redact_text(invocation.prompt),
            execution_policy=execution_policy,
            provider_health_notices=provider_health_notices,
            handoff_controller=handoff_controller,
        )
        executor = StageWorkerRegistry(stage_context)
        self.runtime.transition(run_id, RunState.EXECUTING)
        results, schedule_report = self.scheduler.execute(
            dag,
            decisions,
            executor,
            cache_context,
            cancellation_check=lambda: self.runtime.is_cancel_requested(run_id),
        )
        for record in schedule_report.records:
            self.runtime.save_task_attempt(
                run_id,
                record.task_id,
                record.attempt,
                str(record.status),
                record.cache_key,
                record.warnings,
            )
            self.runtime.save_task_record(run_id, record.task_id, str(record.status), record.attempt, record.cache_key)
        self._ensure_not_cancelled(run_id)
        trace.checkpoint(
            "execution",
            {"result_count": len(results), "cache_hits": len(schedule_report.cache_hits)},
        )
        artifacts = stage_context.artifacts or [request_artifact]
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
        quality_payload = next(
            (
                result.output.get("worker_output", {}).get("quality_result")
                for result in results
                if result.task_id == "T-QUALITY"
                and isinstance(result.output.get("worker_output"), dict)
            ),
            None,
        )
        quality = (
            QualityGateResult.model_validate(quality_payload)
            if quality_payload
            else self._missing_quality_stage_result()
        )
        all_decisions = list(decisions)
        all_results = list(results)
        evidence_audit = self.evidence.audit(
            None,
            cards,
            provenance,
            all_results,
            chunks,
            run_id=run_id,
            consumed_chunk_refs_by_task=chunk_refs_by_task,
        )
        quality = self.evidence.apply_to_quality(
            quality,
            evidence_audit,
            source_required="source-aware synthesis" in contract.must_have,
        )
        self.runtime.transition(run_id, RunState.VALIDATION)
        trace.checkpoint("validation", {"quality_passed": quality.passed, "violations": len(quality.violations)})
        if not quality.passed:
            self.runtime.transition(run_id, RunState.REPAIR_EXECUTION)
            repair_dag = self.repair.create_repair_dag(run_id, quality)
            repair_decisions = router.route_all(repair_dag.topological_order())
            repair_results, repair_schedule = self.scheduler.execute(
                repair_dag,
                repair_decisions,
                executor,
                {**cache_context, "repair": True},
                cancellation_check=lambda: self.runtime.is_cancel_requested(run_id),
            )
            for record in repair_schedule.records:
                self.runtime.save_task_attempt(
                    run_id,
                    record.task_id,
                    record.attempt,
                    str(record.status),
                    record.cache_key,
                    record.warnings,
                )
                self.runtime.save_task_record(
                    run_id,
                    record.task_id,
                    str(record.status),
                    record.attempt,
                    record.cache_key,
                )
            all_decisions.extend(repair_decisions)
            all_results.extend(repair_results)
            schedule_report = schedule_report.model_copy(
                update={
                    "records": [*schedule_report.records, *repair_schedule.records],
                    "execution_order": [
                        *schedule_report.execution_order,
                        *repair_schedule.execution_order,
                    ],
                    "parallel_batches": [
                        *schedule_report.parallel_batches,
                        *repair_schedule.parallel_batches,
                    ],
                    "cache_hits": [*schedule_report.cache_hits, *repair_schedule.cache_hits],
                    "failed_tasks": [
                        *schedule_report.failed_tasks,
                        *repair_schedule.failed_tasks,
                    ],
                }
            )
            self._replace_artifact(
                artifacts,
                self.artifact_store.write_json_artifact(
                    run_id, "schedule_report.json", schedule_report.model_dump(mode="json")
                ),
            )
            self._replace_artifact(
                artifacts,
                self.artifact_store.write_json_artifact(
                    run_id,
                    "routing_decisions.json",
                    [decision.model_dump(mode="json") for decision in all_decisions],
                ),
            )
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
            evidence_audit = self.evidence.audit(
                None,
                cards,
                provenance,
                all_results,
                chunks,
                run_id=run_id,
                consumed_chunk_refs_by_task=chunk_refs_by_task,
            )
            quality = self.evidence.apply_to_quality(
                quality,
                evidence_audit,
                source_required="source-aware synthesis" in contract.must_have,
            )
            trace.checkpoint(
                "repair_execution",
                {"repair_tasks": len(repair_dag.nodes), "quality_passed": quality.passed},
            )
        cost_ledger_report = cost_ledger.snapshot()
        budget_report = self.budget.reconcile_actual_usage(budget_report, cost_ledger_report)
        self._replace_artifact(
            artifacts,
            self.artifact_store.write_json_artifact(
                run_id, "cost_ledger.json", cost_ledger_report.model_dump(mode="json")
            ),
        )
        self._replace_artifact(
            artifacts,
            self.artifact_store.write_json_artifact(
                run_id, "budget_report.json", budget_report.model_dump(mode="json")
            ),
        )
        quality_warnings = list(quality.warnings)
        if budget_report.estimate_actual_reconciliation.get("diverged"):
            quality_warnings.extend(
                warning for warning in budget_report.warnings if warning not in quality_warnings
            )
        quality_violations = list(quality.violations)
        if cost_ledger_report.budget_stop:
            quality_violations.append(
                f"Budget stop prevented provider call for {cost_ledger_report.budget_stop.task_id}: "
                f"{cost_ledger_report.budget_stop.reason}"
            )
        quality = quality.model_copy(
            update={
                "passed": quality.passed and not bool(cost_ledger_report.budget_stop),
                "warnings": quality_warnings,
                "violations": quality_violations,
            }
        )
        validation_findings = self.quality.validators.evaluate(
            manifest,
            contract,
            dag,
            all_decisions,
            all_results,
            [artifact.as_path for artifact in artifacts],
            product_plan=product_plan,
        )
        validator_panel = ValidatorPanelReport(
            run_id=run_id,
            passed=not any(
                not finding.passed and finding.severity in {"high", "critical"}
                for finding in validation_findings
            ),
            finding_count=len(validation_findings),
            failed_validators=sorted(
                {finding.validator for finding in validation_findings if not finding.passed}
            ),
            findings=validation_findings,
        )
        panel_violations = [
            finding.message
            for finding in validation_findings
            if not finding.passed and finding.severity in {"high", "critical"}
        ]
        if panel_violations:
            quality = quality.model_copy(
                update={
                    "passed": False,
                    "violations": [*quality.violations, *panel_violations],
                }
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
                run_id, "validator_panel.json", validator_panel.model_dump(mode="json")
            )
        )
        supported_evidence_refs_by_task: dict[str, list[str]] = {}
        blocked_claims: list[str] = []
        for claim in evidence_audit.claims:
            if not claim.citation_eligible:
                if (
                    claim.verification is not None
                    and claim.verification.status
                    in {
                        ClaimVerificationStatus.CONTRADICTED,
                        ClaimVerificationStatus.INSUFFICIENT,
                    }
                ):
                    blocked_claims.append(
                        f"{claim.task_id}: {claim.blocked_reason or 'configured verifier blocked the claim'}"
                    )
                continue
            supported_evidence_refs_by_task.setdefault(claim.task_id, [])
            supported_evidence_refs_by_task[claim.task_id] = list(
                dict.fromkeys(
                    [*supported_evidence_refs_by_task[claim.task_id], *claim.evidence_refs]
                )
            )
        self.runtime.transition(run_id, RunState.FINAL_ASSEMBLY)
        product_package = self.product_owner.assemble(
            manifest,
            contract,
            cards,
            dag,
            all_decisions,
            all_results,
            quality,
            chunks,
            provenance,
            supported_evidence_refs_by_task,
            blocked_claims,
            product_plan,
        )
        manuscript_artifact = self.artifact_store.write_json_artifact(
            run_id,
            "manuscript.json",
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "chapters": [
                    {
                        "task_id": result.task_id,
                        "chapter_id": result.output.get("worker_output", {}).get("chapter_id"),
                        "chapter_title": result.output.get("worker_output", {}).get("chapter_title"),
                        "objective": result.output.get("worker_output", {}).get("objective"),
                        "synthesis_path": result.output.get("worker_output", {}).get("synthesis_path"),
                        "sections": result.output.get("worker_output", {}).get("manuscript", []),
                    }
                    for result in all_results
                    if isinstance(result.output.get("worker_output"), dict)
                    and result.output.get("worker_output", {}).get("chapter_id")
                ],
            },
        )
        artifacts.append(manuscript_artifact)
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id, "product_package.json", product_package.model_dump(mode="json")
            )
        )
        self.runtime.transition(run_id, RunState.ARTIFACT_BUILD)
        artifacts.append(
            self.artifact_store.write_text_artifact(
                run_id, "final_report.md", product_package.final_markdown, ArtifactType.REPORT
            )
        )
        evidence_audit = self.evidence.audit(
            product_package,
            cards,
            provenance,
            all_results,
            chunks,
            run_id=run_id,
            consumed_chunk_refs_by_task=chunk_refs_by_task,
        )
        quality = self.evidence.apply_to_quality(
            quality,
            evidence_audit,
            source_required="source-aware synthesis" in contract.must_have,
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
        validation_jobs: list[tuple[str, Path]] = []
        if "pdf" in contract.primary_artifacts:
            pdf_path = self.artifact_store.run_dir(run_id) / "final_report.pdf"
            pdf_artifact = self.artifact_builder.build_pdf(product_package.final_markdown, pdf_path)
            artifacts.append(pdf_artifact)
            validation_jobs.append(("pdf", pdf_path))
        if "docx" in contract.primary_artifacts:
            docx_path = self.artifact_store.run_dir(run_id) / "final_report.docx"
            docx_artifact = self.artifact_builder.build_docx(product_package.final_markdown, docx_path)
            artifacts.append(docx_artifact)
            validation_jobs.append(("docx", docx_path))
        if "pptx" in contract.primary_artifacts:
            pptx_path = self.artifact_store.run_dir(run_id) / "final_report.pptx"
            chapter_titles = {
                node.id: node.chapter_title
                for node in dag.nodes
                if node.chapter_id and node.chapter_title
            }
            slides: list[SlideSpec] = []
            for result in all_results:
                title = chapter_titles.get(result.task_id)
                worker_output = result.output.get("worker_output", {})
                if title is None or not isinstance(worker_output, dict):
                    continue
                body = [str(worker_output.get("summary", ""))]
                body.extend(
                    str(finding.get("message", ""))
                    for finding in worker_output.get("findings", [])[:4]
                    if isinstance(finding, dict) and finding.get("message")
                )
                refs = worker_output.get("evidence_refs", [])
                slides.append(
                    SlideSpec(
                        title=title,
                        body=body,
                        notes=f"Evidence refs: {', '.join(str(ref) for ref in refs)}",
                    )
                )
            if not slides:
                slides = [
                    SlideSpec(
                        title="Universal Orchestrator Report",
                        body=product_package.final_markdown.splitlines()[:12],
                    )
                ]
            pptx_artifact = self.artifact_builder.build_pptx(slides, pptx_path)
            artifacts.append(pptx_artifact)
            validation_jobs.append(("pptx", pptx_path))
        if "patch" in contract.primary_artifacts or contract.run_type == "repo_implementation":
            patch_path = self.artifact_store.run_dir(run_id) / "patch_plan.md"
            patch_artifact = self.artifact_builder.build_patch_plan(
                product_package.final_markdown,
                patch_path,
                product_plan=product_plan,
                repo_validation_report=repo_validation_report,
            )
            artifacts.append(patch_artifact)
            validation_jobs.append(("patch_plan", patch_path))

        self.runtime.transition(run_id, RunState.ARTIFACT_VALIDATION)
        validators = {
            "pdf": self.artifact_builder.validate_pdf,
            "docx": self.artifact_builder.validate_docx,
            "pptx": self.artifact_builder.validate_pptx,
            "patch_plan": self.artifact_builder.validate_patch_plan,
        }
        artifact_validation_errors: list[str] = []
        artifact_validation_warnings: list[str] = []
        for artifact_kind, artifact_path in validation_jobs:
            if artifact_kind == "patch_plan":
                validation_errors = validators[artifact_kind](artifact_path)
                validation_warnings: list[str] = []
            else:
                validation_errors, validation_warnings = self.artifact_builder.validate_rendered(
                    artifact_kind,
                    artifact_path,
                    contract.quality_bar,
                    [node.chapter_title for node in dag.nodes if node.chapter_title]
                    if artifact_kind == "pptx"
                    else ["Universal Orchestrator Final Product"],
                )
            artifact_validation_errors.extend(
                f"{artifact_kind}: {error}" for error in validation_errors
            )
            artifact_validation_warnings.extend(
                f"{artifact_kind}: {warning}" for warning in validation_warnings
            )
            artifacts.append(
                self.artifact_store.write_json_artifact(
                    run_id,
                    f"{artifact_kind}_validation.json",
                    {
                        "path": str(artifact_path),
                        "quality_bar": contract.quality_bar,
                        "errors": validation_errors,
                        "warnings": validation_warnings,
                    },
                )
            )

        if artifact_validation_errors or artifact_validation_warnings:
            quality = quality.model_copy(
                update={
                    "passed": quality.passed and not artifact_validation_errors,
                    "violations": [*quality.violations, *artifact_validation_errors],
                    "warnings": [*quality.warnings, *artifact_validation_warnings],
                }
            )
            artifacts = [
                artifact for artifact in artifacts if artifact.name != "quality_report.json"
            ]
            artifacts.append(
                self.artifact_store.write_json_artifact(
                    run_id, "quality_report.json", quality.model_dump(mode="json")
                )
            )

        final_state = RunState.DELIVERED if quality.passed else RunState.NEEDS_ATTENTION
        self._ensure_not_cancelled(run_id)
        trace.checkpoint(
            "final_assembly",
            {"artifact_count": len(artifacts), "quality_passed": quality.passed},
        )
        trace_report = trace.report(
            final_state=final_state,
            event_count=len(self.runtime.list_events(run_id)),
            artifact_count=len(artifacts) + 3,
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

        integrity_report = self.integrity.audit(
            run_id, artifacts, self._expected_artifact_names(contract)
        )
        artifacts.append(
            self.artifact_store.write_json_artifact(
                run_id,
                "artifact_integrity_report.json",
                integrity_report.model_dump(mode="json"),
            )
        )

        return self._finalize_delivery(
            run_id=run_id,
            invocation=invocation,
            context_manifest=manifest,
            contract=contract,
            artifacts=artifacts,
            quality=quality,
            final_state=final_state,
            routing_decisions=all_decisions,
            started_at=started_at,
        )

    def _finalize_delivery(
        self,
        *,
        run_id: str,
        invocation: HostInvocation,
        context_manifest: ContextManifest,
        contract: ProductContract,
        artifacts: list[Artifact],
        quality: QualityGateResult,
        final_state: RunState,
        routing_decisions: list[RoutingDecision],
        started_at: datetime,
    ) -> RunResult:
        """Freeze a state-consistent manifest and only issue a receipt for a valid ZIP."""

        self.runtime.transition(run_id, RunState.PACKAGING)
        run_dir = self.artifact_store.run_dir(run_id)
        zip_path = run_dir / "delivery_bundle.zip"
        receipt_path = run_dir / "delivery_receipt.json"
        zip_attempts: list[dict[str, Any]] = []
        run_manifest: RunManifest | None = None
        run_manifest_artifact: Artifact | None = None
        checksums_artifact: Artifact | None = None
        zip_artifact: Artifact | None = None
        zip_errors: list[str] = []
        bundle_inputs: list[Artifact] = []
        receipt_path.unlink(missing_ok=True)

        for attempt in range(1, 3):
            quality_artifact = self.artifact_store.write_json_artifact(
                run_id, "quality_report.json", quality.model_dump(mode="json")
            )
            artifacts = [
                artifact for artifact in artifacts if artifact.name != "quality_report.json"
            ]
            artifacts.append(quality_artifact)
            run_manifest = RunManifest(
                run_id=run_id,
                invocation=self._redacted_invocation(invocation),
                state=final_state,
                context_manifest_path=str(run_dir / "context_manifest.json"),
                product_contract_path=str(run_dir / "product_contract.json"),
                task_dag_path=str(run_dir / "task_dag.json"),
                quality_report_path=str(run_dir / "quality_report.json"),
                checksums_path=str(run_dir / "checksums.json"),
                delivery_receipt_path=(
                    str(receipt_path) if final_state == RunState.DELIVERED else None
                ),
                artifacts=list(artifacts),
                warnings=context_manifest.warnings + quality.warnings,
                routing_decisions=routing_decisions,
                started_at=started_at,
                completed_at=utc_now(),
            )
            run_manifest_artifact = self.artifact_store.write_run_manifest(run_manifest)
            checksum_inputs = [*artifacts, run_manifest_artifact]
            checksums_artifact = self.artifact_store.write_json_artifact(
                run_id,
                "checksums.json",
                self.integrity.checksums_payload(run_id, checksum_inputs),
            )
            bundle_inputs = [*checksum_inputs, checksums_artifact]
            try:
                zip_path.unlink(missing_ok=True)
                zip_artifact = self.artifact_builder.build_zip(bundle_inputs, zip_path)
                zip_errors = self.artifact_builder.validate_zip(
                    zip_path, [artifact.name for artifact in bundle_inputs]
                )
            except Exception as exc:
                zip_artifact = None
                zip_errors = [
                    "Delivery bundle construction or validation failed: "
                    f"{type(exc).__name__}: {exc}"
                ]
                zip_path.unlink(missing_ok=True)
            zip_attempts.append({"attempt": attempt, "errors": zip_errors})
            if not zip_errors:
                break
            quality = quality.model_copy(
                update={
                    "passed": False,
                    "violations": [
                        *quality.violations,
                        *[f"delivery_bundle.zip: {error}" for error in zip_errors],
                    ],
                }
            )
            final_state = RunState.NEEDS_ATTENTION
            trace_path = run_dir / "trace_report.json"
            if trace_path.exists():
                trace_payload = read_json(trace_path)
                trace_payload["final_state"] = final_state
                trace_payload["warning_count"] = int(trace_payload.get("warning_count", 0)) + len(
                    zip_errors
                )
                trace_artifact = self.artifact_store.write_json_artifact(
                    run_id, "trace_report.json", trace_payload
                )
                artifacts = [
                    artifact for artifact in artifacts if artifact.name != "trace_report.json"
                ]
                artifacts.append(trace_artifact)

        if run_manifest is None or run_manifest_artifact is None or checksums_artifact is None:
            raise RuntimeError("Delivery finalization did not produce a manifest and checksums.")
        zip_validation_artifact = self.artifact_store.write_json_artifact(
            run_id,
            "zip_validation.json",
            {
                "schema_version": "2.0",
                "path": str(zip_path),
                "content_hash": sha256_file(zip_path) if zip_path.exists() else None,
                "errors": zip_errors,
                "attempts": zip_attempts,
            },
        )
        finalization_artifact = self.artifact_store.write_json_artifact(
            run_id,
            "delivery_finalization.json",
            {
                "schema_version": "1.0",
                "run_id": run_id,
                "state": final_state,
                "zip_valid": zip_artifact is not None and not zip_errors,
                "receipt_issued": (
                    final_state == RunState.DELIVERED
                    and zip_artifact is not None
                    and not zip_errors
                ),
                "attempts": zip_attempts,
            },
        )
        receipt_artifact: Artifact | None = None
        if final_state == RunState.DELIVERED and zip_artifact is not None and not zip_errors:
            receipt_artifact = self.artifact_store.write_json_artifact(
                run_id,
                "delivery_receipt.json",
                {
                    "schema_version": "2.0",
                    "run_id": run_id,
                    "state": final_state,
                    "bundle": zip_artifact.model_dump(mode="json"),
                    "manifest": run_manifest_artifact.model_dump(mode="json"),
                    "checksums": checksums_artifact.model_dump(mode="json"),
                    "validation": zip_validation_artifact.model_dump(mode="json"),
                    "bundle_inventory": sorted(artifact.name for artifact in bundle_inputs),
                    "issued_at": utc_now().isoformat(),
                },
            )
        else:
            receipt_path.unlink(missing_ok=True)

        delivery_artifacts = [
            *artifacts,
            run_manifest_artifact,
            checksums_artifact,
            zip_validation_artifact,
            finalization_artifact,
        ]
        if zip_artifact is not None:
            delivery_artifacts.insert(len(artifacts) + 2, zip_artifact)
        if receipt_artifact is not None:
            delivery_artifacts.append(receipt_artifact)
        self.runtime.save_run_summary(
            run_id,
            str(run_manifest.state),
            str(run_dir),
            quality.passed,
        )
        self.runtime.transition(run_id, run_manifest.state)
        self.runtime.record_event(
            RuntimeEvent(
                run_id=run_id,
                event_type="delivered" if run_manifest.state == RunState.DELIVERED else "needs_attention",
                payload={
                    "artifact_count": len(delivery_artifacts),
                    "quality_passed": quality.passed,
                    "zip_valid": not zip_errors,
                },
            )
        )
        return RunResult(
            run_id=run_id,
            state=run_manifest.state,
            artifact_dir=str(run_dir),
            manifest=run_manifest,
            quality=quality,
        )

    def _build_static_artifacts(
        self,
        *,
        run_id: str,
        request_artifact: Artifact,
        manifest: ContextManifest,
        cards: list[ContextCard],
        chunks: list[ContextChunk],
        provenance: list[ProvenanceRecord],
        context_packs: dict[str, ContextPack],
        context_index: dict[str, list[str]],
        retrieval_hits: dict[str, list[dict[str, object]]],
        capacity_snapshots: list[dict[str, Any]],
        conflicts: list[str],
        cache_key: str,
        contract: ProductContract,
        approval_report: ApprovalReport,
        execution_policy: ExecutionPolicy,
        dag: TaskDAG,
        product_plan: ProductPlan,
        product_plan_errors: list[str],
        plan_review: PlanReview,
        budget_report: BudgetReport,
        cost_ledger: CostLedger,
        delta_plan: DeltaExecutionPlan,
        decisions: list[RoutingDecision],
        routing_telemetry: RoutingTelemetryReport,
        repo_validation_report: RepoValidationReport,
        provider_health_report: dict[str, Any],
    ) -> list[Artifact]:
        payloads = [
            ("context_manifest.json", manifest.model_dump(mode="json")),
            ("context_cards.json", [card.model_dump(mode="json") for card in cards]),
            ("context_chunks.json", [chunk.model_dump(mode="json") for chunk in chunks]),
            (
                "context_provenance.json",
                [item.model_dump(mode="json") for item in provenance],
            ),
            (
                "context_packs.json",
                {task_id: pack.model_dump(mode="json") for task_id, pack in context_packs.items()},
            ),
            (
                "context_index.json",
                {"terms": context_index, "conflicts": conflicts, "cache_key": cache_key},
            ),
            (
                "retrieval_report.json",
                {
                    "embedding_model": self.context.retriever.provider.model_id,
                    "by_task": retrieval_hits,
                    "disclosure": "Hybrid retrieval is a ranking aid, not semantic entailment.",
                },
            ),
            (
                "capacity_report.json",
                {
                    "snapshots": capacity_snapshots,
                    "disclosure": "Unknown capacity is not treated as unlimited.",
                },
            ),
            ("product_contract.json", contract.model_dump(mode="json")),
            ("approval_report.json", approval_report.model_dump(mode="json")),
            ("policy_report.json", execution_policy.model_dump(mode="json")),
            ("task_dag.json", dag.model_dump(mode="json")),
            ("product_plan.json", product_plan.model_dump(mode="json")),
            ("product_plan_validation.json", {"errors": product_plan_errors}),
            ("plan_review.json", plan_review.model_dump(mode="json")),
            ("budget_report.json", budget_report.model_dump(mode="json")),
            ("cost_ledger.json", cost_ledger.snapshot().model_dump(mode="json")),
            ("delta_execution_plan.json", delta_plan.model_dump(mode="json")),
            (
                "routing_decisions.json",
                [decision.model_dump(mode="json") for decision in decisions],
            ),
            ("routing_telemetry.json", routing_telemetry.model_dump(mode="json")),
            (
                "repo_validation_report.json",
                repo_validation_report.model_dump(mode="json"),
            ),
            ("provider_health_report.json", provider_health_report),
        ]
        return [
            request_artifact,
            *[
                self.artifact_store.write_json_artifact(run_id, name, payload)
                for name, payload in payloads
            ],
        ]

    def _missing_quality_stage_result(self) -> QualityGateResult:
        message = "Quality stage did not complete; no quality evaluation is available."
        return QualityGateResult(
            passed=False,
            scores=QualityScore(
                completeness=0,
                parse_confidence=0,
                citation_support=0,
                continuity=0,
                routing_efficiency=0,
                artifact_presence="fail",
                code_validation="not_applicable",
            ),
            violations=[message],
            warnings=[message],
            repair_task_ids=["T-REPAIR-001"],
        )

    def list_runs(self) -> list[Path]:
        if not self.artifact_store.root.exists():
            return []
        return sorted([path for path in self.artifact_store.root.iterdir() if path.is_dir()])

    def artifact_manifest_path(self, run_id: str) -> Path:
        return self.artifact_store.run_dir(run_id) / "run_manifest.json"

    def _ensure_not_cancelled(self, run_id: str) -> None:
        if self.runtime.is_cancel_requested(run_id):
            raise RunCancelledError(f"Run {run_id} was cancelled.")

    def _redacted_invocation(self, invocation: HostInvocation) -> HostInvocation:
        return invocation.model_copy(update={"prompt": redact_text(invocation.prompt)})

    def _model_synthesis_available(
        self,
        registry: CapabilityRegistry,
        execution_policy: ExecutionPolicy,
        invocation: HostInvocation,
    ) -> bool:
        for provider in registry.available():
            if provider.kind not in {
                ProviderKind.HOSTED_MODEL,
                ProviderKind.SUBSCRIPTION_CLI,
                ProviderKind.LOCAL_MODEL,
            }:
                continue
            if provider.capabilities.get("final_synthesis", 0.0) < 0.6:
                continue
            allowed, _ = self.policy_compiler.provider_allowed(execution_policy, provider)
            if not allowed:
                continue
            if provider.kind in {ProviderKind.HOSTED_MODEL, ProviderKind.SUBSCRIPTION_CLI} and not invocation.user_options.allow_internet:
                continue
            return True
        return False

    def _replace_artifact(self, artifacts: list[Artifact], replacement: Artifact) -> None:
        for index, artifact in enumerate(artifacts):
            if artifact.name == replacement.name:
                artifacts[index] = replacement
                return
        artifacts.append(replacement)

    def _expected_artifact_names(self, contract: ProductContract) -> list[str]:
        expected = [
            "run_request.json",
            "context_manifest.json",
            "context_cards.json",
            "context_chunks.json",
            "context_provenance.json",
            "context_packs.json",
            "context_index.json",
            "retrieval_report.json",
            "capacity_report.json",
            "product_contract.json",
            "approval_report.json",
            "policy_report.json",
            "task_dag.json",
            "product_plan.json",
            "product_plan_validation.json",
            "plan_review.json",
            "budget_report.json",
            "cost_ledger.json",
            "delta_execution_plan.json",
            "routing_decisions.json",
            "routing_telemetry.json",
            "execution_results.json",
            "schedule_report.json",
            "repo_validation_report.json",
            "provider_health_report.json",
            "validation_findings.json",
            "validator_panel.json",
            "evidence_audit.json",
            "quality_report.json",
            "product_package.json",
            "manuscript.json",
            "final_report.md",
            "trace_report.json",
            "debug_bundle_manifest.json",
        ]
        if "pdf" in contract.primary_artifacts:
            expected.extend(["final_report.pdf", "pdf_validation.json"])
        if "docx" in contract.primary_artifacts:
            expected.extend(["final_report.docx", "docx_validation.json"])
        if "pptx" in contract.primary_artifacts:
            expected.extend(["final_report.pptx", "pptx_validation.json"])
        if "patch" in contract.primary_artifacts or contract.run_type == "repo_implementation":
            expected.extend(["patch_plan.md", "patch_plan_validation.json"])
        return expected
