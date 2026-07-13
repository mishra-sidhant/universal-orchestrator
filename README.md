# Universal Orchestrator

Universal Orchestrator is the first implementation pass for the "Universal AI Executive Kernel" product described in the attached architecture report. It is a host-agnostic, model-agnostic orchestration runtime that turns messy user input into typed context, a product contract, an execution DAG, provider routing decisions, quality gates, and final artifacts.

The current milestone is a deterministic local runtime with fixture-validated live provider transports and model-backed synthesis. With a complete provider configuration plus explicit cloud, internet, and premium-budget permission, `T-SYNTHESIS` executes through a selected model; otherwise the established local extractive path remains the default. Routing and execution enforce cloud and privacy policy before any adapter can be called.

## What Works Now

- Local CLI with `run`, `repo`, `doctor`, `providers`, `artifacts`, `status`, `cancel`, `smoke`, `bench`, and executable `evals` commands.
- Typed Pydantic data models for invocations, manifests, product contracts, DAGs, routing, execution, quality, artifacts, and run manifests.
- Universal input ingestion MVP for prompts, text/markdown, PDFs, folders, repositories, URLs, images, Office files, spreadsheets, archives, and unknown files.
- Safe archive extraction with traversal/link/size guards, plus optional fixture-tested Tesseract OCR and local Whisper timestamped transcription boundaries; optional tools never download models automatically.
- Secret and prompt-injection risk scanning before context cards are built.
- Common provider/PAT/JWT/private-key/credential-URL redaction, complete archive-member inspection, SSRF/private-network blocking, and child-process environment scrubbing.
- Recursive redaction at the provider transport boundary, prompt-injection chunk quarantine, and explicit untrusted-data delimiters around model context.
- Redacted full-text extraction, bounded repository hot/prompt-matched file reads, stable source chunks with path/line locators, provenance, and task-specific context packs.
- Product contract compiler that turns natural prompts into enforceable definitions of done.
- Property-derived planner review and a typed DAG with independent chapter fan-out, durable checkpoints, and real local stage workers.
- Capability-based routing with truthful local capabilities; unsupported work reshapes, pauses, or skips instead of echo-completing.
- Provider/model/account capacity windows with exact reservation checks, configured-prior disclosure, and capacity-aware routing across API, local, and frontier provider families.
- Request, directional-token, total-token, concurrency, and bounded subscription-call reservations are enforced before provider execution; subscription usage is durable in the run SQLite store and never presented as free metered spend.
- Gemini AI Studio, xAI, and generic OpenAI-compatible fixture-tested adapters; consumer subscription execution remains isolated to official CLI adapters.
- Official Claude Code and Codex CLI subprocess adapters with stdin prompts, read-only bounded execution, CLI-owned authentication, structured output parsing, usage capture, and quota-failure classification.
- TTL-cached provider liveness probes, health-weighted cross-family routing, explicit degraded-mode reports, and local fallback when hosted families are down.
- A default $0.50 live-spend ceiling, pre-call reservations, versioned configured rates, provider-reported actual token accounting, estimate/actual reconciliation, and explicit budget stops.
- Reconciled dry-run usage estimates, token-budget control, relevant-prior-run delta planning, versioned exact-match cache reuse, typed provider failures, bounded retries, socket timeouts, durable cancellation, failure diagnostics, and same-run resume.
- Resume restores only validated cacheable checkpoints with an exact execution fingerprint; side-effecting artifact tasks rerun. Provider handoff can cross two bounded alternatives while preserving the original task context and budget boundary.
- Approval gates, safe repo validation planning/execution, and daemon/MCP status parity.
- Quality gate engine with contract, manifest, DAG, routing, security, evidence audit, repo validation, and artifact integrity checks.
- Quality telemetry is provenance-limited: parse coverage, consumed-reference coverage, task continuity, routing efficiency, artifact presence, and executed code validation. It does not claim factuality or style scoring.
- Quality failures execute repair tasks through the scheduler; unresolved runs terminate as `needs_attention` and never receive a delivery receipt.
- Model synthesis accepts only strict structured output, allows one metered reformat repair, audits each claim against delivered chunk IDs, and degrades honestly to extractive synthesis after validation failure.
- Immutable delivery finalization with a frozen run manifest, checksums, validated ZIP, integrity report, and hash-bound delivery receipt.
- PDF, DOCX, and PPTX delivery includes structural checks plus bitmap validation of every rendered page. Serious/max quality bars block on render failure, blank pages, or unavailable render tooling; fast/standard record a warning. Rich reports are assembled from independently synthesized, run-type-specific chapters rather than a single cosmetic slide.
- A native-versus-orchestrated benchmark bundle with side-by-side outputs, per-path cost and latency, plus orchestrated quality/evidence reports. It makes no automated superiority claim; comparison requires human judgment.
- Typed product/chapter plans and PPTX artifact construction with structural slide validation, alongside the existing PDF/DOCX builders.
- Standard-library test suite, so the repo can validate without installing pytest.

## Quick Start

On a bare macOS host, install [`uv`](https://docs.astral.sh/uv/getting-started/installation/). It can install the required Python version as well as project dependencies, so no system Python 3.11+ is required.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --all-extras --dev
uv run python -m universal_orchestrator doctor
uv run python -m universal_orchestrator run "Build an implementation plan from this repo" .
uv run python -m universal_orchestrator repo "Analyze and improve the current project" .
uv run python -m universal_orchestrator evals --run --case unsafe_archive
uv run ai-team release-gate
uv run python -m unittest discover -s tests
```

`uv sync` creates the project environment and installs the package in editable mode. Later commands should continue to use `uv run`; shell activation is optional.

From a checkout with an existing Python 3.11+ environment:

```bash
PYTHONPATH=src python -m universal_orchestrator doctor
PYTHONPATH=src python -m universal_orchestrator run "Summarize this report" /path/to/report.pdf
```

## Optional Install

The default install includes the supported artifact parsers/builders. CLI and daemon surfaces remain optional extras.

```bash
python -m pip install -e .
python -m pip install -e ".[daemon,dev]"
```

## Product Shape

The kernel follows this pipeline:

1. Normalize a host invocation.
2. Ingest all supplied inputs into a `ContextManifest`.
3. Build and rank `ContextCard` records.
4. Compile a `ProductContract` and `DefinitionOfDone`.
5. Create a typed `TaskDAG`.
6. Route tasks by capability, health, risk, and cost.
7. Execute deterministic workers and policy-permitted model synthesis.
8. Audit declared evidence references and run derived quality gates.
9. Freeze the manifest, checksums, delivery bundle, validation, and receipt in order.

See [Product Requirements](docs/product-requirements.md) and [Implementation Plan](docs/implementation-plan.md) for the detailed roadmap.

Current limitation: keyless synthesis is extractive, and neither local nor model synthesis proves factual entailment. Evidence refs are restricted to chunks actually delivered to each task; `citation_support` means consumed-reference coverage, while the model-path lexical-overlap warning is only a weak diagnostic floor. See [Quality Metric Provenance](docs/quality-metrics.md) and [ADR-001](docs/adr/ADR-001-kernel-unification.md).

Provider capability numbers are configured priors used for routing, not measured quality facts. They remain priors until a versioned benchmark records a measurement.

Capacity observations follow the same honesty rule: exact structured provider windows can be reserved durably; observed-only or unknown limits are surfaced as such and never treated as unlimited. A provider that exhausts or stalls during a task can be handed off within the configured alternatives, with grounded local fallback and a degraded-mode notice when no provider remains.

The kernel is headless. Codex, Claude Code, VS Code/Copilot, compatible desktop agents, and the terminal are host surfaces; MCP and CLI expose the same run, status, capacity, and artifact contract. A separate dashboard is not required.

Use `uv run ai-team integrate --host codex|claude-code|vscode|generic` to print a read-only MCP configuration. See [Headless Host Integrations](docs/host-integrations.md).

The kernel is headless. Codex, Claude Code, VS Code/Copilot, compatible desktop agents, and the terminal are host surfaces; MCP and CLI expose the same run/status/capacity/artifact contract. A separate dashboard is not required.

## Live Setup And Measurement

Add keys and model IDs later in the repository-root `.env.local` file, which is gitignored. Use `.env.example` as the template; never place keys in commands, committed configuration, or benchmark artifacts.

```bash
uv run python -m universal_orchestrator configure
uv run python -m universal_orchestrator smoke --provider openai.configured
uv run python -m universal_orchestrator smoke --provider anthropic.configured
uv run python -m universal_orchestrator smoke --provider claude-code.cli
uv run python -m universal_orchestrator smoke --provider codex.cli
uv run python -m universal_orchestrator bench \
  "Compare native and orchestrated output" ./source.pdf \
  --allow-internet --allow-cloud --budget premium --cost-ceiling 0.50
```

Run real smoke checks once per configured provider, then one real bench. These are operator actions and are never part of CI. Paste their JSON summaries into `docs/implementation-log.md` under "Operator Live Evidence." `bench` is a measurement instrument: it records outputs, latency, cost, quality, and evidence for review, but never declares a winner.

For subscription execution, authenticate through the official CLI (`claude` login flow or `codex login`). The orchestrator does not read CLI auth files and does not forward API-key environment variables into CLI processes. CLI capacity is exact only when the official surface exposes a structured limit; otherwise it is reported as observed or unknown.

Best practices: start keyless with local runs and fixture evals; run `uv run ai-team release-gate` before release; keep the default $0.50 ceiling unless you intentionally configure a lower operator limit; use `local_only` for sensitive inputs; run `smoke` before a real job; review `budget_report.json`, `cost_ledger.json`, `evidence_audit.json`, `fidelity_report.json`, `validator_panel.json`, and provider health before trusting a delivery; and treat benchmark output as evidence for human comparison, never as an automatic quality claim.
