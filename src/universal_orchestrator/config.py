from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = ".env.local"

PROVIDER_ENV_VARS: dict[str, list[str]] = {
    "openai.configured": ["OPENAI_API_KEY", "OPENAI_MODEL"],
    "anthropic.configured": ["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"],
    "ollama.local": ["OLLAMA_BASE_URL", "OLLAMA_MODEL"],
    "gemini.configured": ["GOOGLE_API_KEY", "GEMINI_MODEL"],
    "xai.configured": ["XAI_API_KEY", "XAI_MODEL"],
    "openai-compatible.local": ["OPENAI_COMPATIBLE_BASE_URL", "OPENAI_COMPATIBLE_MODEL"],
}

OPTIONAL_ENV_VARS: dict[str, list[str]] = {
    "openai.configured": ["OPENAI_BASE_URL"],
    "anthropic.configured": [
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_VERSION",
        "ANTHROPIC_MAX_TOKENS",
    ],
    "ollama.local": [],
    "gemini.configured": ["GEMINI_BASE_URL"],
    "xai.configured": ["XAI_BASE_URL"],
    "openai-compatible.local": ["OPENAI_COMPATIBLE_API_KEY"],
    "claude-code.cli": ["CLAUDE_CODE_BIN"],
    "codex.cli": ["CODEX_BIN"],
}


def load_env_file(path: Path | str = DEFAULT_ENV_FILE, override: bool = False) -> list[str]:
    env_path = Path(path)
    loaded: list[str] = []
    if not env_path.exists():
        return loaded
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def env_file_presence(path: Path | str = DEFAULT_ENV_FILE) -> dict[str, bool]:
    env_path = Path(path)
    presence: dict[str, bool] = {}
    if not env_path.exists():
        return presence
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        presence[key.strip()] = bool(value.strip().strip('"').strip("'"))
    return presence


def provider_config_status(env_file: Path | str = DEFAULT_ENV_FILE) -> dict[str, dict[str, Any]]:
    file_presence = env_file_presence(env_file)
    statuses: dict[str, dict[str, Any]] = {}
    for provider_id, required_vars in PROVIDER_ENV_VARS.items():
        required = {
            name: bool(os.getenv(name)) or file_presence.get(name, False)
            for name in required_vars
        }
        optional = {
            name: bool(os.getenv(name)) or file_presence.get(name, False)
            for name in OPTIONAL_ENV_VARS.get(provider_id, [])
        }
        missing = [name for name, present in required.items() if not present]
        statuses[provider_id] = {
            "ready": not missing,
            "required": required,
            "optional": optional,
            "missing": missing,
        }
    return statuses


def configuration_template() -> str:
    return "\n".join(
        [
            "# Universal Orchestrator local provider secrets",
            "# Save as .env.local. This file is ignored by git.",
            "",
            "OPENAI_API_KEY=",
            "OPENAI_MODEL=",
            "# OPENAI_BASE_URL=https://api.openai.com/v1",
            "",
            "ANTHROPIC_API_KEY=",
            "ANTHROPIC_MODEL=",
            "# ANTHROPIC_BASE_URL=https://api.anthropic.com",
            "# ANTHROPIC_VERSION=2023-06-01",
            "# ANTHROPIC_MAX_TOKENS=4096",
            "",
            "OLLAMA_BASE_URL=http://127.0.0.1:11434",
            "OLLAMA_MODEL=",
            "",
            "GOOGLE_API_KEY=",
            "GEMINI_MODEL=",
            "# GEMINI_BASE_URL=https://generativelanguage.googleapis.com",
            "",
            "XAI_API_KEY=",
            "XAI_MODEL=",
            "# XAI_BASE_URL=https://api.x.ai/v1",
            "",
            "# OpenAI-compatible local gateway, such as a Llama/vLLM server",
            "# OPENAI_COMPATIBLE_BASE_URL=http://127.0.0.1:8000/v1",
            "OPENAI_COMPATIBLE_MODEL=",
            "# OPENAI_COMPATIBLE_API_KEY=",
            "",
            "# Set these only when the official CLIs are installed on PATH.",
            "# CLAUDE_CODE_BIN=claude",
            "# CODEX_BIN=codex",
            "",
        ]
    )


def write_env_example(path: Path | str = ".env.example", overwrite: bool = False) -> Path:
    target = Path(path)
    if target.exists() and not overwrite:
        return target
    target.write_text(configuration_template())
    return target
