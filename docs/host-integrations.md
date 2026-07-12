# Headless Host Integrations

Universal Orchestrator is a backend MCP/CLI plugin, not a separate dashboard. Hosts launch the same local stdio server and use `ai_team.run_start`, `ai_team.status`, `ai_team.events`, `ai_team.capacity`, `ai_team.cancel`, `ai_team.resume`, and artifact tools.

Print the host-specific JSON without modifying host files:

```bash
uv run ai-team integrate --host codex
uv run ai-team integrate --host claude-code
uv run ai-team integrate --host vscode
uv run ai-team integrate --host generic
```

The integration command is intentionally read-only. Operators review and apply the output using the host's documented MCP configuration mechanism. No host auth files, API keys, or subscription tokens are copied into the orchestrator run directory.

Codex and Claude Code subscription model execution is separate from host integration: authenticate the official CLI in its own supported manner, and let the orchestrator invoke that CLI through its bounded subprocess adapter.
