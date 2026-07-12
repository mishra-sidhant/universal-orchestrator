from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from universal_orchestrator.capacity import CapacityBroker
from universal_orchestrator.handoff import HandoffController
from universal_orchestrator.models import CapacitySnapshot, CapacityStatus
from universal_orchestrator.runtime import RuntimeStore


class HandoffControllerTests(unittest.TestCase):
    def test_all_handoff_candidates_exhausted_uses_grounded_extractive_fallback(self) -> None:
        from types import SimpleNamespace

        from universal_orchestrator.model_synthesis import ModelSynthesisResult
        from universal_orchestrator.models import (
            ContextChunk,
            ContextPack,
            RoutingAction,
            RoutingDecision,
            TaskNode,
            TaskType,
        )
        from universal_orchestrator.providers.base import ProviderError, ProviderErrorKind
        from universal_orchestrator.stages import KernelStageContext, StageWorkerRegistry

        class Adapter:
            def __init__(self, provider_id: str) -> None:
                self.id = provider_id
                self.descriptor = SimpleNamespace()

        class AlwaysDownRunner:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def run(self, adapter: Adapter, *args: object, **kwargs: object) -> ModelSynthesisResult:
                del args, kwargs
                self.calls.append(adapter.id)
                raise ProviderError(ProviderErrorKind.TRANSIENT, adapter.id, "fixture outage")

        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            controller = HandoffController(CapacityBroker(), runtime)
            adapters = {
                provider_id: Adapter(provider_id)
                for provider_id in ("provider-a", "provider-b", "provider-c")
            }
            chunk = ContextChunk(
                id="chunk-1",
                input_id="input-1",
                ordinal=0,
                text="Bounded execution is required.",
                token_estimate=5,
                content_hash="chunk-1",
            )
            task = TaskNode(
                id="T-SYNTHESIS",
                run_id="R",
                title="Synthesis",
                task_type=TaskType.FINAL_SYNTHESIS,
            )
            context = KernelStageContext(
                manifest=SimpleNamespace(),
                contract=SimpleNamespace(),
                cards=[],
                chunks=[chunk],
                conflicts=[],
                chunk_refs_by_task={task.id: [chunk.id]},
                build_static_artifacts=lambda: [],
                evaluate_quality=lambda results: SimpleNamespace(),
                context_packs={task.id: ContextPack(task_id=task.id, task="test", chunks=[chunk])},
                provider_adapters=adapters,
                handoff_controller=controller,
            )
            worker = StageWorkerRegistry(context)
            runner = AlwaysDownRunner()
            worker.model_synthesis = runner
            decision = RoutingDecision(
                task_id=task.id,
                action=RoutingAction.ROUTE,
                provider_id="provider-a",
                alternatives=["provider-b", "provider-c"],
                reason="fixture",
            )

            result = worker.execute([task], [decision])[0]

        self.assertEqual(result.status, "completed")
        worker_output = result.output["worker_output"]
        self.assertEqual(worker_output["synthesis_path"], "extractive_provider_fallback")
        self.assertEqual(runner.calls, ["provider-a", "provider-b", "provider-c"])
        self.assertTrue(any("provider" in warning.lower() for warning in result.warnings))

    def test_model_synthesis_handoff_can_cross_two_provider_boundaries(self) -> None:
        from types import SimpleNamespace

        from universal_orchestrator.models import (
            ContextPack,
            RoutingAction,
            RoutingDecision,
            TaskNode,
            TaskType,
        )
        from universal_orchestrator.stages import KernelStageContext, StageWorkerRegistry
        from universal_orchestrator.model_synthesis import (
            ModelClaimOutput,
            ModelSynthesisOutput,
            ModelSynthesisResult,
        )
        from universal_orchestrator.providers.base import ProviderError, ProviderErrorKind

        class Adapter:
            def __init__(self, provider_id: str) -> None:
                self.id = provider_id
                self.descriptor = SimpleNamespace()

        class Runner:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def run(self, adapter: Adapter, *args: object, **kwargs: object) -> ModelSynthesisResult:
                del args, kwargs
                self.calls.append(adapter.id)
                if adapter.id in {"provider-a", "provider-b"}:
                    raise ProviderError(
                        ProviderErrorKind.TRANSIENT,
                        adapter.id,
                        "fixture outage",
                    )
                return ModelSynthesisResult(
                    ModelSynthesisOutput(
                        summary='{"summary":"done","findings":[],"claims":[{"text":"done","evidence_refs":["chunk-1"]}]}',
                        findings=[],
                        claims=[ModelClaimOutput(text="done", evidence_refs=["chunk-1"])],
                    ),
                    False,
                    [],
                )

        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            controller = HandoffController(CapacityBroker(), runtime)
            adapters = {provider_id: Adapter(provider_id) for provider_id in ("provider-a", "provider-b", "provider-c")}
            task = TaskNode(
                id="T-SYNTHESIS",
                run_id="R",
                title="Synthesis",
                task_type=TaskType.FINAL_SYNTHESIS,
            )
            context = KernelStageContext(
                manifest=SimpleNamespace(),
                contract=SimpleNamespace(),
                cards=[],
                chunks=[],
                conflicts=[],
                chunk_refs_by_task={"T-SYNTHESIS": ["chunk-1"]},
                build_static_artifacts=lambda: [],
                evaluate_quality=lambda results: SimpleNamespace(),
                context_packs={"T-SYNTHESIS": ContextPack(task_id="T-SYNTHESIS", task="test")},
                provider_adapters=adapters,
                handoff_controller=controller,
            )
            worker = StageWorkerRegistry(context)
            runner = Runner()
            worker.model_synthesis = runner
            decision = RoutingDecision(
                task_id=task.id,
                action=RoutingAction.ROUTE,
                provider_id="provider-a",
                alternatives=["provider-b", "provider-c"],
                reason="fixture",
            )

            result = worker.execute([task], [decision])[0]

            self.assertEqual(result.status, "completed")
            self.assertEqual(result.provider_id, "provider-c")
            self.assertEqual(runner.calls, ["provider-a", "provider-b", "provider-c"])
            self.assertEqual(len(runtime.handoffs("R", task.id)), 2)

    def test_handoff_skips_attempted_and_exhausted_connectors(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            capacity = CapacityBroker()
            capacity.update(
                CapacitySnapshot(
                    connector_id="provider-a",
                    provider_id="a",
                    model_id="a-model",
                    account_scope="a",
                    status=CapacityStatus.EXHAUSTED,
                    reason="limit",
                )
            )
            controller = HandoffController(capacity, runtime)

            handoff = controller.choose(
                "R",
                "T",
                attempt=1,
                candidates=["provider-a", "provider-b", "provider-c"],
                attempted_connectors={"provider-b"},
                reason="provider stopped on quota",
                current_connector_id="provider-a",
                checkpoint_sequence=3,
            )

            self.assertIsNotNone(handoff)
            assert handoff is not None
            self.assertEqual(handoff.to_connector_id, "provider-c")
            self.assertEqual(runtime.handoffs("R", "T")[0].reason, "provider stopped on quota")

    def test_handoff_limit_is_honest(self) -> None:
        capacity = CapacityBroker()
        controller = HandoffController(capacity, max_attempts=2, max_handoffs=1)
        first = controller.choose("R", "T", 2, ["a"], set(), "stop")
        self.assertIsNone(first)


if __name__ == "__main__":
    unittest.main()
