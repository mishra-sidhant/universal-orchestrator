"""Safe, receipt-backed MCP host configuration management."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from universal_orchestrator.utils import sha256_bytes


SERVER_ID = "universal-orchestrator"


class IntegrationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    host: str
    scope: str
    path: str
    format: str
    server_id: str = SERVER_ID
    before_sha256: str | None = None
    after_sha256: str | None = None
    installed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    changed: bool = False
    warnings: list[str] = Field(default_factory=list)


class HostSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str
    config_format: str
    config_key: str
    default_user_path: str
    default_project_path: str


HOST_SPECS: dict[str, HostSpec] = {
    "codex": HostSpec(
        host="codex",
        config_format="toml",
        config_key="mcp_servers",
        default_user_path="~/.codex/config.toml",
        default_project_path=".codex/config.toml",
    ),
    "claude-code": HostSpec(
        host="claude-code",
        config_format="json",
        config_key="mcpServers",
        default_user_path="~/.claude.json",
        default_project_path=".mcp.json",
    ),
    "cursor": HostSpec(
        host="cursor",
        config_format="json",
        config_key="mcpServers",
        default_user_path="~/.cursor/mcp.json",
        default_project_path=".cursor/mcp.json",
    ),
    "vscode": HostSpec(
        host="vscode",
        config_format="json",
        config_key="servers",
        default_user_path="~/.config/Code/User/mcp.json",
        default_project_path=".vscode/mcp.json",
    ),
    "windsurf": HostSpec(
        host="windsurf",
        config_format="json",
        config_key="mcpServers",
        default_user_path="~/.codeium/windsurf/mcp_config.json",
        default_project_path=".windsurf/mcp_config.json",
    ),
    "generic": HostSpec(
        host="generic",
        config_format="json",
        config_key="mcpServers",
        default_user_path="~/.config/ai-team/mcp.json",
        default_project_path=".ai-team/mcp.json",
    ),
}


class IntegrationError(RuntimeError):
    pass


class IntegrationManager:
    def __init__(self, *, executable: str = "ai-team") -> None:
        self.executable = executable

    def spec(self, host: str) -> HostSpec:
        try:
            return HOST_SPECS[host]
        except KeyError as exc:
            raise IntegrationError(f"Unsupported host integration: {host}") from exc

    def target_path(
        self,
        host: str,
        *,
        scope: str = "user",
        cwd: Path | str | None = None,
        explicit_path: Path | str | None = None,
    ) -> Path:
        if scope not in {"user", "project"}:
            raise IntegrationError("Integration scope must be `user` or `project`.")
        if explicit_path is not None:
            return Path(explicit_path).expanduser().resolve()
        spec = self.spec(host)
        if scope == "project":
            base = Path(cwd or Path.cwd()).expanduser().resolve()
            return (base / spec.default_project_path).resolve()
        return Path(spec.default_user_path).expanduser().resolve()

    def install(
        self,
        host: str,
        *,
        scope: str = "user",
        cwd: Path | str | None = None,
        explicit_path: Path | str | None = None,
    ) -> IntegrationReceipt:
        spec = self.spec(host)
        path = self.target_path(host, scope=scope, cwd=cwd, explicit_path=explicit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        before = path.read_bytes() if path.exists() else None
        if spec.config_format == "toml":
            updated = _install_toml(path, self.executable)
        else:
            updated = _install_json(path, spec.config_key, self.executable)
        if before == updated:
            return IntegrationReceipt(
                host=host,
                scope=scope,
                path=str(path),
                format=spec.config_format,
                before_sha256=sha256_bytes(before) if before is not None else None,
                after_sha256=sha256_bytes(updated),
                changed=False,
            )
        _atomic_write(path, updated)
        return IntegrationReceipt(
            host=host,
            scope=scope,
            path=str(path),
            format=spec.config_format,
            before_sha256=sha256_bytes(before) if before is not None else None,
            after_sha256=sha256_bytes(updated),
            changed=True,
        )

    def verify(
        self,
        host: str,
        *,
        scope: str = "user",
        cwd: Path | str | None = None,
        explicit_path: Path | str | None = None,
    ) -> dict[str, Any]:
        spec = self.spec(host)
        path = self.target_path(host, scope=scope, cwd=cwd, explicit_path=explicit_path)
        if not path.exists():
            return {"host": host, "path": str(path), "configured": False, "reason": "file_missing"}
        try:
            payload = _read_config(path, spec.config_format)
            server = payload.get(spec.config_key, {}).get(SERVER_ID)
            configured = isinstance(server, dict) and server.get("command") == self.executable
            return {
                "host": host,
                "path": str(path),
                "configured": configured,
                "command": server.get("command") if isinstance(server, dict) else None,
            }
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"host": host, "path": str(path), "configured": False, "reason": str(exc)}

    def uninstall(
        self,
        host: str,
        *,
        scope: str = "user",
        cwd: Path | str | None = None,
        explicit_path: Path | str | None = None,
    ) -> IntegrationReceipt:
        spec = self.spec(host)
        path = self.target_path(host, scope=scope, cwd=cwd, explicit_path=explicit_path)
        if not path.exists():
            return IntegrationReceipt(host=host, scope=scope, path=str(path), format=spec.config_format)
        before = path.read_bytes()
        if spec.config_format == "toml":
            updated = _uninstall_toml(path)
        else:
            updated = _uninstall_json(path, spec.config_key)
        if updated != before:
            _atomic_write(path, updated)
        return IntegrationReceipt(
            host=host,
            scope=scope,
            path=str(path),
            format=spec.config_format,
            before_sha256=sha256_bytes(before),
            after_sha256=sha256_bytes(updated),
            changed=updated != before,
        )


def _server_config(executable: str) -> dict[str, Any]:
    return {"command": executable, "args": ["mcp-server"]}


def _read_config(path: Path, config_format: str) -> dict[str, Any]:
    text = path.read_text()
    if config_format == "json":
        return cast(dict[str, Any], json.loads(_strip_json_comments(text)))
    import tomllib

    with path.open("rb") as handle:
        return tomllib.load(handle)


def _install_json(path: Path, config_key: str, executable: str) -> bytes:
    payload: dict[str, Any] = {}
    if path.exists():
        payload = _read_config(path, "json")
        if not isinstance(payload, dict):
            raise IntegrationError(f"Host configuration root must be an object: {path}")
    servers = payload.get(config_key, {})
    if servers is None:
        servers = {}
    if not isinstance(servers, dict):
        raise IntegrationError(f"Host MCP configuration `{config_key}` must be an object: {path}")
    servers[SERVER_ID] = _server_config(executable)
    payload[config_key] = servers
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _uninstall_json(path: Path, config_key: str) -> bytes:
    payload = _read_config(path, "json")
    servers = payload.get(config_key)
    if isinstance(servers, dict):
        servers.pop(SERVER_ID, None)
        if not servers:
            payload.pop(config_key, None)
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _install_toml(path: Path, executable: str) -> bytes:
    before = path.read_text() if path.exists() else ""
    block = (
        '[mcp_servers."universal-orchestrator"]\n'
        f"command = {json.dumps(executable)}\n"
        'args = ["mcp-server"]\n'
    )
    pattern = re.compile(
        r'(?ms)^\[mcp_servers\."universal-orchestrator"\]\n.*?(?=^\[|\Z)'
    )
    if pattern.search(before):
        return pattern.sub(block, before).encode("utf-8")
    suffix = "" if not before or before.endswith("\n") else "\n"
    return (before + suffix + block).encode("utf-8")


def _uninstall_toml(path: Path) -> bytes:
    before = path.read_text()
    pattern = re.compile(
        r'(?ms)^\[mcp_servers\."universal-orchestrator"\]\n.*?(?=^\[|\Z)'
    )
    return pattern.sub("", before).encode("utf-8")


def _strip_json_comments(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and next_char == "*":
            index += 2
            while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                index += 1
            index += 2
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.uo-tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
    if sys.platform != "win32":
        path.chmod(0o600)
