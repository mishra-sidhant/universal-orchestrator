# Universal Orchestrator

Universal Orchestrator is the first implementation pass for the "Universal AI Executive Kernel" product described in the attached architecture report. It is a host-agnostic, model-agnostic orchestration runtime that turns messy user input into typed context, a product contract, an execution DAG, provider routing decisions, quality gates, and final artifacts.

The current milestone is a deterministic local runtime with optional provider adapters. Hosted execution remains deferred for validation, but routing and execution now enforce explicit cloud and privacy policy before an adapter can be called.

## What Works Now

- Local CLI with `run`, `repo`, `doctor`, `providers`, `artifacts`, `status`, `cancel`, and executable `evals` commands.
- Typed Pydantic data models for invocations, manifests, product contracts, DAGs, routing, execution, quality, artifacts, and run manifests.
- Universal input ingestion MVP for prompts, text/markdown, PDFs, folders, repositories, URLs, images, Office files, spreadsheets, archives, and unknown files.
- Secret and prompt-injection risk scanning before context cards are built.
- Common provider/PAT/JWT/private-key/credential-URL redaction, complete archive-member inspection, SSRF/private-network blocking, and child-process environment scrubbing.
- Redacted full-text extraction, bounded repository hot/prompt-matched file reads, stable source chunks with path/line locators, provenance, and task-specific context packs.
- Product contract compiler that turns natural prompts into enforceable definitions of done.
- Property-derived planner review and a five-node typed DAG backed by real local stage workers.
- Capability-based routing with truthful local capabilities; unsupported work reshapes, pauses, or skips instead of echo-completing.
- Reconciled dry-run usage estimates, budget control, relevant-prior-run delta planning, versioned exact-match cache reuse, retries, timeouts, durable cancellation, failure diagnostics, and same-run resume.
- Approval gates, safe repo validation planning/execution, and daemon/MCP status parity.
- Quality gate engine with contract, manifest, DAG, routing, security, evidence audit, repo validation, and artifact integrity checks.
- Quality telemetry is provenance-limited: parse coverage, consumed-reference coverage, task continuity, routing efficiency, artifact presence, and executed code validation. It does not claim factuality or style scoring.
- Quality failures execute repair tasks through the scheduler; unresolved runs terminate as `needs_attention` and never receive a delivery receipt.
- Immutable delivery finalization with a frozen run manifest, checksums, validated ZIP, integrity report, and hash-bound delivery receipt.
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
7. Execute deterministic MVP workers.
8. Audit declared evidence references and run derived quality gates.
9. Freeze the manifest, checksums, delivery bundle, validation, and receipt in order.

See [Product Requirements](docs/product-requirements.md) and [Implementation Plan](docs/implementation-plan.md) for the detailed roadmap.

Current limitation: local synthesis is extractive, not model reasoning, and does not prove factual entailment. Evidence refs are restricted to chunks actually delivered to each task, but `citation_support` means consumed-reference coverage, not factual verification. See [Quality Metric Provenance](docs/quality-metrics.md) and [ADR-001](docs/adr/ADR-001-kernel-unification.md).
