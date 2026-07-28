# Headless Host Integrations

Universal Orchestrator is a headless MCP/CLI product. Hosts launch the same stdio server and use `ai_team.run_start`, `ai_team.status`, `ai_team.events`, `ai_team.capacity`, `ai_team.cancel`, `ai_team.resume`, and artifact tools.

Inspect an integration without modifying host files:

```bash
uv run ai-team integrate --host codex
uv run ai-team integrate --host claude-code
uv run ai-team integrate --host vscode
uv run ai-team integrate --host generic
```

Install, verify, or remove an integration with an atomic, receipt-backed update:

```bash
uv run ai-team integrate --host codex --install
uv run ai-team integrate --host codex --verify
uv run ai-team integrate --host codex --uninstall
uv run ai-team integrate --host claude-code --scope project --install
uv run ai-team integrate --host cursor --install
uv run ai-team integrate --host vscode --scope project --install
uv run ai-team integrate --host windsurf --install
```

The installer changes only the `universal-orchestrator` MCP entry, preserves unrelated entries, writes a receipt with before/after hashes, and refuses malformed configuration. Use `--path` to target a nonstandard host configuration. No host auth files, API keys, or subscription tokens are copied into the orchestrator run directory.

The `ai_team.run` and `ai_team.run_start` tools preserve the same execution controls as the CLI: artifact types, the default `$0.50` ceiling, internet host allowlists, privacy mode, cloud permission, repository writes, and shell permission. Omitted controls retain their safe defaults.

The daemon exposes versioned `/v1` routes and remains loopback-oriented. Set `AI_TEAM_DAEMON_TOKEN` before exposing it beyond a trusted local process; health is the only unauthenticated route when a token is configured.

Codex and Claude Code subscription model execution is separate from host integration: authenticate the official CLI in its own supported manner, and let the orchestrator invoke that CLI through its bounded subprocess adapter.
