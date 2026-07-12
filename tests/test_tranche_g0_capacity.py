from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import patch
import json

from universal_orchestrator.capacity import (
    CapacityBroker,
    CapacityReservationError,
    snapshot_from_headers,
)
from universal_orchestrator.models import (
    CapacityDimension,
    CapacitySnapshot,
    CapacitySource,
    CapacityStatus,
    CapacityWindow,
    utc_now,
)
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.routing import AdaptiveRouter, CapabilityRegistry
from universal_orchestrator.models import (
    CostTier,
    ProviderDescriptor,
    ProviderHealth,
    ProviderKind,
    ProviderTask,
    ProviderStatus,
    TaskNode,
    TaskType,
)
from universal_orchestrator.providers.openai import OpenAIResponsesAdapter
from universal_orchestrator.providers.transport import FakeTransport, HTTPResponse


class CapacityBrokerTests(unittest.TestCase):
    def snapshot(
        self,
        status: CapacityStatus = CapacityStatus.AVAILABLE,
        remaining: float | None = 100,
    ) -> CapacitySnapshot:
        now = utc_now()
        return CapacitySnapshot(
            connector_id="openai.configured/default",
            provider_id="openai.configured",
            model_id="fixture-model",
            account_scope="fixture-account",
            status=status,
            source=CapacitySource.CONFIGURED,
            observed_at=now,
            expires_at=now + timedelta(minutes=5),
            windows=[
                CapacityWindow(
                    dimension=CapacityDimension.INPUT_TOKENS,
                    limit=100,
                    remaining=remaining,
                )
            ],
        )

    def test_exhausted_connector_cannot_reserve(self) -> None:
        broker = CapacityBroker()
        broker.update(self.snapshot(CapacityStatus.EXHAUSTED, 0))

        with self.assertRaises(CapacityReservationError):
            broker.reserve("R", "T", "openai.configured/default", {CapacityDimension.INPUT_TOKENS: 1})

    def test_exact_remaining_capacity_cannot_be_overbooked(self) -> None:
        broker = CapacityBroker()
        broker.update(self.snapshot(remaining=10))
        first = broker.reserve(
            "R", "T1", "openai.configured/default", {CapacityDimension.INPUT_TOKENS: 7}
        )

        with self.assertRaises(CapacityReservationError):
            broker.reserve("R", "T2", "openai.configured/default", {CapacityDimension.INPUT_TOKENS: 4})

        broker.release(first)
        second = broker.reserve(
            "R", "T2", "openai.configured/default", {CapacityDimension.INPUT_TOKENS: 10}
        )
        self.assertEqual(second.connector_id, "openai.configured/default")

    def test_unknown_capacity_is_eligible_but_penalized(self) -> None:
        broker = CapacityBroker()
        snapshot = self.snapshot(CapacityStatus.UNKNOWN, None)
        broker.update(snapshot)

        self.assertTrue(broker.is_eligible(snapshot.connector_id))
        self.assertLess(broker.score(snapshot.connector_id), 1.0)

    def test_capacity_snapshot_round_trips_through_runtime(self) -> None:
        with self.subTest("sqlite persistence"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                runtime = RuntimeStore(f"{directory}/runtime.sqlite3")
                original = self.snapshot()
                runtime.save_capacity_snapshot(original)
                restored = runtime.latest_capacity_snapshot(original.connector_id)

                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertEqual(restored.model_id, original.model_id)
                self.assertEqual(restored.windows[0].remaining, 100)

    def test_headers_produce_exact_token_and_request_windows(self) -> None:
        snapshot = snapshot_from_headers(
            connector_id="openai.configured/default",
            provider_id="openai.configured",
            model_id="fixture-model",
            account_scope="fixture-account",
            headers={
                "x-ratelimit-limit-requests": "10",
                "x-ratelimit-remaining-requests": "8",
                "x-ratelimit-limit-tokens": "1000",
                "x-ratelimit-remaining-tokens": "750",
                "x-ratelimit-reset-requests": "2s",
            },
        )

        self.assertEqual(snapshot.status, CapacityStatus.AVAILABLE)
        self.assertEqual(
            {window.dimension for window in snapshot.windows},
            {CapacityDimension.REQUESTS, CapacityDimension.TOTAL_TOKENS},
        )
        token_window = next(
            window for window in snapshot.windows if window.dimension == CapacityDimension.TOTAL_TOKENS
        )
        self.assertEqual(token_window.remaining, 750)

    def test_http_adapter_records_response_capacity(self) -> None:
        descriptor = ProviderDescriptor(
            id="openai.configured",
            kind=ProviderKind.HOSTED_MODEL,
            model_id="fixture-model",
            enabled=True,
            capabilities={"final_synthesis": 1.0},
            cost_tier=CostTier.PREMIUM,
            health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
        )
        response = HTTPResponse(
            status_code=200,
            headers={
                "x-ratelimit-limit-tokens": "100",
                "x-ratelimit-remaining-tokens": "90",
            },
            body=json.dumps(
                {
                    "id": "resp_fixture",
                    "model": "fixture-model",
                    "output_text": "ok",
                    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                }
            ).encode(),
        )
        adapter = OpenAIResponsesAdapter(descriptor, transport=FakeTransport([response]))
        task = ProviderTask(
            task=TaskNode(id="T", run_id="R", title="Synthesize", task_type=TaskType.FINAL_SYNTHESIS),
            prompt="Return ok",
            dry_run=False,
            allow_network=True,
        )
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            adapter.execute(task)

        assert adapter.latest_capacity is not None
        self.assertEqual(adapter.latest_capacity.windows[0].remaining, 90)

    def test_router_excludes_known_exhausted_connector(self) -> None:
        broker = CapacityBroker()
        broker.update(self.snapshot(CapacityStatus.EXHAUSTED, 0))
        provider = ProviderDescriptor(
            id="openai.configured",
            kind=ProviderKind.HOSTED_MODEL,
            connector_id="openai.configured/default",
            enabled=True,
            capabilities={"final_synthesis": 1.0},
            cost_tier=CostTier.PREMIUM,
            health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
        )
        registry = CapabilityRegistry([provider], capacity_broker=broker)
        router = AdaptiveRouter(registry)
        decision = router.route(
            TaskNode(
                id="T",
                run_id="R",
                title="Synthesize",
                task_type=TaskType.FINAL_SYNTHESIS,
                required_capabilities={"final_synthesis": 0.8},
            )
        )

        self.assertEqual(decision.action, "reshape")
        metric = router.provider_metrics(TaskNode(
            id="T",
            run_id="R",
            title="Synthesize",
            task_type=TaskType.FINAL_SYNTHESIS,
            required_capabilities={"final_synthesis": 0.8},
        ))[0]
        self.assertFalse(metric.eligible)
        self.assertIn("capacity", " ".join(metric.rejection_reasons))

    def test_adapter_capacity_gate_stops_before_second_transport_call(self) -> None:
        broker = CapacityBroker()
        descriptor = ProviderDescriptor(
            id="openai.configured",
            kind=ProviderKind.HOSTED_MODEL,
            connector_id="openai.configured/default",
            enabled=True,
            capabilities={"final_synthesis": 1.0},
            cost_tier=CostTier.PREMIUM,
            health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
        )
        first_transport = FakeTransport(
            [
                HTTPResponse(
                    200,
                    {
                        "x-ratelimit-limit-tokens": "100",
                        "x-ratelimit-remaining-tokens": "0",
                    },
                    json.dumps({"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}).encode(),
                )
            ]
        )
        adapter = OpenAIResponsesAdapter(
            descriptor,
            transport=first_transport,
            capacity_broker=broker,
        )
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            adapter.execute(
                ProviderTask(
                    task=TaskNode(id="T1", run_id="R", title="One", task_type=TaskType.FINAL_SYNTHESIS),
                    prompt="one",
                    dry_run=False,
                    allow_network=True,
                )
            )
            second_transport = FakeTransport([])
            second = OpenAIResponsesAdapter(
                descriptor,
                transport=second_transport,
                capacity_broker=broker,
            )
            with self.assertRaises(Exception) as caught:
                second.execute(
                    ProviderTask(
                        task=TaskNode(id="T2", run_id="R", title="Two", task_type=TaskType.FINAL_SYNTHESIS),
                        prompt="two",
                        dry_run=False,
                        allow_network=True,
                    )
                )

        self.assertIn("capacity_exhausted", str(caught.exception))
        self.assertEqual(second_transport.requests, [])


if __name__ == "__main__":
    unittest.main()
