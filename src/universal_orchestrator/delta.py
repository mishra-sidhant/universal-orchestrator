from __future__ import annotations

from pathlib import Path
from typing import Any

from universal_orchestrator.models import (
    ContextManifest,
    DeltaExecutionPlan,
    DeltaTaskDecision,
    TaskDAG,
)
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.scheduler import DAGScheduler
from universal_orchestrator.utils import read_json


class DeltaPlanner:
    def plan(
        self,
        manifest: ContextManifest,
        dag: TaskDAG,
        runtime: RuntimeStore,
        scheduler: DAGScheduler,
        cache_context: dict[str, Any],
    ) -> DeltaExecutionPlan:
        previous = runtime.latest_successful_summary(exclude_run_id=manifest.run_id)
        current_hashes = self._manifest_hashes(manifest.model_dump(mode="json"))
        previous_hashes: set[str] = set()
        warnings: list[str] = []
        previous_run_id: str | None = None

        if previous:
            previous_run_id = previous["run_id"]
            previous_manifest_path = Path(previous["artifact_dir"]) / "context_manifest.json"
            if previous_manifest_path.exists():
                previous_hashes = self._manifest_hashes(read_json(previous_manifest_path))
            else:
                warnings.append(f"Previous manifest not found: {previous_manifest_path}")
        else:
            warnings.append("No previous successful run found for delta comparison.")

        changed_hashes = current_hashes.difference(previous_hashes)
        input_hash_changed = previous is None or bool(changed_hashes) or current_hashes != previous_hashes
        changed_input_ids = [
            item.id for item in manifest.inputs if item.content_hash in changed_hashes or previous is None
        ]

        task_decisions: list[DeltaTaskDecision] = []
        reusable: list[str] = []
        executable: list[str] = []
        for node in dag.topological_order():
            cache_key = scheduler.cache_key_for_task(node, cache_context)
            cache_available = bool(
                scheduler.cache and (scheduler.cache.root / f"{cache_key}.json").exists()
            )
            if previous and not input_hash_changed and cache_available:
                action = "reuse"
                reason = "Inputs unchanged and scheduler cache entry is available."
                reusable.append(node.id)
            elif previous and not input_hash_changed:
                action = "execute"
                reason = "Inputs unchanged but scheduler cache entry is missing."
                executable.append(node.id)
            elif previous:
                action = "execute"
                reason = "Input fingerprint changed since the previous successful run."
                executable.append(node.id)
            else:
                action = "execute"
                reason = "No previous successful run exists."
                executable.append(node.id)
            task_decisions.append(
                DeltaTaskDecision(
                    task_id=node.id,
                    action=action,
                    reason=reason,
                    cache_key=cache_key,
                    previous_run_id=previous_run_id,
                )
            )

        return DeltaExecutionPlan(
            run_id=manifest.run_id,
            previous_run_id=previous_run_id,
            input_hash_changed=input_hash_changed,
            changed_input_ids=changed_input_ids,
            reusable_task_ids=reusable,
            executable_task_ids=executable,
            task_decisions=task_decisions,
            warnings=warnings,
        )

    def _manifest_hashes(self, manifest_payload: dict[str, Any]) -> set[str]:
        hashes: set[str] = set()
        for item in manifest_payload.get("inputs", []):
            content_hash = item.get("content_hash")
            if content_hash:
                hashes.add(content_hash)
        return hashes
