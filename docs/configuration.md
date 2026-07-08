# Configuration

The deterministic MVP works without provider keys. Provider configuration is detected from environment variables only; secrets are not printed.

## Environment Variables

- `OPENAI_API_KEY`: enables the `openai.configured` provider descriptor.
- `ANTHROPIC_API_KEY`: enables the `anthropic.configured` provider descriptor.
- `OLLAMA_BASE_URL`: enables the `ollama.local` provider descriptor.

Current provider detection is read-only. Real provider calls will be added behind explicit adapter modules and tests.

## Commands

```bash
PYTHONPATH=src python -m universal_orchestrator doctor
PYTHONPATH=src python -m universal_orchestrator providers
PYTHONPATH=src python -m universal_orchestrator run "Build a product package" ./path-or-url
PYTHONPATH=src python -m universal_orchestrator repo "Analyze this repo" .
PYTHONPATH=src python -m universal_orchestrator artifacts
PYTHONPATH=src python -m universal_orchestrator status <run_id>
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

