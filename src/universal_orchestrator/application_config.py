"""Versioned, non-secret application configuration.

Provider credentials are deliberately represented by environment-variable names
or keychain references, never by values in these files.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field


CONFIG_SCHEMA_VERSION = 1


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderProfile(ConfigModel):
    provider_id: str
    model: str | None = None
    base_url: str | None = None
    credential_env: str | None = None
    credential_ref: str | None = None
    enabled: bool = True
    capability_prior_overrides: dict[str, float] = Field(default_factory=dict)


class AppConfig(ConfigModel):
    schema_version: int = CONFIG_SCHEMA_VERSION
    active_profile: str = "default"
    privacy_mode: str = "balanced"
    cost_ceiling_usd: float = Field(default=0.50, gt=0.0)
    max_parallel_tasks: int = Field(default=4, ge=1, le=32)
    repo_sandbox: str = "strict_container"
    root: str = ".uo/runs"
    providers: dict[str, ProviderProfile] = Field(default_factory=dict)


class ConfigPaths:
    """Stable application directories with an explicit test override."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).expanduser() if root is not None else self._default_root()
        self.config_file = self.root / "config.toml"
        self.profiles_dir = self.root / "profiles"
        self.state_dir = self.root / "state"
        self.cache_dir = self.root / "cache"
        self.worktrees_dir = self.root / "worktrees"
        self.logs_dir = self.root / "logs"

    @staticmethod
    def _default_root() -> Path:
        override = os.getenv("AI_TEAM_HOME")
        if override:
            return Path(override).expanduser()
        system = platform.system()
        if system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "ai-team"
        if system == "Windows":
            return Path(os.getenv("APPDATA", str(Path.home()))) / "ai-team"
        return Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "ai-team"

    def create(self) -> None:
        for directory in (
            self.root,
            self.profiles_dir,
            self.state_dir,
            self.cache_dir,
            self.worktrees_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


class CredentialStore:
    """Optional OS keychain boundary used by interactive setup."""

    service = "universal-orchestrator"

    def get(self, reference: str) -> str | None:
        try:
            import keyring
        except ImportError:
            return None
        try:
            return cast(str | None, keyring.get_password(self.service, reference))
        except Exception:
            return None

    def set(self, reference: str, value: str) -> None:
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError(
                "OS keychain support is unavailable; set the documented environment variable instead."
            ) from exc
        keyring.set_password(self.service, reference, value)

    def delete(self, reference: str) -> None:
        try:
            import keyring
        except ImportError:
            return
        try:
            keyring.delete_password(self.service, reference)
        except Exception:
            return


def default_config() -> AppConfig:
    return AppConfig(
        providers={
            "openai.configured": ProviderProfile(
                provider_id="openai.configured",
                model=None,
                credential_env="OPENAI_API_KEY",
            ),
            "anthropic.configured": ProviderProfile(
                provider_id="anthropic.configured",
                model=None,
                credential_env="ANTHROPIC_API_KEY",
            ),
            "ollama.local": ProviderProfile(
                provider_id="ollama.local",
                model=None,
                base_url="http://127.0.0.1:11434",
            ),
            "claude-code.cli": ProviderProfile(
                provider_id="claude-code.cli",
                credential_env=None,
            ),
            "codex.cli": ProviderProfile(
                provider_id="codex.cli",
                credential_env=None,
            ),
        }
    )


def load_config(paths: ConfigPaths | None = None, profile: str | None = None) -> AppConfig:
    paths = paths or ConfigPaths()
    values: dict[str, Any] = {}
    if paths.config_file.exists():
        values.update(_read_toml(paths.config_file))
    selected = profile or str(values.get("active_profile", "default"))
    profile_path = paths.profiles_dir / f"{selected}.toml"
    if profile_path.exists():
        profile_values = _read_toml(profile_path)
        values = _deep_merge(values, profile_values)
    if not values:
        return default_config()
    version = int(values.get("schema_version", CONFIG_SCHEMA_VERSION))
    if version != CONFIG_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported application config schema {version}; run `ai-team config migrate`."
        )
    values["active_profile"] = selected
    return AppConfig.model_validate(values)


def save_config(config: AppConfig, paths: ConfigPaths | None = None) -> Path:
    paths = paths or ConfigPaths()
    paths.create()
    _atomic_write(paths.config_file, _to_toml(config.model_dump(mode="json", exclude_none=True)))
    return paths.config_file


def save_profile(config: AppConfig, profile: str, paths: ConfigPaths | None = None) -> Path:
    paths = paths or ConfigPaths()
    paths.create()
    path = paths.profiles_dir / f"{profile}.toml"
    _atomic_write(path, _to_toml(config.model_dump(mode="json", exclude_none=True)))
    return path


def initialize(paths: ConfigPaths | None = None, overwrite: bool = False) -> AppConfig:
    paths = paths or ConfigPaths()
    paths.create()
    if paths.config_file.exists() and not overwrite:
        return load_config(paths)
    config = default_config()
    save_config(config, paths)
    save_profile(config, "default", paths)
    return config


def migrate_env_file(
    env_file: Path | str = ".env.local", paths: ConfigPaths | None = None
) -> tuple[AppConfig, list[str]]:
    """Import non-secret provider settings; leave all credential values untouched."""

    from universal_orchestrator.config import env_file_presence

    paths = paths or ConfigPaths()
    config = load_config(paths)
    presence = env_file_presence(env_file)
    loaded: list[str] = []
    env_to_provider = {
        "OPENAI_MODEL": ("openai.configured", "model"),
        "ANTHROPIC_MODEL": ("anthropic.configured", "model"),
        "OLLAMA_MODEL": ("ollama.local", "model"),
        "OLLAMA_BASE_URL": ("ollama.local", "base_url"),
        "GEMINI_MODEL": ("gemini.configured", "model"),
        "XAI_MODEL": ("xai.configured", "model"),
        "OPENAI_COMPATIBLE_MODEL": ("openai-compatible.local", "model"),
        "OPENAI_COMPATIBLE_BASE_URL": ("openai-compatible.local", "base_url"),
    }
    raw_values = _read_env_values(Path(env_file))
    for env_name, (provider_id, field_name) in env_to_provider.items():
        value = raw_values.get(env_name)
        if not value:
            continue
        existing = config.providers.get(provider_id) or ProviderProfile(provider_id=provider_id)
        config.providers[provider_id] = existing.model_copy(update={field_name: value})
        loaded.append(env_name)
    for provider_id, profile in list(config.providers.items()):
        required_env = {
            "openai.configured": "OPENAI_API_KEY",
            "anthropic.configured": "ANTHROPIC_API_KEY",
        }.get(provider_id)
        if required_env and presence.get(required_env):
            config.providers[provider_id] = profile.model_copy(
                update={"credential_env": required_env}
            )
            loaded.append(required_env)
    save_config(config, paths)
    return config, sorted(set(loaded))


def apply_profile_environment(config: AppConfig) -> list[str]:
    """Project configuration may supply non-secret provider values at runtime."""

    applied: list[str] = []
    fields = {
        "openai.configured": {"model": "OPENAI_MODEL", "base_url": "OPENAI_BASE_URL"},
        "anthropic.configured": {
            "model": "ANTHROPIC_MODEL",
            "base_url": "ANTHROPIC_BASE_URL",
        },
        "ollama.local": {"model": "OLLAMA_MODEL", "base_url": "OLLAMA_BASE_URL"},
        "gemini.configured": {"model": "GEMINI_MODEL", "base_url": "GEMINI_BASE_URL"},
        "xai.configured": {"model": "XAI_MODEL", "base_url": "XAI_BASE_URL"},
        "openai-compatible.local": {
            "model": "OPENAI_COMPATIBLE_MODEL",
            "base_url": "OPENAI_COMPATIBLE_BASE_URL",
        },
    }
    for provider_id, profile in config.providers.items():
        for field_name, env_name in fields.get(provider_id, {}).items():
            value = getattr(profile, field_name)
            if value and not os.getenv(env_name):
                os.environ[env_name] = value
                applied.append(env_name)
        if profile.credential_ref and profile.credential_env and not os.getenv(profile.credential_env):
            secret = CredentialStore().get(profile.credential_ref)
            if secret:
                os.environ[profile.credential_env] = secret
                applied.append(profile.credential_env)
    return applied


def _read_toml(path: Path) -> dict[str, Any]:
    import tomllib

    with path.open("rb") as handle:
        payload = tomllib.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Configuration root must be a table: {path}")
    return payload


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            values[key.strip()] = value
    return values


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _to_toml(values: dict[str, Any]) -> str:
    lines: list[str] = []
    _append_toml_table(lines, (), values)
    return "\n".join(lines) + "\n"


def _append_toml_table(lines: list[str], prefix: tuple[str, ...], table: dict[str, Any]) -> None:
    scalars = {key: value for key, value in table.items() if not isinstance(value, dict)}
    if prefix:
        if lines:
            lines.append("")
        lines.append("[" + ".".join(_quote_key(item) for item in prefix) + "]")
    for key in sorted(scalars):
        lines.append(f"{key} = {_toml_value(scalars[key])}")
    for key in sorted(table):
        value = table[key]
        if isinstance(value, dict) and value:
            _append_toml_table(lines, (*prefix, key), value)


def _quote_key(value: str) -> str:
    return json.dumps(value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(f"{key} = {_toml_value(item)}" for key, item in value.items())
        return "{" + pairs + "}"
    return json.dumps(str(value))


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    os.replace(temporary, path)
    if sys.platform != "win32":
        path.chmod(0o600)
