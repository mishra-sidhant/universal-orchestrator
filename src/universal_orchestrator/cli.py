from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import monotonic

from universal_orchestrator import __version__
from universal_orchestrator.config import (
    DEFAULT_ENV_FILE,
    configuration_template,
    load_env_file,
    provider_config_status,
    write_env_example,
)
from universal_orchestrator.models import (
    Host,
    HostInvocation,
    InputAttachment,
    ProviderTask,
    TaskNode,
    TaskType,
    UserOptions,
)
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.utils import read_json
from universal_orchestrator.evals import EvaluationRunner, built_in_suite


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", None)
    if command is None:
        parser.print_help()
        return
    handler = getattr(args, "handler")
    try:
        handler(args)
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-team", description="Universal AI Executive Kernel CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run the orchestrator on a prompt and optional paths")
    _add_run_args(run_parser)
    run_parser.set_defaults(handler=handle_run)

    repo_parser = sub.add_parser("repo", help="Repo-focused shortcut for implementation or review tasks")
    _add_run_args(repo_parser)
    repo_parser.set_defaults(handler=handle_repo)

    doctor_parser = sub.add_parser("doctor", help="Inspect local runtime readiness")
    doctor_parser.set_defaults(handler=handle_doctor)

    providers_parser = sub.add_parser("providers", help="List provider descriptors and health")
    providers_parser.set_defaults(handler=handle_providers)

    configure_parser = sub.add_parser("configure", help="Show or write local provider configuration template")
    configure_parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    configure_parser.add_argument("--write-example", action="store_true")
    configure_parser.add_argument("--json", action="store_true")
    configure_parser.set_defaults(handler=handle_configure)

    smoke_parser = sub.add_parser("smoke", help="Run one explicit live provider round-trip")
    smoke_parser.add_argument("--provider", required=True)
    smoke_parser.add_argument("--timeout", type=int, default=30)
    smoke_parser.set_defaults(handler=handle_smoke)

    mcp_parser = sub.add_parser("mcp-server", help="Run the stdio MCP-style host adapter")
    mcp_parser.set_defaults(handler=handle_mcp_server)

    artifacts_parser = sub.add_parser("artifacts", help="List local run artifact directories")
    artifacts_parser.add_argument("--root", default=".uo/runs")
    artifacts_parser.set_defaults(handler=handle_artifacts)

    status_parser = sub.add_parser("status", help="Show a run manifest")
    status_parser.add_argument("run_id")
    status_parser.add_argument("--root", default=".uo/runs")
    status_parser.set_defaults(handler=handle_status)

    cancel_parser = sub.add_parser("cancel", help="Request cancellation for a durable run")
    cancel_parser.add_argument("run_id")
    cancel_parser.add_argument("--root", default=".uo/runs")
    cancel_parser.add_argument("--reason", default="User requested cancellation.")
    cancel_parser.set_defaults(handler=handle_cancel)

    resume_parser = sub.add_parser("resume", help="Resume a failed or cancelled durable run")
    resume_parser.add_argument("run_id")
    resume_parser.add_argument("--root", default=".uo/runs")
    resume_parser.set_defaults(handler=handle_resume)

    evals_parser = sub.add_parser("evals", help="List or run built-in world-readiness evaluation cases")
    evals_parser.add_argument("--run", action="store_true", help="Execute the built-in eval suite")
    evals_parser.add_argument("--root", default=".uo/evals", help="Eval artifact root")
    evals_parser.add_argument("--case", action="append", default=[], help="Run only a specific eval case id")
    evals_parser.set_defaults(handler=handle_evals)

    return parser


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("prompt")
    parser.add_argument("paths", nargs="*", help="Files, folders, repos, or URLs to ingest")
    parser.add_argument("--host", default=Host.TERMINAL.value, choices=[host.value for host in Host])
    parser.add_argument("--quality", default="serious", choices=["fast", "standard", "serious", "max"])
    parser.add_argument("--budget", default="balanced", choices=["cheap", "balanced", "premium", "unlimited"])
    parser.add_argument("--artifact", action="append", default=[], help="Requested artifact type")
    parser.add_argument("--allow-internet", action="store_true")
    parser.add_argument("--allow-url-host", action="append", default=[])
    parser.add_argument("--allow-cloud", action="store_true")
    parser.add_argument("--allow-repo-writes", action="store_true")
    parser.add_argument("--allow-shell", action="store_true")
    parser.add_argument("--root", default=".uo/runs", help="Artifact root")


def handle_run(args: argparse.Namespace) -> None:
    invocation = _invocation_from_args(args, command="run")
    result = Orchestrator(args.root).run(invocation)
    _print_run_result(result.run_id, result.artifact_dir, result.quality.passed)


def handle_repo(args: argparse.Namespace) -> None:
    paths = args.paths or ["."]
    args.paths = paths
    invocation = _invocation_from_args(args, command="repo")
    result = Orchestrator(args.root).run(invocation)
    _print_run_result(result.run_id, result.artifact_dir, result.quality.passed)


def handle_doctor(args: argparse.Namespace) -> None:
    del args
    load_env_file()
    checks = {
        "python": sys.version.split()[0],
        "pydantic": _module_available("pydantic"),
        "pdfplumber": _module_available("pdfplumber"),
        "pypdf": _module_available("pypdf"),
        "fastapi_optional": _module_available("fastapi"),
        "typer_optional": _module_available("typer"),
        "provider_config": provider_config_status(),
    }
    print(json.dumps(checks, indent=2, sort_keys=True))


def handle_providers(args: argparse.Namespace) -> None:
    del args
    registry = CapabilityRegistry.from_environment()
    payload = [provider.model_dump(mode="json") for provider in registry.providers]
    print(json.dumps(payload, indent=2, sort_keys=True))


def handle_configure(args: argparse.Namespace) -> None:
    if args.write_example:
        path = write_env_example()
        print(f"wrote: {path}")
    status = provider_config_status(args.env_file)
    if args.json:
        print(json.dumps({"env_file": args.env_file, "providers": status}, indent=2, sort_keys=True))
        return
    print(f"Recommended secrets file: {args.env_file}")
    print("Add provider keys/models there when you are ready. Values are never printed by doctor.")
    print("")
    print(configuration_template())
    print("Provider readiness:")
    for provider_id, provider_status in status.items():
        ready = "ready" if provider_status["ready"] else "missing " + ", ".join(provider_status["missing"])
        print(f"- {provider_id}: {ready}")


def handle_smoke(args: argparse.Namespace) -> None:
    load_env_file()
    registry = CapabilityRegistry.from_environment()
    descriptor = next(
        (provider for provider in registry.providers if provider.id == args.provider),
        None,
    )
    if descriptor is None:
        raise ValueError(f"Unknown provider: {args.provider}")
    if not descriptor.enabled:
        raise RuntimeError(f"{args.provider} is not configured; run `ai-team configure` for required values.")
    adapter = registry.adapter_registry().require(args.provider)
    task = ProviderTask(
        task=TaskNode(
            id="T-SMOKE",
            run_id="R-SMOKE",
            title="Provider smoke check",
            task_type=TaskType.FINAL_SYNTHESIS,
        ),
        prompt="Reply with exactly: smoke-ok",
        dry_run=False,
        allow_network=True,
        timeout_seconds=max(1, args.timeout),
    )
    started = monotonic()
    result = adapter.execute(task)
    latency_ms = round((monotonic() - started) * 1_000)
    estimate = adapter.estimate_cost(task)
    print(
        json.dumps(
            {
                "provider": args.provider,
                "status": result.status,
                "latency_ms": latency_ms,
                "usage": result.output.get("usage", {}),
                "estimated_cost_usd": estimate.estimated_usd,
                "response_received": bool(result.output.get("summary")),
            },
            indent=2,
            sort_keys=True,
        )
    )


def handle_mcp_server(args: argparse.Namespace) -> None:
    del args
    from universal_orchestrator.mcp import serve_stdio

    serve_stdio()


def handle_artifacts(args: argparse.Namespace) -> None:
    runs = Orchestrator(args.root).list_runs()
    for run_dir in runs:
        print(run_dir)


def handle_status(args: argparse.Namespace) -> None:
    path = Path(args.root) / args.run_id / "run_manifest.json"
    payload = read_json(path) if path.exists() else {"run_id": args.run_id}
    runtime = RuntimeStore(Path(args.root) / "runtime.sqlite3")
    payload["runtime_snapshot"] = runtime.resumable_snapshot(args.run_id)
    print(json.dumps(payload, indent=2, sort_keys=True))


def handle_cancel(args: argparse.Namespace) -> None:
    runtime = RuntimeStore(Path(args.root) / "runtime.sqlite3")
    print(json.dumps(runtime.request_cancel(args.run_id, args.reason), indent=2, sort_keys=True, default=str))


def handle_resume(args: argparse.Namespace) -> None:
    result = Orchestrator(args.root).resume(args.run_id)
    _print_run_result(result.run_id, result.artifact_dir, result.quality.passed)


def handle_evals(args: argparse.Namespace) -> None:
    if args.run:
        report = EvaluationRunner().run(root=args.root, case_ids=args.case or None)
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    print(json.dumps(built_in_suite().model_dump(mode="json"), indent=2, sort_keys=True))


def _invocation_from_args(args: argparse.Namespace, command: str) -> HostInvocation:
    options = UserOptions(
        quality=args.quality,
        budget_profile=args.budget,
        artifact_types=args.artifact,
        allow_internet=args.allow_internet,
        allowed_url_hosts=args.allow_url_host,
        allow_cloud=args.allow_cloud,
        allow_repo_writes=args.allow_repo_writes,
        allow_shell=args.allow_shell,
    )
    return HostInvocation(
        host=args.host,
        command=command,
        prompt=args.prompt,
        cwd=str(Path.cwd()),
        attachments=[InputAttachment(uri=path) for path in args.paths],
        user_options=options,
    )


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except Exception:
        return False
    return True


def _print_run_result(run_id: str, artifact_dir: str, passed: bool) -> None:
    print(f"run_id: {run_id}")
    print(f"artifact_dir: {artifact_dir}")
    print(f"quality_passed: {passed}")
