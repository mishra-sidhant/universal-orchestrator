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
- `ANTHROPIC_MAX_TOKENS`: optional positive output-token limit; defaults to `4096` and is included in dry-run usage estimates.
- `OLLAMA_BASE_URL`: enables the `ollama.local` provider descriptor.
- `OLLAMA_MODEL`: model id used by the Ollama adapter when live calls are enabled.

Provider detection is read-only by default. Hosted execution requires `--allow-internet`, `--allow-cloud`, a privacy mode that permits hosted models, and the provider-specific key/model variables. Internet permission alone never grants cloud execution, and `local_only` privacy cannot be overridden by a key or flag.

Add keys later in the repository-root `.env.local` file:

```text
OPENAI_API_KEY=
OPENAI_MODEL=
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
# ANTHROPIC_MAX_TOKENS=4096
OLLAMA_BASE_URL=
OLLAMA_MODEL=
```

Run `python -m universal_orchestrator configure` to see missing values without printing configured secrets.

Provider capability numbers shown by `providers` are configured routing priors, not measured facts. Update them only as configuration-backed hypotheses until benchmark evidence exists.

## Explicit Live Smoke

`smoke` is the only sanctioned standalone live check. It sends one fixed tiny prompt, requires the selected provider to be configured, applies a socket-level timeout, and prints round-trip latency plus provider-reported token usage. It is opt-in and is never run by CI.

```bash
uv run python -m universal_orchestrator smoke --provider openai.configured
uv run python -m universal_orchestrator smoke --provider anthropic.configured
uv run python -m universal_orchestrator smoke --provider ollama.local
```

Do not paste keys into commands. Add them only to the gitignored `.env.local` file or the process environment. Actual USD pricing is added by the cost-ledger phase; until then the smoke result leaves `estimated_cost_usd` unset rather than inventing a price.

## Commands

```bash
PYTHONPATH=src python -m universal_orchestrator doctor
PYTHONPATH=src python -m universal_orchestrator configure
PYTHONPATH=src python -m universal_orchestrator configure --write-example
PYTHONPATH=src python -m universal_orchestrator providers
PYTHONPATH=src python -m universal_orchestrator smoke --provider openai.configured
PYTHONPATH=src python -m universal_orchestrator mcp-server
PYTHONPATH=src python -m universal_orchestrator run "Build a product package" ./path-or-url
PYTHONPATH=src python -m universal_orchestrator run "Fetch approved host" --allow-internet --allow-url-host approved.example ./url
PYTHONPATH=src python -m universal_orchestrator repo "Analyze this repo" .
PYTHONPATH=src python -m universal_orchestrator artifacts
PYTHONPATH=src python -m universal_orchestrator status <run_id>
PYTHONPATH=src python -m universal_orchestrator cancel <run_id>
PYTHONPATH=src python -m universal_orchestrator resume <run_id>
PYTHONPATH=src python -m universal_orchestrator evals --run
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
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/resume`
- `GET /artifacts`

## Privacy Defaults

- URL fetch is not performed without explicit internet permission.
- Internet-enabled URL fetch accepts only HTTP(S), rejects credentials in URLs, DNS failures, loopback, link-local, private, reserved, multicast, and unspecified addresses, and does not follow redirects. `--allow-url-host` is an explicit exact-host override and restriction.
- Archives are not unpacked yet.
- Secret-like text is redacted before summaries, extracted context, and source chunks are persisted.
- Untrusted prompt-injection-like content is recorded as a risk card.
- Hosted provider descriptors are disabled unless their environment variables are present.
- Hosted models additionally require explicit cloud permission; provider availability is never treated as execution authority.
- `local_only` blocks hosted transport invocation even when keys, models, internet permission, cloud permission, and a hosted route are all present.
- Source chunks flagged for prompt-injection risk are quarantined from provider context. Remaining source context is labeled and delimited as untrusted data.
- Provider JSON payloads are recursively redacted immediately before transport serialization; persisted artifacts and delivery ZIP members are independently key-swept in regression tests.
- Repository validation never auto-runs `npm test` or `cargo test`; Python unittest subprocesses receive only `PATH`, `HOME`, `LANG`, and explicitly declared command variables.
