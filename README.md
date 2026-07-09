# Universal Orchestrator

Universal Orchestrator is the first implementation pass for the "Universal AI Executive Kernel" product described in the attached architecture report. It is a host-agnostic, model-agnostic orchestration runtime that turns messy user input into typed context, a product contract, an execution DAG, provider routing decisions, quality gates, and final artifacts.

The current milestone is a deterministic local MVP. It does not call hosted LLMs yet; it establishes the typed kernel and product packaging path that provider adapters can plug into safely.

## What Works Now

- Local CLI with `run`, `repo`, `doctor`, `providers`, `artifacts`, `status`, and `cancel` commands.
- Typed Pydantic data models for invocations, manifests, product contracts, DAGs, routing, execution, quality, artifacts, and run manifests.
- Universal input ingestion MVP for prompts, text/markdown, PDFs, folders, repositories, URLs, images, Office files, spreadsheets, archives, and unknown files.
- Secret and prompt-injection risk scanning before context cards are built.
- Context cards, deterministic relevance ranking, provenance, and task-specific context packs.
- Product contract compiler that turns natural prompts into enforceable definitions of done.
- Planner ensemble v1 that emits a typed execution DAG.
- Capability-based provider registry and router with deterministic tools, configured provider detection, and routing telemetry.
- Budget control, delta execution planning, scheduler cache reuse, runtime state snapshots, and durable cancel markers.
- Quality gate engine with contract, manifest, DAG, routing, security, evidence audit, and artifact integrity checks.
- Artifact store that writes final reports, JSON manifests, task graphs, quality reports, routing decisions, trace reports, debug manifests, and delivery manifests.
- Standard-library test suite, so the repo can validate without installing pytest.

## Quick Start

Use the bundled Codex runtime Python, or any Python 3.11+ environment with Pydantic v2 installed.

```bash
python -m universal_orchestrator doctor
python -m universal_orchestrator run "Build an implementation plan from this repo" .
python -m universal_orchestrator repo "Analyze and improve the current project" .
```

From a checkout without installation:

```bash
PYTHONPATH=src python -m universal_orchestrator doctor
PYTHONPATH=src python -m universal_orchestrator run "Summarize this report" /path/to/report.pdf
```

Run tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Optional Install

The project metadata includes optional CLI and daemon extras. The core currently only needs Pydantic.

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
8. Run quality gates.
9. Build final artifacts and a `RunManifest`.

See [Product Requirements](docs/product-requirements.md) and [Implementation Plan](docs/implementation-plan.md) for the detailed roadmap.
