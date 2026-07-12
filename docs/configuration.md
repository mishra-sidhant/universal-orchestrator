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
- `GOOGLE_API_KEY`: enables `gemini.configured` through the Gemini API.
- `GEMINI_MODEL`: Gemini model id.
- `XAI_API_KEY`: enables `xai.configured`.
- `XAI_MODEL`: xAI model id.
- `OPENAI_COMPATIBLE_BASE_URL`: enables a local OpenAI-compatible gateway.
- `OPENAI_COMPATIBLE_MODEL`: model id for that gateway.
- `CLAUDE_CODE_BIN` and `CODEX_BIN`: optional explicit executable paths; otherwise the official CLIs are discovered on `PATH` in the CLI tranche.

Provider detection is read-only by default. Hosted execution requires `--allow-internet`, `--allow-cloud`, a privacy mode that permits hosted models, and the provider-specific key/model variables. Internet permission alone never grants cloud execution, and `local_only` privacy cannot be overridden by a key or flag.

Model-backed pipeline synthesis also requires `--budget premium` because configured hosted providers are premium-tier routing options. Example:

```bash
uv run python -m universal_orchestrator run \
  "Produce a grounded research report" ./source.pdf \
  --allow-internet --allow-cloud --budget premium --cost-ceiling 0.50
```

Without a complete key/model pair, or without the required permissions and budget tier, synthesis remains local and extractive. Provider readiness requires the full pair; a key alone is not advertised as executable.

Before model routing, the runtime performs a cheap bounded liveness request (`/models`, `/v1/models`, or Ollama `/api/tags`) and caches the result for 60 seconds. These probes do not consume model tokens and are recorded separately from `cost_ledger.json`. A provider-down notice in the final report identifies the family and measured status. `local_only` makes no hosted liveness request, even when keys are present.

`bench` runs one direct strongest-provider path and one full orchestrated path, each with the requested cost ceiling. It writes a comparison directory under `.uo/bench` by default. It makes no automated superiority claim; the operator reviews the side-by-side output, cost, latency, quality, and evidence artifacts.

Add keys later in the repository-root `.env.local` file:

```text
OPENAI_API_KEY=
OPENAI_MODEL=
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
# ANTHROPIC_MAX_TOKENS=4096
OLLAMA_BASE_URL=
OLLAMA_MODEL=
GOOGLE_API_KEY=
GEMINI_MODEL=
XAI_API_KEY=
XAI_MODEL=
# OPENAI_COMPATIBLE_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_COMPATIBLE_MODEL=
# OPENAI_COMPATIBLE_API_KEY=
# CLAUDE_CODE_BIN=claude
# CODEX_BIN=codex
```

Run `python -m universal_orchestrator configure` to see missing values without printing configured secrets.

Provider capability numbers shown by `providers` are configured routing priors, not measured facts. Update them only as configuration-backed hypotheses until benchmark evidence exists.

Capacity is reported with a source and confidence. A provider with no observation is `unknown`, not unlimited. Subscription-backed CLI calls record capacity usage separately from metered API dollars, and their ledger rows are `allocated_cost_unknown` rather than priced at zero.

## Explicit Live Smoke

`smoke` is the only sanctioned standalone live check. It sends one fixed tiny prompt, requires the selected provider to be configured, applies a socket-level timeout, and prints round-trip latency plus provider-reported token usage. It is opt-in and is never run by CI.

```bash
uv run python -m universal_orchestrator smoke --provider openai.configured
uv run python -m universal_orchestrator smoke --provider anthropic.configured
uv run python -m universal_orchestrator smoke --provider ollama.local
uv run python -m universal_orchestrator smoke --provider claude-code.cli
uv run python -m universal_orchestrator smoke --provider codex.cli
```

Do not paste keys into commands. Add them only to the gitignored `.env.local` file or the process environment. Smoke reports both its pre-call estimate and provider-usage-priced actual cost from the configured rate table.

## Cost Ceiling And Rates

Every live run and smoke call defaults to a $0.50 ceiling. Operators may lower or explicitly raise it per invocation with `--cost-ceiling`; no profile, including `unlimited`, changes this default automatically. Authorization reserves estimated cost before transport, so an unaffordable call produces a recorded budget stop without opening the socket.

Provider/model rates live in `src/universal_orchestrator/provider_rates.json`, not Python code. To update pricing, edit that file, advance its `version`, add an exact model entry when available, and run the full fixture suite plus package build. Provider defaults are configured pricing priors and must be reviewed against the provider's published pricing before operator live use. Every ledger row records the table version and whether an exact model or provider default rate priced it.

## Commands

```bash
PYTHONPATH=src python -m universal_orchestrator doctor
PYTHONPATH=src python -m universal_orchestrator configure
PYTHONPATH=src python -m universal_orchestrator configure --write-example
PYTHONPATH=src python -m universal_orchestrator providers
PYTHONPATH=src python -m universal_orchestrator smoke --provider openai.configured
PYTHONPATH=src python -m universal_orchestrator bench "Compare paths" --allow-internet --allow-cloud --budget premium ./source.pdf
PYTHONPATH=src python -m universal_orchestrator mcp-server
PYTHONPATH=src python -m universal_orchestrator run "Build a product package" ./path-or-url
PYTHONPATH=src python -m universal_orchestrator run "Build a bounded package" --cost-ceiling 0.25 ./path-or-url
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
