from __future__ import annotations

import json
import unittest
from unittest.mock import patch

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
from universal_orchestrator.cost_ledger import CostLedger
from universal_orchestrator.providers.cli import ClaudeCodeCLIAdapter, CodexCLIAdapter
from universal_orchestrator.providers.command import (
    CommandResponse,
    FakeCommandTransport,
)


def descriptor(provider_id: str) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=provider_id,
        kind=ProviderKind.SUBSCRIPTION_CLI,
        enabled=True,
        model_id="fixture-model",
        billing_mode="subscription",
        capabilities={"final_synthesis": 1.0},
        cost_tier=CostTier.PREMIUM,
        health=ProviderHealth(status=ProviderStatus.HEALTHY, reliability_score=1.0),
    )


def task() -> ProviderTask:
    return ProviderTask(
        task=TaskNode(id="T", run_id="R", title="Synthesize", task_type=TaskType.FINAL_SYNTHESIS),
        prompt="Return a compact result",
        dry_run=False,
        allow_network=True,
    )


class CLIProviderTests(unittest.TestCase):
    def test_claude_cli_uses_stdin_and_parses_structured_result(self) -> None:
        transport = FakeCommandTransport(
            [
                CommandResponse(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "result": "Claude result",
                            "usage": {"input_tokens": 7, "output_tokens": 3},
                        }
                    ),
                    stderr="",
                )
            ]
        )
        adapter = ClaudeCodeCLIAdapter(
            descriptor("claude-code.cli"),
            command_transport=transport,
            executable="claude",
        )
        with patch.dict("os.environ", {"CLAUDE_CODE_MODEL": "fixture-model"}, clear=True):
            result = adapter.execute(task())

        self.assertEqual(result.output["summary"], "Claude result")
        self.assertEqual(result.output["usage"]["total_tokens"], 10)
        self.assertIn("Return a compact result", transport.requests[0].stdin)
        self.assertIn("--output-format", transport.requests[0].argv)

    def test_codex_cli_parses_jsonl_turn_usage(self) -> None:
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "fixture-thread"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "Codex result"},
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 11, "output_tokens": 5},
                    }
                ),
            ]
        )
        transport = FakeCommandTransport([CommandResponse(returncode=0, stdout=output, stderr="")])
        adapter = CodexCLIAdapter(
            descriptor("codex.cli"),
            command_transport=transport,
            executable="codex",
        )
        with patch.dict("os.environ", {"CODEX_MODEL": "fixture-model"}, clear=True):
            result = adapter.execute(task())

        self.assertEqual(result.output["summary"], "Codex result")
        self.assertEqual(result.output["usage"]["total_tokens"], 16)
        self.assertIn("exec", transport.requests[0].argv)

    def test_cli_quota_failure_is_typed_and_does_not_retry(self) -> None:
        transport = FakeCommandTransport(
            [CommandResponse(returncode=1, stdout="", stderr="usage limit reached; resets soon")]
        )
        adapter = ClaudeCodeCLIAdapter(
            descriptor("claude-code.cli"),
            command_transport=transport,
            executable="claude",
        )
        with patch.dict("os.environ", {"CLAUDE_CODE_MODEL": "fixture-model"}, clear=True):
            with self.assertRaises(Exception) as caught:
                adapter.execute(task())

        self.assertIn("capacity_exhausted", str(caught.exception))
        self.assertEqual(len(transport.requests), 1)

    def test_cli_environment_does_not_forward_api_keys(self) -> None:
        transport = FakeCommandTransport(
            [CommandResponse(returncode=0, stdout=json.dumps({"result": "ok"}), stderr="")]
        )
        adapter = ClaudeCodeCLIAdapter(
            descriptor("claude-code.cli"),
            command_transport=transport,
            executable="claude",
        )
        with patch.dict(
            "os.environ",
            {
                "CLAUDE_CODE_MODEL": "fixture-model",
                "OPENAI_API_KEY": "should-not-forward",
                "ANTHROPIC_API_KEY": "should-not-forward",
            },
            clear=True,
        ):
            adapter.execute(task())

        self.assertNotIn("OPENAI_API_KEY", transport.requests[0].env)
        self.assertNotIn("ANTHROPIC_API_KEY", transport.requests[0].env)

    def test_subscription_usage_is_not_reported_as_free_metered_spend(self) -> None:
        transport = FakeCommandTransport(
            [CommandResponse(returncode=0, stdout=json.dumps({"result": "ok"}), stderr="")]
        )
        ledger = CostLedger("R", ceiling_usd=0.50)
        adapter = ClaudeCodeCLIAdapter(
            descriptor("claude-code.cli"),
            command_transport=transport,
            executable="claude",
            cost_ledger=ledger,
        )
        with patch.dict("os.environ", {"CLAUDE_CODE_MODEL": "fixture-model"}, clear=True):
            adapter.execute(task())

        report = ledger.snapshot()
        self.assertEqual(len(report.calls), 1)
        self.assertEqual(report.calls[0].billing_mode, "subscription")
        self.assertEqual(report.calls[0].cost_status, "allocated_cost_unknown")
        self.assertEqual(report.unknown_cost_calls, 1)


if __name__ == "__main__":
    unittest.main()
