from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from universal_orchestrator.budget import BudgetController
from universal_orchestrator.cost_ledger import BudgetStopError, CostLedger
from universal_orchestrator.models import (
    BudgetProfile,
    BudgetReport,
    CostTier,
    ProviderTask,
    HostInvocation,
    TaskNode,
    TaskType,
    UserOptions,
)
from universal_orchestrator.pricing import RateTable
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.providers.transport import FakeTransport, HTTPResponse
from universal_orchestrator.routing import CapabilityRegistry


def task() -> ProviderTask:
    return ProviderTask(
        task=TaskNode(
            id="T-COST",
            run_id="R-COST",
            title="Costed synthesis",
            task_type=TaskType.FINAL_SYNTHESIS,
        ),
        prompt="Return a concise answer",
        dry_run=False,
        allow_network=True,
    )


def success_response(input_tokens: int = 11, output_tokens: int = 7) -> HTTPResponse:
    return HTTPResponse(
        200,
        {},
        json.dumps(
            {
                "id": "resp_cost",
                "model": "fixture-model",
                "output_text": "costed result",
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            }
        ).encode(),
    )


class TrancheF3CostTruthTests(unittest.TestCase):
    def test_default_ceiling_is_pinned_and_rates_are_versioned_config(self) -> None:
        rates = RateTable.load()

        self.assertEqual(UserOptions().cost_ceiling_usd, 0.50)
        self.assertEqual(rates.version, "2026-07-11")
        quote = rates.quote("openai.configured", "fixture-model", 11, 7)
        self.assertEqual(quote.rate_key, "default")
        self.assertAlmostEqual(quote.cost_usd, 0.00016)
        self.assertTrue(Path(rates.source_path).name == "provider_rates.json")

    def test_pre_call_gate_stops_before_transport_and_records_reason(self) -> None:
        transport = FakeTransport([success_response()])
        ledger = CostLedger("R-COST", ceiling_usd=0.000001, rate_table=RateTable.load())
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            registry = CapabilityRegistry.from_environment(
                transports={"openai.configured": transport},
                cost_ledger=ledger,
            )
            adapter = registry.adapter_registry().require("openai.configured")
            with self.assertRaises(BudgetStopError):
                adapter.execute(task())

        snapshot = ledger.snapshot()
        self.assertEqual(transport.requests, [])
        self.assertIsNotNone(snapshot.budget_stop)
        self.assertEqual(snapshot.budget_stop.task_id, "T-COST")
        self.assertGreater(snapshot.budget_stop.estimated_usd, snapshot.budget_stop.remaining_usd)
        self.assertEqual(snapshot.total_actual_usd, 0)

    def test_actual_provider_usage_is_priced_and_recorded_per_call(self) -> None:
        transport = FakeTransport([success_response()])
        ledger = CostLedger("R-COST", ceiling_usd=0.50, rate_table=RateTable.load())
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            adapter = CapabilityRegistry.from_environment(
                transports={"openai.configured": transport},
                cost_ledger=ledger,
            ).adapter_registry().require("openai.configured")
            result = adapter.execute(task())

        snapshot = ledger.snapshot()
        self.assertIsNotNone(result.cost_estimate)
        self.assertEqual(len(snapshot.calls), 1)
        row = snapshot.calls[0]
        self.assertEqual((row.input_tokens, row.output_tokens), (11, 7))
        self.assertAlmostEqual(row.actual_usd, 0.00016)
        self.assertGreater(row.estimated_usd, row.actual_usd)
        self.assertEqual(row.model, "fixture-model")
        self.assertEqual(row.rate_table_version, "2026-07-11")
        self.assertEqual(row.rate_key, "default")

    def test_estimate_actual_divergence_is_a_warning_not_a_gate(self) -> None:
        transport = FakeTransport([success_response()])
        ledger = CostLedger("R-COST", ceiling_usd=0.50, rate_table=RateTable.load())
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "fixture-key", "OPENAI_MODEL": "fixture-model"},
            clear=True,
        ):
            adapter = CapabilityRegistry.from_environment(
                transports={"openai.configured": transport},
                cost_ledger=ledger,
            ).adapter_registry().require("openai.configured")
            adapter.execute(task())
        report = BudgetReport(
            run_id="R-COST",
            requested_profile=BudgetProfile.BALANCED,
            effective_max_cost_tier=CostTier.PREMIUM,
        )

        reconciled = BudgetController().reconcile_actual_usage(report, ledger.snapshot())

        self.assertTrue(reconciled.estimate_actual_reconciliation["diverged"])
        self.assertTrue(any("recalibration" in warning for warning in reconciled.warnings))
        self.assertTrue(reconciled.enforced)

    def test_every_pipeline_run_persists_cost_ledger_and_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = Orchestrator(Path(tmp) / "runs").run(
                HostInvocation(prompt="Build a local report")
            )
            run_dir = Path(result.artifact_dir)
            ledger = json.loads((run_dir / "cost_ledger.json").read_text())
            budget = json.loads((run_dir / "budget_report.json").read_text())

        self.assertEqual(ledger["cost_ceiling_usd"], 0.50)
        self.assertEqual(ledger["calls"], [])
        self.assertEqual(ledger["total_actual_usd"], 0)
        self.assertFalse(budget["estimate_actual_reconciliation"]["diverged"])


if __name__ == "__main__":
    unittest.main()
