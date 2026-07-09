from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from universal_orchestrator.models import (
    ContextManifest,
    HostInvocation,
    InputRecord,
    InputType,
    RepoValidationReport,
    ValidationCommandResult,
)


class RepoValidationRunner:
    def run(self, invocation: HostInvocation, manifest: ContextManifest) -> RepoValidationReport:
        command_specs = self._commands_from_manifest(manifest)
        if not command_specs:
            return RepoValidationReport(
                run_id=manifest.run_id,
                executed=False,
                passed=True,
                warnings=["No repository validation commands were detected."],
            )

        results: list[ValidationCommandResult] = []
        for record, command in command_specs:
            if not invocation.user_options.allow_shell:
                results.append(
                    ValidationCommandResult(
                        command=command,
                        cwd=record.path or "",
                        status="skipped",
                        reason="allow_shell is false; command was planned but not executed.",
                    )
                )
                continue
            parsed = self._parse_allowed_command(command)
            if parsed is None:
                results.append(
                    ValidationCommandResult(
                        command=command,
                        cwd=record.path or "",
                        status="blocked",
                        reason="Command is not in the deterministic validation allowlist.",
                    )
                )
                continue
            env_updates, argv = parsed
            results.append(self._run_command(command, record.path or ".", env_updates, argv))

        return RepoValidationReport(
            run_id=manifest.run_id,
            executed=any(result.status in {"passed", "failed"} for result in results),
            passed=not any(result.status == "failed" for result in results),
            command_results=results,
            warnings=[
                result.reason
                for result in results
                if result.status in {"skipped", "blocked"} and result.reason
            ],
        )

    def _commands_from_manifest(self, manifest: ContextManifest) -> list[tuple[InputRecord, str]]:
        commands: list[tuple[InputRecord, str]] = []
        for record in manifest.inputs:
            if record.type != InputType.REPO:
                continue
            repo_map = record.metadata.get("repo_map", {})
            for command in repo_map.get("test_commands", []):
                commands.append((record, str(command)))
        return commands

    def _parse_allowed_command(self, command: str) -> tuple[dict[str, str], list[str]] | None:
        try:
            tokens = shlex.split(command)
        except ValueError:
            return None
        env_updates: dict[str, str] = {}
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            key, value = tokens.pop(0).split("=", 1)
            if not key.replace("_", "").isalnum():
                return None
            env_updates[key] = value
        if not tokens:
            return None
        executable = tokens[0]
        if executable in {"python", "python3"}:
            tokens[0] = sys.executable
            if tokens[1:3] == ["-m", "unittest"]:
                return env_updates, tokens
        if tokens == ["npm", "test"]:
            return env_updates, tokens
        if tokens == ["cargo", "test"]:
            return env_updates, tokens
        return None

    def _run_command(
        self,
        command: str,
        cwd: str,
        env_updates: dict[str, str],
        argv: list[str],
    ) -> ValidationCommandResult:
        started = perf_counter()
        env = {**os.environ, **env_updates}
        try:
            completed = subprocess.run(
                argv,
                cwd=str(Path(cwd)),
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            duration_ms = (perf_counter() - started) * 1000
            return ValidationCommandResult(
                command=command,
                cwd=str(Path(cwd)),
                status="passed" if completed.returncode == 0 else "failed",
                exit_code=completed.returncode,
                stdout=completed.stdout[-4_000:],
                stderr=completed.stderr[-4_000:],
                duration_ms=round(duration_ms, 3),
                reason="Command executed through deterministic validation allowlist.",
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = (perf_counter() - started) * 1000
            return ValidationCommandResult(
                command=command,
                cwd=str(Path(cwd)),
                status="failed",
                stdout=(exc.stdout or "")[-4_000:] if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "")[-4_000:] if isinstance(exc.stderr, str) else "",
                duration_ms=round(duration_ms, 3),
                reason="Command timed out after 30 seconds.",
            )
