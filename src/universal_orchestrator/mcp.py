from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from universal_orchestrator.cli import _module_available
from universal_orchestrator.config import configuration_template, load_env_file, provider_config_status
from universal_orchestrator.evals import built_in_suite
from universal_orchestrator.models import Host, HostInvocation, InputAttachment, UserOptions
from universal_orchestrator.pipeline import Orchestrator
from universal_orchestrator.routing import CapabilityRegistry
from universal_orchestrator.utils import read_json


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
            "name": "ai_team.cancel",
            "description": "Cancellation placeholder for future durable runs.",
            "inputSchema": {
                "type": "object",
                "required": ["run_id"],
                "properties": {"run_id": {"type": "string"}},
            },
        },
        {
            "name": "ai_team.evals",
            "description": "List built-in world-readiness evaluation cases.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    if name == "ai_team.run":
        return _tool_run(args)
    if name == "ai_team.status":
        return _tool_status(args)
    if name == "ai_team.artifacts":
        return _tool_artifacts(args)
    if name == "ai_team.providers":
        return _tool_providers()
    if name == "ai_team.doctor":
        return _tool_doctor()
    if name == "ai_team.configure":
        return _tool_configure(args)
    if name == "ai_team.cancel":
        return {"run_id": args.get("run_id"), "cancelled": False, "reason": "Durable cancellation is not implemented yet."}
    if name == "ai_team.evals":
        return built_in_suite().model_dump(mode="json")
    raise ValueError(f"Unknown tool: {name}")


def serve_stdio(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    for line in stdin:
        if not line.strip():
            continue
        response = handle_json_rpc(json.loads(line))
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()


def handle_json_rpc(request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    method = request.get("method")
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "universal-orchestrator", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": tool_definitions()}
        elif method == "tools/call":
            params = request.get("params", {})
            payload = call_tool(params.get("name", ""), params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}]}
        elif method == "ping":
            result = {}
        else:
            return _error(request_id, -32601, f"Method not found: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:  # pragma: no cover - protocol boundary
        return _error(request_id, -32000, str(exc))


def _tool_run(args: dict[str, Any]) -> dict[str, Any]:
    prompt = args["prompt"]
    paths = args.get("paths", [])
    options = UserOptions(
        quality=args.get("quality", "serious"),
        budget_profile=args.get("budget", "balanced"),
        allow_internet=bool(args.get("allow_internet", False)),
    )
    invocation = HostInvocation(
        host=Host.API,
        command="mcp.run",
        prompt=prompt,
        cwd=str(Path.cwd()),
        attachments=[InputAttachment(uri=path) for path in paths],
        user_options=options,
    )
    result = Orchestrator(args.get("root", ".uo/runs")).run(invocation)
    return {
        "run_id": result.run_id,
        "state": result.state,
        "artifact_dir": result.artifact_dir,
        "quality_passed": result.quality.passed,
        "manifest_path": str(Path(result.artifact_dir) / "run_manifest.json"),
    }


def _tool_status(args: dict[str, Any]) -> dict[str, Any]:
    path = Path(args.get("root", ".uo/runs")) / args["run_id"] / "run_manifest.json"
    return read_json(path)


def _tool_artifacts(args: dict[str, Any]) -> dict[str, Any]:
    root = args.get("root", ".uo/runs")
    runs = [str(path) for path in Orchestrator(root).list_runs()]
    return {"root": root, "runs": runs}


def _tool_providers() -> dict[str, Any]:
    registry = CapabilityRegistry.from_environment()
    return {"providers": [provider.model_dump(mode="json") for provider in registry.providers]}


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


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
