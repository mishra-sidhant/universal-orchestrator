import unittest

from universal_orchestrator.models import ProviderTask, TaskNode, TaskType
from universal_orchestrator.routing import CapabilityRegistry


class ProviderAdapterTests(unittest.TestCase):
    def test_registry_builds_all_known_adapters(self) -> None:
        registry = CapabilityRegistry.from_environment().adapter_registry()

        self.assertIsNotNone(registry.get("deterministic.tools"))
        self.assertIsNotNone(registry.get("openai.configured"))
        self.assertIsNotNone(registry.get("anthropic.configured"))
        self.assertIsNotNone(registry.get("ollama.local"))

    def test_openai_adapter_dry_run_never_requires_key(self) -> None:
        registry = CapabilityRegistry.from_environment().adapter_registry()
        adapter = registry.require("openai.configured")
        task = ProviderTask(
            task=TaskNode(id="T", run_id="R", title="Plan", task_type=TaskType.PLANNING),
            prompt="Plan safely",
            dry_run=True,
            allow_network=False,
        )

        result = adapter.execute(task)

        self.assertEqual(result.status, "completed")
        self.assertTrue(result.output["dry_run"])


if __name__ == "__main__":
    unittest.main()

