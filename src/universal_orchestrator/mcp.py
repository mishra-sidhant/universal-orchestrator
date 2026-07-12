from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, TextIO

from universal_orchestrator.cli import _module_available
from universal_orchestrator.config import configuration_template, load_env_file, provider_config_status
from universal_orchestrator.evals import EvaluationRunner, built_in_suite
from universal_orchestrator.models import Host, HostInvocation, InputAttachment, UserOptions, new_id
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.runtime import RuntimeStore
from universal_orchestrator.utils import read_json


_ASYNC_RUN_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="uo-mcp-job")


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "ai_team.run",
            "description": "Run the Universal Orchestrator on a prompt plus optional files, folders, repos, or URLs.",
            "inputSchema": {
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "root": {"type": "string", "default": ".uo/runs"},
                    "quality": {"type": "string", "default": "serious"},
                    "budget": {"type": "string", "default": "balanced"},
                    "allow_internet": {"type": "boolean", "default": False},
                    "allowed_url_hosts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "allow_cloud": {"type": "boolean", "default": False},
                    "artifact_types": {"type": "array", "items": {"type": "string"}, "default": []},
                    "cost_ceiling": {"type": "number", "default": 0.50, "minimum": 0.01},
                    "allow_repo_writes": {"type": "boolean", "default": False},
                    "allow_shell": {"type": "boolean", "default": False},
                    "privacy_mode": {
                        "type": "string",
                        "enum": ["local_only", "balanced", "cloud_allowed", "explicit_approval"],
                        "default": "balanced",
                    },
                },
            },
        },
        {
            "name": "ai_team.run_start",
            "description": "Start a durable run and return immediately with its run id.",
            "inputSchema": {
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "root": {"type": "string", "default": ".uo/runs"},
                    "quality": {"type": "string", "default": "serious"},
                    "budget": {"type": "string", "default": "balanced"},
                    "allow_internet": {"type": "boolean", "default": False},
                    "allow_cloud": {"type": "boolean", "default": False},
                    "allowed_url_hosts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "artifact_types": {"type": "array", "items": {"type": "string"}, "default": []},
                    "cost_ceiling": {"type": "number", "default": 0.50, "minimum": 0.01},
                    "allow_repo_writes": {"type": "boolean", "default": False},
                    "allow_shell": {"type": "boolean", "default": False},
                    "privacy_mode": {
                        "type": "string",
                        "enum": ["local_only", "balanced", "cloud_allowed", "explicit_approval"],
                        "default": "balanced",
                    },
                },
            },
        },
        {
            "name": "ai_team.status",
            "description": "Read a run manifest by run id.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "root": {"type": "string", "default": ".uo/runs"},
                },
            },
        },
        {
            "name": "ai_team.artifacts",
            "description": "List local run artifact directories.",
            "inputSchema": {
                "type": "object",
                "properties": {"root": {"type": "string", "default": ".uo/runs"}},
            },
        },
        {
            "name": "ai_team.providers",
            "description": "List provider descriptors and health without printing secrets.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "ai_team.doctor",
            "description": "Inspect runtime dependencies and provider configuration readiness.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "ai_team.configure",
            "description": "Return the local provider configuration template and readiness status.",
            "inputSchema": {
                "type": "object",
                "properties": {"env_file": {"type": "string", "default": ".env.local"}},
            },
        },
        {
            "name": "ai_team.capacity",
            "description": "Read observed provider/model capacity windows without secrets.",
            "inputSchema": {
                "type": "object",
                "properties": {"root": {"type": "string", "default": ".uo/runs"}},
            },
        },
        {
            "name": "ai_team.events",
            "description": "Read the durable redacted runtime event stream for a run.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "root": {"type": "string", "default": ".uo/runs"},
                },
            },
        },
        {
            "name": "ai_team.cancel",
            "description": "Request durable cancellation for a run.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "root": {"type": "string", "default": ".uo/runs"},
                    "reason": {"type": "string", "default": "User requested cancellation."},
                },
            },
        },
        {
            "name": "ai_team.evals",
            "description": "List or run built-in world-readiness evaluation cases.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run": {"type": "boolean", "default": False},
                    "root": {"type": "string", "default": ".uo/evals"},
                    "case_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        {
            "name": "ai_team.resume",
            "description": "Resume a failed or cancelled durable run.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {
                    "run_id": {"type": "string"},
                    "root": {"type": "string", "default": ".uo/runs"},
                },
            },
        },
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    if name == "ai_team.run":
        return _tool_run(args)
    if name == "ai_team.run_start":
        return _tool_run_start(args)
    if name == "ai_team.status":
        return _tool_status(args)
    if name == "ai_team.artifacts":
        return _tool_artifacts(args)
    if name == "ai_team.providers":
        return _tool_providers()
    if name == "ai_team.capacity":
        return _tool_capacity(args)
    if name == "ai_team.events":
        return _tool_events(args)
    if name == "ai_team.doctor":
        return _tool_doctor()
    if name == "ai_team.configure":
        return _tool_configure(args)
    if name == "ai_team.cancel":
        return _tool_cancel(args)
    if name == "ai_team.evals":
        return _tool_evals(args)
    if name == "ai_team.resume":
        return _tool_resume(args)
    raise ValueError(f"Unknown tool: {name}")


def serve_stdio(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    write_lock = Lock()

    def write_response(response: dict[str, Any] | None) -> None:
        if response is None:
            return
        with write_lock:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="uo-mcp-run") as workers:
        def dispatch(item: dict[str, Any]) -> None:
            write_response(handle_json_rpc(item))

        for line in stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                write_response(_error(None, -32700, f"Parse error: {exc.msg}"))
                continue
            if not isinstance(request, dict):
                write_response(_error(None, -32600, "Invalid Request"))
                continue
            if _is_run_request(request) and "id" in request:
                workers.submit(dispatch, request)
            else:
                write_response(handle_json_rpc(request))


def handle_json_rpc(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    try:
        result: dict[str, Any]
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "universal-orchestrator", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": tool_definitions()}
        elif method == "tools/call":
            params_value = request.get("params", {})
            params = params_value if isinstance(params_value, dict) else {}
            arguments_value = params.get("arguments", {})
            arguments = arguments_value if isinstance(arguments_value, dict) else {}
            payload = call_tool(str(params.get("name", "")), arguments)
            result = {"content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}]}
        elif method == "ping":
            result = {}
        else:
            response = _error(request_id, -32601, f"Method not found: {method}")
            return None if request_id is None else response
        response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        return None if request_id is None else response
    except Exception as exc:  # pragma: no cover - protocol boundary
        response = _error(request_id, -32000, str(exc))
        return None if request_id is None else response


def _is_run_request(request: dict[str, Any]) -> bool:
    params = request.get("params")
    return (
        request.get("method") == "tools/call"
        and isinstance(params, dict)
        and params.get("name") in {"ai_team.run", "ai_team.run_start"}
    )


def _tool_run(args: dict[str, Any]) -> dict[str, Any]:
    root = str(args.get("root", ".uo/runs"))
    result = Orchestrator(root).run(_invocation_from_args(args, "mcp.run"))
    return {
        "run_id": result.run_id,
        "state": result.state,
        "artifact_dir": result.artifact_dir,
        "quality_passed": result.quality.passed,
        "manifest_path": str(Path(result.artifact_dir) / "run_manifest.json"),
    }


def _tool_run_start(args: dict[str, Any]) -> dict[str, Any]:
    root = str(args.get("root", ".uo/runs"))
    run_id = new_id("run")
    _ASYNC_RUN_WORKERS.submit(
        Orchestrator(root).run,
        _invocation_from_args(args, "mcp.run_start"),
        run_id,
    )
    return {
        "run_id": run_id,
        "state": "received",
        "artifact_dir": str(Path(root) / run_id),
        "accepted": True,
        "poll_with": "ai_team.status",
    }


def _invocation_from_args(args: dict[str, Any], command: str) -> HostInvocation:
    prompt = str(args["prompt"])
    paths = args.get("paths", [])
    options = UserOptions(
        quality=args.get("quality", "serious"),
        budget_profile=args.get("budget", "balanced"),
        artifact_types=[str(item) for item in args.get("artifact_types", [])],
        allow_internet=bool(args.get("allow_internet", False)),
        allowed_url_hosts=[str(host) for host in args.get("allowed_url_hosts", [])],
        allow_cloud=bool(args.get("allow_cloud", False)),
        allow_repo_writes=bool(args.get("allow_repo_writes", False)),
        allow_shell=bool(args.get("allow_shell", False)),
        privacy_mode=args.get("privacy_mode", "balanced"),
        cost_ceiling_usd=float(args.get("cost_ceiling", 0.50)),
    )
    return HostInvocation(
        host=Host.API,
        command=command,
        prompt=prompt,
        cwd=str(Path.cwd()),
        attachments=[InputAttachment(uri=str(path)) for path in paths],
        user_options=options,
    )


def _tool_status(args: dict[str, Any]) -> dict[str, Any]:
    root = Path(args.get("root", ".uo/runs"))
    path = root / args["run_id"] / "run_manifest.json"
    payload = read_json(path) if path.exists() else {"run_id": args["run_id"]}
    runtime = RuntimeStore(root / "runtime.sqlite3")
    payload["runtime_snapshot"] = runtime.resumable_snapshot(args["run_id"])
    return payload


def _tool_artifacts(args: dict[str, Any]) -> dict[str, Any]:
    root = args.get("root", ".uo/runs")
    runs = [str(path) for path in Orchestrator(root).list_runs()]
    return {"root": root, "runs": runs}


def _tool_providers() -> dict[str, Any]:
    registry = CapabilityRegistry.from_environment()
    return {"providers": [provider.model_dump(mode="json") for provider in registry.providers]}


def _tool_capacity(args: dict[str, Any]) -> dict[str, Any]:
    root = Path(args.get("root", ".uo/runs"))
    runtime = RuntimeStore(root / "runtime.sqlite3")
    return {
        "root": str(root),
        "snapshots": [snapshot.model_dump(mode="json") for snapshot in runtime.capacity_snapshots()],
        "disclosure": "Unknown capacity is not treated as unlimited.",
    }


def _tool_events(args: dict[str, Any]) -> dict[str, Any]:
    root = Path(args.get("root", ".uo/runs"))
    runtime = RuntimeStore(root / "runtime.sqlite3")
    return {"run_id": args["run_id"], "events": runtime.list_events(args["run_id"])}


def _tool_doctor() -> dict[str, Any]:
    load_env_file()
    return {
        "python": sys.version.split()[0],
        "pydantic": _module_available("pydantic"),
        "pdfplumber": _module_available("pdfplumber"),
        "pypdf": _module_available("pypdf"),
        "fastapi_optional": _module_available("fastapi"),
        "typer_optional": _module_available("typer"),
        "provider_config": provider_config_status(),
    }


def _tool_configure(args: dict[str, Any]) -> dict[str, Any]:
    env_file = args.get("env_file", ".env.local")
    return {
        "env_file": env_file,
        "template": configuration_template(),
        "providers": provider_config_status(env_file),
    }


def _tool_cancel(args: dict[str, Any]) -> dict[str, Any]:
    root = Path(args.get("root", ".uo/runs"))
    runtime = RuntimeStore(root / "runtime.sqlite3")
    return runtime.request_cancel(
        args["run_id"],
        args.get("reason", "User requested cancellation."),
    )


def _tool_evals(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("run"):
        return EvaluationRunner().run(
            root=args.get("root", ".uo/evals"),
            case_ids=args.get("case_ids"),
        ).model_dump(mode="json")
    return built_in_suite().model_dump(mode="json")


def _tool_resume(args: dict[str, Any]) -> dict[str, Any]:
    result = Orchestrator(args.get("root", ".uo/runs")).resume(args["run_id"])
    return {
        "run_id": result.run_id,
        "state": result.state,
        "artifact_dir": result.artifact_dir,
        "quality_passed": result.quality.passed,
    }


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
