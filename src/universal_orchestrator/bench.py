from __future__ import annotations

import shutil
from pathlib import Path
from time import monotonic
from typing import Any

from universal_orchestrator.context import ContextIntelligence
from universal_orchestrator.cost_ledger import CostLedger
from universal_orchestrator.execution_policy import PolicyCompiler
from universal_orchestrator.ingestion import InputIngestor
from universal_orchestrator.models import (
    CostTier,
    ExecutionPolicy,
    HostInvocation,
    ProviderDescriptor,
    ProviderKind,
    ProviderStatus,
    ProviderTask,
    TaskNode,
    TaskType,
    new_id,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.utils import ensure_dir, read_json, write_json


class BenchmarkRunner:
    def __init__(
        self,
        artifact_root: Path | str = ".uo/bench",
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.artifact_root = ensure_dir(Path(artifact_root))
        self.capability_registry = capability_registry
        self.context = ContextIntelligence()
        self.policy = PolicyCompiler()

    def run(self, invocation: HostInvocation) -> dict[str, Any]:
        bench_id = new_id("bench")
        bundle_dir = ensure_dir(self.artifact_root / bench_id)
        manifest = InputIngestor().ingest(invocation, f"{bench_id}_native")
        policy = self.policy.compile(invocation, manifest)
        registry = self.capability_registry or CapabilityRegistry.from_environment()
        registry.refresh_health(policy, allow_network=invocation.user_options.allow_internet)
        provider = self._strongest_provider(registry, policy)

        native_ledger = CostLedger(
            f"{bench_id}_native",
            invocation.user_options.cost_ceiling_usd,
        )
        registry.cost_ledger = native_ledger
        adapter = registry.adapter_registry().require(provider.id)
        cards = self.context.rank_cards(invocation.prompt, self.context.build_cards(manifest))
        chunks = self.context.chunk_manifest(manifest)
        task = TaskNode(
            id="T-NATIVE",
            run_id=f"{bench_id}_native",
            title="Direct native benchmark call",
            task_type=TaskType.FINAL_SYNTHESIS,
            required_capabilities={"final_synthesis": 0.6},
            max_cost_tier=CostTier.PREMIUM,
        )
        pack = self.context.compile_pack(
            task.id,
            invocation.prompt,
            cards,
            chunks=chunks,
        )
        native_started = monotonic()
        native_result = adapter.execute(
            ProviderTask(
                task=task,
                prompt=invocation.prompt,
                context={"context_pack": pack.model_dump(mode="json")},
                dry_run=False,
                allow_network=True,
                timeout_seconds=task.timeout_seconds,
            )
        )
        native_latency_ms = round((monotonic() - native_started) * 1_000)
        native_snapshot = native_ledger.snapshot()

        orchestrated_started = monotonic()
        orchestrated = Orchestrator(
            bundle_dir / "orchestrated_runs",
            capability_registry=registry,
        ).run(invocation)
        orchestrated_latency_ms = round((monotonic() - orchestrated_started) * 1_000)
        orchestrated_dir = Path(orchestrated.artifact_dir)
        orchestrated_ledger = read_json(orchestrated_dir / "cost_ledger.json")

        native_output = str(native_result.output.get("summary", ""))
        (bundle_dir / "native_output.md").write_text(f"# Native Output\n\n{native_output}\n")
        shutil.copy2(orchestrated_dir / "final_report.md", bundle_dir / "orchestrated_output.md")
        shutil.copy2(orchestrated_dir / "quality_report.json", bundle_dir / "quality_report.json")
        shutil.copy2(orchestrated_dir / "evidence_audit.json", bundle_dir / "evidence_audit.json")
        write_json(bundle_dir / "native_cost_ledger.json", native_snapshot.model_dump(mode="json"))
        shutil.copy2(orchestrated_dir / "cost_ledger.json", bundle_dir / "orchestrated_cost_ledger.json")

        comparison = {
            "schema_version": "1.0",
            "bench_id": bench_id,
            "prompt": invocation.prompt,
            "automated_superiority_claim": None,
            "interpretation": (
                "This bundle is a measurement instrument. Human judgment must compare the "
                "outputs; the kernel makes no automated superiority claim."
            ),
            "native": {
                "provider_id": provider.id,
                "model": native_result.output.get("model"),
                "latency_ms": native_latency_ms,
                "actual_cost_usd": native_snapshot.total_actual_usd,
                "cost_ceiling_usd": native_snapshot.cost_ceiling_usd,
                "output_path": "native_output.md",
                "cost_ledger_path": "native_cost_ledger.json",
            },
            "orchestrated": {
                "run_id": orchestrated.run_id,
                "state": orchestrated.state,
                "latency_ms": orchestrated_latency_ms,
                "actual_cost_usd": orchestrated_ledger.get("total_actual_usd", 0.0),
                "cost_ceiling_usd": orchestrated_ledger.get("cost_ceiling_usd", 0.50),
                "output_path": "orchestrated_output.md",
                "cost_ledger_path": "orchestrated_cost_ledger.json",
                "quality_report_path": "quality_report.json",
                "evidence_audit_path": "evidence_audit.json",
            },
        }
        write_json(bundle_dir / "comparison.json", comparison)
        return {
            "bench_id": bench_id,
            "bundle_dir": str(bundle_dir),
            "comparison_path": str(bundle_dir / "comparison.json"),
        }

    def _strongest_provider(
        self,
        registry: CapabilityRegistry,
        policy: ExecutionPolicy,
    ) -> ProviderDescriptor:
        candidates = []
        for provider in registry.providers:
            if not provider.enabled or provider.health.status == ProviderStatus.UNAVAILABLE:
                continue
            if provider.kind not in {ProviderKind.HOSTED_MODEL, ProviderKind.LOCAL_MODEL}:
                continue
            allowed, _ = self.policy.provider_allowed(policy, provider)
            if not allowed or provider.capabilities.get("final_synthesis", 0.0) < 0.6:
                continue
            candidates.append(provider)
        if not candidates:
            raise RuntimeError(
                "No healthy configured model can run the native benchmark. Configure a provider "
                "and grant the required execution permissions."
            )
        return max(
            candidates,
            key=lambda item: (
                item.capabilities.get("final_synthesis", 0.0),
                item.health.reliability_score,
                item.context_limit_tokens,
            ),
        )
