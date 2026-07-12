from __future__ import annotations

import json
import os
import shutil
from typing import Any

from universal_orchestrator.capacity import CapacityBroker
from universal_orchestrator.models import (
    CapacitySnapshot,
    CapacitySource,
    CapacityStatus,
    ProviderDescriptor,
    ProviderResult,
    ProviderTask,
    TaskStatus,
    utc_now,
)
from universal_orchestrator.providers.base import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorKind,
    dry_run_result,
    render_provider_prompt,
    unavailable_result,
)
from universal_orchestrator.providers.command import (
    CommandRequest,
    CommandTimeout,
    CommandTransport,
    SubprocessCommandTransport,
    sanitized_cli_environment,
)


class SubscriptionCLIAdapter(ProviderAdapter):
    model_env = ""

    def __init__(
        self,
        descriptor: ProviderDescriptor,
        *,
        executable: str,
        command_transport: CommandTransport | None = None,
        capacity_broker: CapacityBroker | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(descriptor, capacity_broker=capacity_broker, **kwargs)
        self.executable = executable
        self.command_transport = command_transport or SubprocessCommandTransport()

    def execute(self, task: ProviderTask) -> ProviderResult:
        model = os.getenv(self.model_env, self.descriptor.model_id)
        if task.dry_run or not task.allow_network:
            return dry_run_result(
                self.id,
                {"provider": self.id, "model": model, "stdin": render_provider_prompt(task)},
                f"{self.id} CLI request prepared in dry-run mode; no process was started.",
                self.estimate_cost(task),
            )
        if not self.executable:
            return unavailable_result(self.id, "The official provider CLI executable is not configured.")
        self._active_model = model
        cost_estimate, authorization = self.authorize_cost(task, model)
        request = CommandRequest(
            argv=self._argv(model),
            stdin=render_provider_prompt(task),
            timeout_seconds=task.timeout_seconds,
            cwd=task.context.get("command_dir") if isinstance(task.context.get("command_dir"), str) else None,
            env=sanitized_cli_environment(),
        )
        try:
            response = self.command_transport.run(request)
            if response.returncode != 0:
                raise self._classify_failure(response.stderr or response.stdout)
            output, usage = self._parse_output(response.stdout)
            self.commit_cost(authorization, usage)
            self._record_unknown_capacity("CLI completed; subscription quota was not exposed in output.")
            return ProviderResult(
                provider_id=self.id,
                status=TaskStatus.COMPLETED,
                output={"summary": output, "model": model, "usage": usage, "billing_mode": "subscription"},
                cost_estimate=cost_estimate,
            )
        except Exception:
            self.release_cost(authorization)
            raise

    def _argv(self, model: str) -> tuple[str, ...]:
        raise NotImplementedError

    def _parse_output(self, stdout: str) -> tuple[str, dict[str, int]]:
        raise NotImplementedError

    def _classify_failure(self, message: str) -> ProviderError:
        lowered = message.casefold()
        if any(term in lowered for term in ("rate limit", "usage limit", "quota", "too many requests", "capacity")):
            self._record_exhausted_capacity("Official CLI reported a subscription limit.")
            return ProviderError(
                ProviderErrorKind.CAPACITY_EXHAUSTED,
                self.id,
                "Official CLI reported a subscription capacity limit.",
            )
        if any(term in lowered for term in ("unauthorized", "authentication", "login", "credential")):
            return ProviderError(ProviderErrorKind.AUTH, self.id, "Official CLI authentication failed.")
        return ProviderError(ProviderErrorKind.FATAL, self.id, "Official CLI execution failed.")

    def _record_unknown_capacity(self, reason: str) -> None:
        self._record_capacity(CapacityStatus.UNKNOWN, CapacitySource.CLI_STATUS, reason)

    def _record_exhausted_capacity(self, reason: str) -> None:
        self._record_capacity(CapacityStatus.EXHAUSTED, CapacitySource.OBSERVED_ERROR, reason)

    def _record_capacity(self, status: CapacityStatus, source: CapacitySource, reason: str) -> None:
        snapshot = CapacitySnapshot(
            connector_id=self.connector_id,
            provider_id=self.id,
            model_id=self._active_model,
            account_scope=self.descriptor.account_scope,
            status=status,
            source=source,
            confidence=0.9 if status == CapacityStatus.EXHAUSTED else 0.35,
            observed_at=utc_now(),
            reason=reason,
        )
        self.latest_capacity = snapshot
        if self.capacity_broker is not None:
            self.capacity_broker.update(snapshot)
        if self.runtime_store is not None:
            self.runtime_store.save_capacity_snapshot(snapshot)


class ClaudeCodeCLIAdapter(SubscriptionCLIAdapter):
    model_env = "CLAUDE_CODE_MODEL"

    def _argv(self, model: str) -> tuple[str, ...]:
        return (
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--max-turns",
            "1",
            "--model",
            model,
        )

    def _parse_output(self, stdout: str) -> tuple[str, dict[str, int]]:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(ProviderErrorKind.MALFORMED_OUTPUT, self.id, "Claude CLI output was not JSON.") from exc
        if not isinstance(payload, dict):
            raise ProviderError(ProviderErrorKind.MALFORMED_OUTPUT, self.id, "Claude CLI output was not an object.")
        summary = payload.get("result", payload.get("text"))
        if not isinstance(summary, str):
            raise ProviderError(ProviderErrorKind.MALFORMED_OUTPUT, self.id, "Claude CLI output had no result text.")
        return summary, _usage(payload.get("usage"))


class CodexCLIAdapter(SubscriptionCLIAdapter):
    model_env = "CODEX_MODEL"

    def _argv(self, model: str) -> tuple[str, ...]:
        return (
            self.executable,
            "exec",
            "--ephemeral",
            "--json",
            "--sandbox",
            "read-only",
            "--model",
            model,
            "-",
        )

    def _parse_output(self, stdout: str) -> tuple[str, dict[str, int]]:
        summary = ""
        usage: dict[str, int] = {}
        try:
            events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            raise ProviderError(ProviderErrorKind.MALFORMED_OUTPUT, self.id, "Codex CLI output was not JSONL.") from exc
        for event in events:
            if not isinstance(event, dict):
                continue
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                summary = item["text"]
            if event.get("type") == "turn.completed":
                usage = _usage(event.get("usage"))
        if not summary:
            raise ProviderError(ProviderErrorKind.MALFORMED_OUTPUT, self.id, "Codex CLI output had no final agent message.")
        return summary, usage


def _usage(value: Any) -> dict[str, int]:
    usage = value if isinstance(value, dict) else {}
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": int(usage.get("total_tokens", input_tokens + output_tokens) or 0),
    }


def discover_executable(env_name: str, default: str) -> str | None:
    configured = os.getenv(env_name)
    return configured if configured else shutil.which(default)
