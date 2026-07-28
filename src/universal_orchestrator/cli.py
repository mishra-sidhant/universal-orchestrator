from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from time import monotonic

from universal_orchestrator import __version__
from universal_orchestrator.application_config import (
    AppConfig,
    ConfigPaths,
    CredentialStore,
    initialize,
    load_config,
    migrate_env_file,
    save_config,
    save_profile,
)
from universal_orchestrator.bench import BenchmarkRunner
from universal_orchestrator.config import (
    DEFAULT_ENV_FILE,
    configuration_template,
    load_env_file,
    provider_config_status,
    write_env_example,
)
from universal_orchestrator.cost_ledger import CostLedger
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
from universal_orchestrator.repo_transaction import RepositoryEdit
from universal_orchestrator.repo_workflow import RepositoryWorkflow
from universal_orchestrator.release_gate import ReleaseGateRunner
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

    bench_parser = sub.add_parser("bench", help="Measure native and orchestrated output side by side")
    _add_run_args(bench_parser)
    bench_parser.set_defaults(handler=handle_bench, root=".uo/bench")

    repo_parser = sub.add_parser("repo", help="Repo-focused shortcut for implementation or review tasks")
    _add_run_args(repo_parser)
    repo_parser.set_defaults(handler=handle_repo)

    repo_prepare_parser = sub.add_parser(
        "repo-prepare", help="Prepare an approval-bound repository change set without writing"
    )
    repo_prepare_parser.add_argument("repo_root")
    repo_prepare_parser.add_argument("--edits-json", default=None)
    repo_prepare_parser.add_argument("--run-id", default=None)
    repo_prepare_parser.add_argument("--output", default=None)
    repo_prepare_parser.add_argument("--allow-dirty-snapshot", action="store_true")
    repo_prepare_parser.set_defaults(handler=handle_repo_prepare)

    repo_apply_parser = sub.add_parser("repo-apply", help="Apply a prepared repository change set")
    repo_apply_parser.add_argument("changeset")
    repo_apply_parser.add_argument("--approval-digest", required=True)
    repo_apply_parser.add_argument("--root", default=None)
    repo_apply_parser.add_argument("--allow-repo-writes", action="store_true")
    repo_apply_parser.set_defaults(handler=handle_repo_apply)

    repo_publish_parser = sub.add_parser("repo-publish", help="Create a branch from an isolated worktree")
    repo_publish_parser.add_argument("worktree")
    repo_publish_parser.add_argument("--branch", required=True)
    repo_publish_parser.add_argument("--commit-message", default=None)
    repo_publish_parser.set_defaults(handler=handle_repo_publish)

    doctor_parser = sub.add_parser("doctor", help="Inspect local runtime readiness")
    doctor_parser.set_defaults(handler=handle_doctor)

    providers_parser = sub.add_parser("providers", help="List provider descriptors and health")
    providers_parser.set_defaults(handler=handle_providers)

    capacity_parser = sub.add_parser("capacity", help="Show observed provider/model capacity windows")
    capacity_parser.add_argument("--root", default=".uo/runs")
    capacity_parser.add_argument("--json", action="store_true")
    capacity_parser.set_defaults(handler=handle_capacity)

    configure_parser = sub.add_parser("configure", help="Show or write local provider configuration template")
    configure_parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    configure_parser.add_argument("--write-example", action="store_true")
    configure_parser.add_argument("--json", action="store_true")
    configure_parser.set_defaults(handler=handle_configure)

    smoke_parser = sub.add_parser("smoke", help="Run one explicit live provider round-trip")
    smoke_parser.add_argument("--provider", required=True)
    smoke_parser.add_argument("--timeout", type=int, default=30)
    smoke_parser.add_argument("--cost-ceiling", type=float, default=0.50)
    smoke_parser.set_defaults(handler=handle_smoke)

    mcp_parser = sub.add_parser("mcp-server", help="Run the stdio MCP-style host adapter")
    mcp_parser.set_defaults(handler=handle_mcp_server)

    daemon_parser = sub.add_parser("daemon", help="Run or inspect the optional local HTTP daemon")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_command", required=True)
    daemon_serve = daemon_sub.add_parser("serve", help="Serve the authenticated local API")
    daemon_serve.add_argument("--root", default=".uo/runs")
    daemon_serve.add_argument("--host", default="127.0.0.1")
    daemon_serve.add_argument("--port", type=int, default=8765)
    daemon_serve.set_defaults(handler=handle_daemon_serve)
    daemon_status_parser = daemon_sub.add_parser("status", help="Show local daemon configuration readiness")
    daemon_status_parser.add_argument("--root", default=".uo/runs")
    daemon_status_parser.set_defaults(handler=handle_daemon_status)

    integrate_parser = sub.add_parser("integrate", help="Print host MCP configuration")
    integrate_parser.add_argument(
        "--host",
        required=True,
        choices=["codex", "claude-code", "cursor", "vscode", "windsurf", "generic"],
    )
    integrate_parser.add_argument("--scope", choices=["user", "project"], default="user")
    integrate_parser.add_argument("--path", default=None, help="Override the host configuration path")
    integrate_parser.add_argument("--install", action="store_true")
    integrate_parser.add_argument("--verify", action="store_true")
    integrate_parser.add_argument("--uninstall", action="store_true")
    integrate_parser.add_argument("--json", action="store_true")
    integrate_parser.set_defaults(handler=handle_integrate)

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

    release_parser = sub.add_parser(
        "release-gate", help="Run the offline adversarial release gate"
    )
    release_parser.add_argument("--root", default=".uo/release-gate")
    release_parser.set_defaults(handler=handle_release_gate)

    init_parser = sub.add_parser("init", help="Initialize user configuration and runtime directories")
    init_parser.add_argument("--home", default=None, help="Override the application home directory")
    init_parser.add_argument("--overwrite", action="store_true")
    init_parser.set_defaults(handler=handle_init)

    config_parser = sub.add_parser("config", help="Inspect and migrate application configuration")
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_show = config_sub.add_parser("show", help="Show non-secret effective configuration")
    config_show.add_argument("--home", default=None)
    config_show.set_defaults(handler=handle_config_show)
    config_validate = config_sub.add_parser("validate", help="Validate application configuration")
    config_validate.add_argument("--home", default=None)
    config_validate.set_defaults(handler=handle_config_validate)
    config_migrate = config_sub.add_parser("migrate", help="Import non-secret values from .env.local")
    config_migrate.add_argument("--home", default=None)
    config_migrate.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    config_migrate.set_defaults(handler=handle_config_migrate)

    profile_parser = sub.add_parser("profile", help="Manage non-secret routing profiles")
    profile_sub = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_list = profile_sub.add_parser("list")
    profile_list.add_argument("--home", default=None)
    profile_list.set_defaults(handler=handle_profile_list)
    profile_create = profile_sub.add_parser("create")
    profile_create.add_argument("name")
    profile_create.add_argument("--home", default=None)
    profile_create.set_defaults(handler=handle_profile_create)
    profile_select = profile_sub.add_parser("select")
    profile_select.add_argument("name")
    profile_select.add_argument("--home", default=None)
    profile_select.set_defaults(handler=handle_profile_select)

    provider_parser = sub.add_parser("provider", help="Manage provider profile metadata and credentials")
    provider_sub = provider_parser.add_subparsers(dest="provider_command", required=True)
    provider_add = provider_sub.add_parser("add")
    provider_add.add_argument("provider_id")
    provider_add.add_argument("--model")
    provider_add.add_argument("--base-url")
    provider_add.add_argument("--credential-env")
    provider_add.add_argument("--credential", action="store_true", help="Read a credential without echoing it")
    provider_add.add_argument("--home", default=None)
    provider_add.set_defaults(handler=handle_provider_add)
    provider_remove = provider_sub.add_parser("remove")
    provider_remove.add_argument("provider_id")
    provider_remove.add_argument("--home", default=None)
    provider_remove.set_defaults(handler=handle_provider_remove)
    provider_list = provider_sub.add_parser("list")
    provider_list.add_argument("--home", default=None)
    provider_list.set_defaults(handler=handle_provider_list)

    return parser


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("prompt")
    parser.add_argument("paths", nargs="*", help="Files, folders, repos, or URLs to ingest")
    parser.add_argument("--host", default=Host.TERMINAL.value, choices=[host.value for host in Host])
    parser.add_argument("--quality", default="serious", choices=["fast", "standard", "serious", "max"])
    parser.add_argument("--budget", default="balanced", choices=["cheap", "balanced", "premium", "unlimited"])
    parser.add_argument("--cost-ceiling", type=float, default=0.50)
    parser.add_argument("--artifact", action="append", default=[], help="Requested artifact type")
    parser.add_argument("--allow-internet", action="store_true")
    parser.add_argument("--allow-url-host", action="append", default=[])
    parser.add_argument("--allow-cloud", action="store_true")
    parser.add_argument("--allow-repo-writes", action="store_true")
    parser.add_argument("--allow-shell", action="store_true")
    parser.add_argument(
        "--verification-mode",
        default="structural",
        choices=["structural", "semantic", "required_semantic"],
        help="Choose structural evidence checks or an explicitly configured semantic verifier",
    )
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


def handle_repo_prepare(args: argparse.Namespace) -> None:
    edits: list[RepositoryEdit] = []
    if args.edits_json:
        payload = json.loads(Path(args.edits_json).read_text())
        if not isinstance(payload, list):
            raise ValueError("--edits-json must contain a JSON array of repository edits.")
        edits = [RepositoryEdit.model_validate(item) for item in payload]
    from universal_orchestrator.models import new_id

    run_id = args.run_id or new_id("repo")
    workflow = RepositoryWorkflow()
    changeset = workflow.prepare(
        args.repo_root,
        run_id=run_id,
        edits=edits,
        allow_dirty_snapshot=args.allow_dirty_snapshot,
    )
    output = Path(args.output) if args.output else Path(".uo") / "repo" / f"{run_id}.json"
    workflow.write_changeset(changeset, output)
    print(json.dumps({"changeset": str(output), **changeset.model_dump(mode="json")}, indent=2, sort_keys=True))


def handle_repo_apply(args: argparse.Namespace) -> None:
    workflow = RepositoryWorkflow()
    changeset = workflow.read_changeset(args.changeset)
    report = workflow.apply(
        changeset,
        approval_digest=args.approval_digest,
        allow_repo_writes=args.allow_repo_writes,
        root_override=args.root,
    )
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    if not report.committed:
        raise SystemExit(1)


def handle_repo_publish(args: argparse.Namespace) -> None:
    payload = RepositoryWorkflow().publish(
        args.worktree,
        branch=args.branch,
        commit_message=args.commit_message,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


def handle_bench(args: argparse.Namespace) -> None:
    invocation = _invocation_from_args(args, command="bench")
    result = BenchmarkRunner(args.root).run(invocation)
    print(json.dumps(result, indent=2, sort_keys=True))


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


def handle_capacity(args: argparse.Namespace) -> None:
    runtime = RuntimeStore(Path(args.root) / "runtime.sqlite3")
    snapshots = runtime.capacity_snapshots()
    payload = {
        "root": args.root,
        "snapshots": [snapshot.model_dump(mode="json") for snapshot in snapshots],
        "note": "No observation is reported as unknown, never as unlimited.",
    }
    if args.json or not snapshots:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for snapshot in snapshots:
        print(
            f"{snapshot.connector_id}: {snapshot.status} "
            f"source={snapshot.source} confidence={snapshot.confidence:.2f}"
        )


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
    cost_ledger = CostLedger("R-SMOKE", ceiling_usd=args.cost_ceiling)
    registry.cost_ledger = cost_ledger
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
    estimate = result.cost_estimate or adapter.estimate_cost(task)
    ledger = cost_ledger.snapshot()
    print(
        json.dumps(
            {
                "provider": args.provider,
                "status": result.status,
                "latency_ms": latency_ms,
                "usage": result.output.get("usage", {}),
                "estimated_cost_usd": estimate.estimated_usd,
                "actual_cost_usd": ledger.total_actual_usd,
                "cost_ceiling_usd": ledger.cost_ceiling_usd,
                "rate_table_version": ledger.rate_table_version,
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


def handle_daemon_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("FastAPI daemon support is not installed; use the `daemon` extra.") from exc
    from universal_orchestrator.daemon import create_app

    uvicorn.run(create_app(args.root), host=args.host, port=args.port, log_level="info")


def handle_daemon_status(args: argparse.Namespace) -> None:
    print(
        json.dumps(
            {
                "root": args.root,
                "api_version": "v1",
                "bind_default": "127.0.0.1",
                "token_configured": bool(os.getenv("AI_TEAM_DAEMON_TOKEN")),
            },
            indent=2,
            sort_keys=True,
        )
    )


def handle_integrate(args: argparse.Namespace) -> None:
    from universal_orchestrator.integrations import IntegrationManager

    manager = IntegrationManager()
    actions = sum(bool(value) for value in (args.install, args.verify, args.uninstall))
    if actions > 1:
        raise ValueError("Choose only one of --install, --verify, or --uninstall.")
    if args.install:
        payload = manager.install(args.host, scope=args.scope, explicit_path=args.path).model_dump(mode="json")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if args.verify:
        payload = manager.verify(args.host, scope=args.scope, explicit_path=args.path)
        print(json.dumps(payload, indent=2, sort_keys=True))
        if not payload.get("configured"):
            raise SystemExit(1)
        return
    if args.uninstall:
        payload = manager.uninstall(args.host, scope=args.scope, explicit_path=args.path).model_dump(mode="json")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    command = {
        "command": "ai-team",
        "args": ["mcp-server"],
    }
    if args.host == "vscode":
        payload = {"servers": {"universal-orchestrator": command}}
    else:
        payload = {"mcpServers": {"universal-orchestrator": command}}
    print(json.dumps({"host": args.host, "configuration": payload}, indent=2, sort_keys=True))


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


def handle_release_gate(args: argparse.Namespace) -> None:
    report = ReleaseGateRunner().run(args.root)
    print(json.dumps(report, indent=2, sort_keys=True))


def _config_paths(home: str | None) -> ConfigPaths:
    return ConfigPaths(home) if home else ConfigPaths()


def handle_init(args: argparse.Namespace) -> None:
    paths = _config_paths(args.home)
    config = initialize(paths, overwrite=args.overwrite)
    print(json.dumps({"home": str(paths.root), "config": config.model_dump(mode="json")}, indent=2, sort_keys=True))


def handle_config_show(args: argparse.Namespace) -> None:
    config = load_config(_config_paths(args.home))
    print(json.dumps(config.model_dump(mode="json"), indent=2, sort_keys=True))


def handle_config_validate(args: argparse.Namespace) -> None:
    paths = _config_paths(args.home)
    config = load_config(paths)
    print(json.dumps({"valid": True, "home": str(paths.root), "schema_version": config.schema_version}, indent=2))


def handle_config_migrate(args: argparse.Namespace) -> None:
    config, loaded = migrate_env_file(args.env_file, _config_paths(args.home))
    print(json.dumps({"migrated": loaded, "config": config.model_dump(mode="json")}, indent=2, sort_keys=True))


def handle_profile_list(args: argparse.Namespace) -> None:
    paths = _config_paths(args.home)
    paths.create()
    names = sorted(path.stem for path in paths.profiles_dir.glob("*.toml"))
    if "default" not in names:
        names.insert(0, "default")
    config = load_config(paths)
    print(json.dumps({"active": config.active_profile, "profiles": names}, indent=2, sort_keys=True))


def handle_profile_create(args: argparse.Namespace) -> None:
    paths = _config_paths(args.home)
    config = load_config(paths)
    target = paths.profiles_dir / f"{args.name}.toml"
    if target.exists():
        raise ValueError(f"Profile already exists: {args.name}")
    save_profile(config.model_copy(update={"active_profile": args.name}), args.name, paths)
    print(f"created profile: {args.name}")


def handle_profile_select(args: argparse.Namespace) -> None:
    paths = _config_paths(args.home)
    profile_path = paths.profiles_dir / f"{args.name}.toml"
    if not profile_path.exists():
        raise ValueError(f"Unknown profile: {args.name}")
    config = load_config(paths, profile=args.name).model_copy(update={"active_profile": args.name})
    save_config(config, paths)
    print(f"selected profile: {args.name}")


def handle_provider_list(args: argparse.Namespace) -> None:
    config = load_config(_config_paths(args.home))
    print(json.dumps(config.model_dump(mode="json")["providers"], indent=2, sort_keys=True))


def handle_provider_add(args: argparse.Namespace) -> None:
    paths = _config_paths(args.home)
    config = load_config(paths)
    current = config.providers.get(args.provider_id)
    credential_env = args.credential_env or (current.credential_env if current else None)
    credential_ref = current.credential_ref if current else None
    if args.credential:
        import getpass

        if not credential_env:
            raise ValueError("--credential-env is required when storing a credential")
        credential_ref = f"{config.active_profile}:{args.provider_id}"
        CredentialStore().set(credential_ref, getpass.getpass(f"Credential for {args.provider_id}: "))
    profile = (current or AppConfig().providers.get(args.provider_id))
    if current is None:
        from universal_orchestrator.application_config import ProviderProfile

        profile = ProviderProfile(provider_id=args.provider_id)
    assert profile is not None
    profile = profile.model_copy(
        update={
            "model": args.model if args.model is not None else profile.model,
            "base_url": args.base_url if args.base_url is not None else profile.base_url,
            "credential_env": credential_env,
            "credential_ref": credential_ref,
        }
    )
    config.providers[args.provider_id] = profile
    save_config(config, paths)
    print(json.dumps(profile.model_dump(mode="json"), indent=2, sort_keys=True))


def handle_provider_remove(args: argparse.Namespace) -> None:
    paths = _config_paths(args.home)
    config = load_config(paths)
    profile = config.providers.pop(args.provider_id, None)
    if profile is None:
        raise ValueError(f"Unknown provider profile: {args.provider_id}")
    if profile.credential_ref:
        CredentialStore().delete(profile.credential_ref)
    save_config(config, paths)
    print(f"removed provider: {args.provider_id}")


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
        verification_mode=args.verification_mode,
        cost_ceiling_usd=args.cost_ceiling,
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
