from __future__ import annotations

from universal_orchestrator.models import ProviderDescriptor, ProviderResult, ProviderTask, TaskStatus
from universal_orchestrator.providers.base import ProviderAdapter


class DeterministicToolsAdapter(ProviderAdapter):
    def execute(self, task: ProviderTask) -> ProviderResult:
        node = task.task
        return ProviderResult(
            provider_id=self.id,
            status=TaskStatus.SKIPPED,
            output={
                "title": node.title,
                "task_type": node.task_type,
                "summary": "No registered deterministic stage worker can execute this task.",
            },
            warnings=["No registered deterministic stage worker can execute this task."],
        )


def build_adapter(descriptor: ProviderDescriptor) -> DeterministicToolsAdapter:
    return DeterministicToolsAdapter(descriptor)
