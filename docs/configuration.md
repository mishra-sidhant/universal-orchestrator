# Configuration

The deterministic MVP works without provider keys. Provider configuration is detected from environment variables and `.env.local`; secrets are not printed.

Recommended local secrets file:

```text
.env.local
```

Use `.env.example` as the template. `.env.local` is ignored by git.

## Environment Variables

- `OPENAI_API_KEY`: enables the `openai.configured` provider descriptor.
- `OPENAI_MODEL`: model id used by the OpenAI Responses adapter when live calls are enabled.
- `OPENAI_BASE_URL`: optional override for OpenAI-compatible Responses API base URL.
- `ANTHROPIC_API_KEY`: enables the `anthropic.configured` provider descriptor.
- `ANTHROPIC_MODEL`: model id used by the Anthropic adapter when live calls are enabled.
- `ANTHROPIC_BASE_URL`: optional Anthropic API base URL override.
- `ANTHROPIC_VERSION`: optional Anthropic API version override; defaults to `2023-06-01`.
- `OLLAMA_BASE_URL`: enables the `ollama.local` provider descriptor.
- `OLLAMA_MODEL`: model id used by the Ollama adapter when live calls are enabled.

Provider detection is read-only by default. Real provider adapters exist, but they run in dry-run mode unless a run is created with internet access enabled and the provider-specific key/model variables are configured.

## Commands

```bash
PYTHONPATH=src python -m universal_orchestrator doctor
PYTHONPATH=src python -m universal_orchestrator configure
PYTHONPATH=src python -m universal_orchestrator configure --write-example
PYTHONPATH=src python -m universal_orchestrator providers
PYTHONPATH=src python -m universal_orchestrator mcp-server
PYTHONPATH=src python -m universal_orchestrator run "Build a product package" ./path-or-url
PYTHONPATH=src python -m universal_orchestrator repo "Analyze this repo" .
PYTHONPATH=src python -m universal_orchestrator artifacts
PYTHONPATH=src python -m universal_orchestrator status <run_id>
PYTHONPATH=src python -m universal_orchestrator cancel <run_id>
```

## Artifact Location

Default output:

```text
.uo/runs/{run_id}/
```

Override with:

```bash
PYTHONPATH=src python -m universal_orchestrator run "..." --root /tmp/uo-runs
```

## Optional Daemon

The daemon module exposes a FastAPI app when the optional dependency is installed.

```bash
python -m pip install -e ".[daemon]"
uvicorn universal_orchestrator.daemon:app --reload
```

Endpoints:

- `GET /health`
- `GET /providers`
- `POST /runs`

## Privacy Defaults

- URL fetch is not performed by the deterministic MVP.
- Archives are not unpacked yet.
- Secret-like text is redacted before summaries are created.
- Untrusted prompt-injection-like content is recorded as a risk card.
- Hosted provider descriptors are disabled unless their environment variables are present.
