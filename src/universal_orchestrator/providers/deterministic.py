from __future__ import annotations

from universal_orchestrator.models import ProviderDescriptor, ProviderResult, ProviderTask, TaskStatus
from universal_orchestrator.providers.base import ProviderAdapter


class DeterministicToolsAdapter(ProviderAdapter):
    def execute(self, task: ProviderTask) -> ProviderResult:
        node = task.task
        capability_names = sorted(node.required_capabilities)
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.COMPLETED,
            output={
                "title": node.title,
                "task_type": node.task_type,
                "summary": f"{node.title} completed by local deterministic tools.",
                "capabilities_considered": capability_names,
                "context_keys": sorted(task.context.keys()),
                "dry_run": task.dry_run,
            },
        )


def build_adapter(descriptor: ProviderDescriptor) -> DeterministicToolsAdapter:
    return DeterministicToolsAdapter(descriptor)

