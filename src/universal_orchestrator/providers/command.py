from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class CommandRequest:
    argv: tuple[str, ...]
    stdin: str
    timeout_seconds: float
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResponse:
    returncode: int
    stdout: str
    stderr: str


class CommandTimeout(TimeoutError):
    """The CLI process exceeded its hard execution deadline."""


class CommandTransport(Protocol):
    def run(self, request: CommandRequest) -> CommandResponse:
        """Run one command without provider retry policy."""


class SubprocessCommandTransport:
    def run(self, request: CommandRequest) -> CommandResponse:
        process = subprocess.Popen(
            list(request.argv),
            cwd=request.cwd,
            env=request.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(
                request.stdin,
                timeout=max(0.1, request.timeout_seconds),
            )
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = process.communicate()
            raise CommandTimeout(
                f"CLI command timed out after {request.timeout_seconds:g} seconds."
            ) from exc
        return CommandResponse(process.returncode, stdout, stderr)


class FakeCommandTransport:
    """Scripted command transport for offline CLI adapter tests."""

    def __init__(self, outcomes: list[CommandResponse | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[CommandRequest] = []

    def run(self, request: CommandRequest) -> CommandResponse:
        self.requests.append(request)
        if not self.outcomes:
            raise AssertionError("FakeCommandTransport received an unexpected request.")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def sanitized_cli_environment() -> dict[str, str]:
    """Preserve CLI-owned auth discovery while excluding API-key variables."""

    allowed = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}
