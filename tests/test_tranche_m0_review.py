from __future__ import annotations

import unittest
from datetime import timedelta

from universal_orchestrator.capacity import CapacityBroker, CapacityReservationError
from universal_orchestrator.models import (
    CapacityDimension,
    CapacitySnapshot,
    CapacityStatus,
    CapacityWindow,
    utc_now,
)


class ReviewRegressionTests(unittest.TestCase):
    def test_request_and_total_token_windows_are_reserved_together(self) -> None:
        now = utc_now()
        broker = CapacityBroker()
        broker.update(
            CapacitySnapshot(
                connector_id="provider/default",
                provider_id="provider",
                model_id="model",
                account_scope="account",
                status=CapacityStatus.AVAILABLE,
                observed_at=now,
                expires_at=now + timedelta(minutes=5),
                windows=[
                    CapacityWindow(dimension=CapacityDimension.REQUESTS, remaining=1),
                    CapacityWindow(dimension=CapacityDimension.TOTAL_TOKENS, remaining=100),
                ],
            )
        )

        broker.reserve(
            "run",
            "task-1",
            "provider/default",
            {
                CapacityDimension.REQUESTS: 1,
                CapacityDimension.TOTAL_TOKENS: 80,
            },
        )
        with self.assertRaises(CapacityReservationError):
            broker.reserve(
                "run",
                "task-2",
                "provider/default",
                {
                    CapacityDimension.REQUESTS: 1,
                    CapacityDimension.TOTAL_TOKENS: 20,
                },
            )

    def test_expired_snapshot_is_effectively_unknown_in_routing_state(self) -> None:
        now = utc_now()
        snapshot = CapacitySnapshot(
            connector_id="provider/default",
            provider_id="provider",
            model_id="model",
            account_scope="account",
            status=CapacityStatus.EXHAUSTED,
            observed_at=now - timedelta(minutes=10),
            expires_at=now - timedelta(seconds=1),
            windows=[CapacityWindow(dimension=CapacityDimension.REQUESTS, remaining=0)],
        )
        broker = CapacityBroker()
        broker.update(snapshot)

        effective = broker.effective_status(snapshot.connector_id)
        self.assertEqual(effective, CapacityStatus.UNKNOWN)
        self.assertTrue(broker.is_eligible(snapshot.connector_id))

    def test_subscription_capacity_is_durable_and_released_on_failed_call(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            from universal_orchestrator.runtime import RuntimeStore

            runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
            broker = CapacityBroker(runtime_store=runtime, subscription_call_limit=1)
            first = broker.reserve(
                "run",
                "task-1",
                "claude-code/default",
                {CapacityDimension.SUBSCRIPTION_CALLS: 1},
            )
            with self.assertRaises(CapacityReservationError):
                broker.reserve(
                    "run",
                    "task-2",
                    "claude-code/default",
                    {CapacityDimension.SUBSCRIPTION_CALLS: 1},
                )
            broker.release(first)
            second = broker.reserve(
                "run",
                "task-2",
                "claude-code/default",
                {CapacityDimension.SUBSCRIPTION_CALLS: 1},
            )
            broker.commit(second)
            restored = CapacityBroker(runtime_store=runtime, subscription_call_limit=1)
            with self.assertRaises(CapacityReservationError):
                restored.reserve(
                    "run",
                    "task-3",
                    "claude-code/default",
                    {CapacityDimension.SUBSCRIPTION_CALLS: 1},
                )

    def test_provider_authorization_reserves_request_and_total_token_dimensions(self) -> None:
        from universal_orchestrator.models import (
            CostTier,
            ProviderDescriptor,
            ProviderHealth,
            ProviderKind,
            ProviderStatus,
            ProviderTask,
            TaskNode,
            TaskType,
        )
        from universal_orchestrator.providers.openai import OpenAIResponsesAdapter
        from universal_orchestrator.providers.base import ProviderError, ProviderErrorKind

        descriptor = ProviderDescriptor(
            id="openai.configured",
            connector_id="openai.configured/default",
            kind=ProviderKind.HOSTED_MODEL,
            model_id="fixture-model",
            enabled=True,
            capabilities={"final_synthesis": 1.0},
            cost_tier=CostTier.PREMIUM,
            health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
        )
        broker = CapacityBroker()
        now = utc_now()
        broker.update(
            CapacitySnapshot(
                connector_id=descriptor.connector_id,
                provider_id=descriptor.id,
                model_id=descriptor.model_id,
                account_scope="account",
                status=CapacityStatus.AVAILABLE,
                observed_at=now,
                expires_at=now + timedelta(minutes=5),
                windows=[
                    CapacityWindow(dimension=CapacityDimension.REQUESTS, remaining=1),
                    CapacityWindow(dimension=CapacityDimension.TOTAL_TOKENS, remaining=100_000),
                ],
            )
        )
        adapter = OpenAIResponsesAdapter(descriptor, capacity_broker=broker)
        provider_task = ProviderTask(
            task=TaskNode(id="T", run_id="R", title="Synthesize", task_type=TaskType.FINAL_SYNTHESIS),
            prompt="Return a compact result",
            dry_run=False,
            allow_network=True,
        )
        estimate = adapter.estimate_cost(provider_task)
        adapter.authorize_capacity(provider_task, descriptor.model_id, estimate)
        with self.assertRaises(ProviderError) as raised:
            adapter.authorize_capacity(provider_task, descriptor.model_id, estimate)
        self.assertEqual(raised.exception.kind, ProviderErrorKind.CAPACITY_EXHAUSTED)


if __name__ == "__main__":
    unittest.main()
